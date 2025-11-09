#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
12_llm_translate.py
- Excel 第1列 RU, 第2列 speaker, 第3列 EN, 第4列 当前中文(不改), 第5列 输出中文(写入)
- 读取 artifacts/scenes.json 提供“scene”上下文模式（可选）
- 集成术语：从 data/name_map.json 加载，支持“软约束（prompt excerpt）+ 硬替换（enforce）”
- 自适应并发：基于 429/延迟/排队自动调节 in-flight & rpm
- 断点续跑：WAL(.jsonl) + checkpoint(.jsonl) + 周期写盘到输出 Excel
- 仅翻译第5列为空的行；可用 --retranslate 覆盖已有译文
"""

import argparse
import json
import os
import re
import sys
import time
import threading
import queue
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# -------- Optional Glossary --------
_GLOSS: Any = None
try:
    # 尝试从 scripts/glossary_utils.py 导入 Glossary
    from scripts.glossary_utils import Glossary
    _GLOSS = Glossary
except Exception as e:
    _GLOSS = None

# -------- OpenAI-compatible client --------
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # 用于延后导入失败提示

# ------------------ Prompt Templates ------------------
BASE_SYSTEM_PROMPT = """You are a senior localization writer for an ADULT visual novel set in Sunville (阳光镇),
mostly inside a COLLEGE (学院). Output MUST be natural, colloquial Chinese for players.

GENERAL:
- Base literal meaning on EN; use RU for mood & sensual nuance when helpful.
- STRICTLY apply the glossary with LONGEST MATCH FIRST; never contradict it.
- Preserve placeholders/tags exactly: [like_this], {vars}, {{vars}}, <tags>.
- Keep brand/product names in Latin (Patreon, Instagram, Lovense).
- Use colloquial “你”; avoid stiff, bookish phrasing.
- You MAY restructure English syntax for natural Chinese (意合优先); merge or split clauses as needed.
- Use Chinese punctuation and spoken word order; avoid copying EN period-per-fragment habit.
- Output ONLY the final Chinese line (no quotes or explanations).

WORLD TERMS (PINNED):
- Sunville → 阳光镇
- College → 学院  (NEVER translate as 大学/大学院)
- Principal → 院长
- Steward → 管理员
- Doctor’s Office → 医务室
- Locker Rooms → 更衣室
- College Entrance → 学院正门

CAMPUS & TOWN LOCATION RULES (CRITICAL):
If the line is a short ALL-CAPS or Title-like label and the SPEAKER is "string"
(or otherwise looks like a map/room/UI location), translate as a PLACE NAME, not a subject:
- SUBJECT + CLASS → “X教室”：Computer Class→计算机教室; Arts Class→美术教室
- Lone SUBJECT words (BIOLOGY/PHYSICS/ENGLISH/GEOGRAPHY/ALGEBRA) in this context → “X教室”
- ...’S OFFICE:
  - DOCTOR’S OFFICE → 医务室
  - STEWARD’S OFFICE → 管理员办公室
  - (others) “某某办公室” (keep role natural in CN)
- LOCKER (singular) → 储物柜区; LOCKER ROOMS (plural) → 更衣室
- GIRL’S/BOY’S CHANGING ROOM → 女生/男生更衣室
- BOYS/GIRLS TOILET(S) → 男厕 / 女厕（全局一致）
- GYM → 体育馆; POOL → 泳池; LIBRARY → 图书馆; ASSEMBLY HALL → 学院礼堂
- COLLEGE ENTRANCE → 学院正门
- TOWN → 镇上（地图/导航标签时更自然）

SPEAKER-AWARE TONE:
- Principal/Teacher/Librarian (incl. *_t thoughts) → formal, calm, precise; no slang.
- System/Operator/Post/Help/Hotel_staff/Secretary/Policeman → concise UI/service tone; no erotic flourish.
- Punk/Whore/Stripper/Showman → bolder, street tone; explicit but not gratuitous.
- Students/Girls/Actresses/Models/teen names → youthful, casual, flirty; explicit when context requires.

OBJECTIVES / TASK HINTS (non-dialogue):
If EN is a short imperative objective (e.g., “Go to Sean’s. Meet his mother. Talk to Sean.”),
render as a natural Chinese checklist/flow, not literal one-sentence-per-dot:
- Prefer: “前往肖恩家、见见他妈妈、和肖恩聊聊”
- Or: “去趟肖恩家，先见见他妈妈，再跟肖恩聊聊。”
Avoid stiff phrases like “认识他妈妈”; use “见见他妈妈/见肖恩的妈妈”.

DIALOGUE (MOST LINES):
If it reads like human speech (pronouns, questions, interjections, longer sentences), treat as dialogue:
- Keep colloquial rhythm and erotic intensity appropriate to the scene.
- Moans/breathing (“嗯…/哈啊…/啊…”) natural but not overdone.
- Be explicit but not clinical; don’t censor sexual content.

DISAMBIGUATION HEURISTICS:
- ALL-CAPS 1–4 nouns with campus/town semantics + speaker=string → PLACE NAME per rules above.
- Multiple short imperative fragments (Go to/Meet/Talk/Find…) → OBJECTIVE style as above.
- Otherwise treat as DIALOGUE/normal UI and localize naturally.
"""

USER_PROMPT_TMPL = """[META]
SPEAKER: {speaker}
ROW: {row_id}

[RU] {ru}
[EN] {en}

If helpful, you can consider contextual lines from the same scene (SPEAKER tagged) below:
{ctx}

Output ONLY one Chinese line, no quotes, no commentary.
"""

# ------------------ Rate Limiter & Adaptive Pool ------------------
class TokenBucket:
    """Simple RPM limiter: allow N requests per minute spread across time."""
    def __init__(self, rpm: int):
        self.capacity = max(1, rpm)
        self.tokens = float(self.capacity)
        self.fill_rate = self.capacity / 60.0  # tokens per second
        self.lock = threading.Lock()
        self.last = time.time()

    def set_rpm(self, rpm: int):
        with self.lock:
            self.capacity = max(1, rpm)
            self.fill_rate = self.capacity / 60.0
            if self.tokens > self.capacity:
                self.tokens = self.capacity
            self.last = time.time()

    def take(self):
        while True:
            with self.lock:
                now = time.time()
                elapsed = now - self.last
                self.last = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
            time.sleep(0.02)

@dataclass
class PoolConfig:
    min_workers: int = 2
    max_workers: int = 32
    init_workers: int = 8
    rpm_init: int = 200
    rpm_min: int = 60
    rpm_max: int = 1000
    tpm_max: Optional[int] = None  # not strictly enforced here (estimates only)

class AdaptivePool:
    """Adaptive in-flight controller based on latency & errors."""
    def __init__(self, cfg: PoolConfig):
        self.cfg = cfg
        self.inflight_cap = cfg.init_workers
        self.err_429 = 0
        self.lat_hist: List[float] = []
        self.lock = threading.Lock()
        self.last_adjust = time.time()

    def on_result(self, latency: float, status_ok: bool, got_429: bool):
        with self.lock:
            self.lat_hist.append(latency)
            if got_429:
                self.err_429 += 1
            # keep history bounded
            if len(self.lat_hist) > 200:
                self.lat_hist = self.lat_hist[-200:]

    def maybe_adjust(self, bucket: TokenBucket):
        with self.lock:
            now = time.time()
            if now - self.last_adjust < 2.0:
                return
            self.last_adjust = now
            lat = (sum(self.lat_hist) / len(self.lat_hist)) if self.lat_hist else 0.5
            # 基本策略：如果 429 增长或延迟升高 -> 降低 in-flight & rpm；反之缓慢增加
            if self.err_429 > 0 or lat > 2.0:
                self.inflight_cap = max(self.cfg.min_workers, int(self.inflight_cap * 0.8))
                new_rpm = max(self.cfg.rpm_min, int(bucket.capacity * 0.8))
                bucket.set_rpm(new_rpm)
                self.err_429 = 0
            else:
                # 温和增加
                self.inflight_cap = min(self.cfg.max_workers, self.inflight_cap + 1)
                new_rpm = min(self.cfg.rpm_max, bucket.capacity + 20)
                bucket.set_rpm(new_rpm)

# ------------------ Scenes Loader ------------------
def load_scenes(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def build_context(scene_map: Dict[str, Any], row_idx: int, df: pd.DataFrame, max_chars: int = 160) -> str:
    if not scene_map:
        return ""
    # scene_map 约定: {"scenes": [{"rows":[start,end]}, ...]}
    # 或 05_segment_context.py 生成的简单结构：包含每个 scene 的行号列表
    scenes = scene_map.get("scenes") or scene_map
    # 找到包含 row_idx 的 scene
    def in_scene(s):
        rows = s.get("rows") or s.get("indices") or []
        if isinstance(rows, list):
            if rows and isinstance(rows[0], list):  # ranges
                for st, ed in rows:
                    if st <= row_idx <= ed:
                        return True
                return False
            return (row_idx in rows)
        if isinstance(rows, dict):
            st, ed = rows.get("start", 0), rows.get("end", 0)
            return st <= row_idx <= ed
        return False

    scene = None
    if isinstance(scenes, list):
        for s in scenes:
            if in_scene(s):
                scene = s
                break

    if not scene:
        return ""

    # 收集该 scene 中周边若干行的 RU/EN/speaker
    buf = []
    def pick(i):
        try:
            ru = str(df.iloc[i, 0]) if i < len(df) else ""
            en = str(df.iloc[i, 2]) if i < len(df) else ""
            sp = str(df.iloc[i, 1]) if i < len(df) else ""
            return f"{i}: [{sp}] RU: {ru} | EN: {en}"
        except Exception:
            return ""

    rows = scene.get("rows") or scene.get("indices") or []
    flat_rows: List[int] = []
    if isinstance(rows, list) and rows and isinstance(rows[0], list):
        for st, ed in rows:
            flat_rows.extend(list(range(st, ed + 1)))
    elif isinstance(rows, list):
        flat_rows = rows
    elif isinstance(rows, dict):
        st, ed = rows.get("start", 0), rows.get("end", 0)
        flat_rows = list(range(st, ed + 1))

    # 只拼接附近 ±6 行
    if row_idx in flat_rows:
        pos = flat_rows.index(row_idx)
        window = flat_rows[max(0, pos - 6): pos + 7]
    else:
        window = [row_idx]

    for i in window:
        line = pick(i)
        if line:
            buf.append(line)
        if sum(len(x) for x in buf) > max_chars:
            break
    return "\n".join(buf)

# ------------------ Helpers ------------------
def now_ts():
    return time.strftime("%H:%M:%S")

def eprint(*a, **k):
    print(*a, **k, file=sys.stderr, flush=True)

def load_settings(path: Path) -> Dict[str, Any]:
    # 支持 YAML，但不强依赖 pyyaml；用简陋解析或回退 json
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        # fallback json
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

def select_provider(args, settings):
    if args.provider and args.provider != "auto":
        return args.provider
    prov = settings.get("provider") or os.environ.get("PROVIDER")
    return prov or "deepseek"

def build_client(provider: str, settings: Dict[str, Any]):
    if OpenAI is None:
        raise RuntimeError("openai package not installed. pip install openai")
    llm = (settings.get("llm") or {})
    model_cfg = (settings.get("model") or {})
    if provider == "deepseek":
        ds = llm.get("deepseek") or {}
        api_key = ds.get("api_key") or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("SILICONFLOW_API_KEY")
        base_url = ds.get("base_url") or os.environ.get("DEEPSEEK_BASE_URL") or os.environ.get("SILICONFLOW_BASE_URL") or "https://api.siliconflow.cn"
        if not api_key:
            raise RuntimeError("Missing DeepSeek/SiliconFlow API key (settings or env).")
        client = OpenAI(api_key=api_key, base_url=base_url)
        model = (model_cfg.get("deepseek") or {}).get("name") or os.environ.get("DEEPSEEK_MODEL") or "deepseek-ai/DeepSeek-V3.2-Exp"
        rpm_cap = (settings.get("rate_limit") or {}).get("rpm") or 200
        return client, model, int(rpm_cap)
    elif provider == "openai":
        oa = llm.get("openai") or {}
        api_key = oa.get("api_key") or os.environ.get("OPENAI_API_KEY")
        base_url = oa.get("base_url") or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY (settings or env).")
        client = OpenAI(api_key=api_key, base_url=base_url)
        model = (model_cfg.get("openai") or {}).get("name") or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
        rpm_cap = (settings.get("rate_limit") or {}).get("rpm") or 200
        return client, model, int(rpm_cap)
    else:
        raise RuntimeError(f"Unknown provider: {provider}")

# ------------------ I/O ------------------
def read_excel(path: Path, sheet_index: Optional[int], sheet_name: Optional[str]) -> pd.DataFrame:
    if sheet_name is not None:
        df = pd.read_excel(path, sheet_name=sheet_name)
    elif sheet_index is not None:
        df = pd.read_excel(path, sheet_name=sheet_index)
    else:
        df = pd.read_excel(path)
    # 支持返回 dict（多表），取第一张
    if isinstance(df, dict):
        df = df[0] if 0 in df else list(df.values())[0]
    return df

def wal_append(path: Path, rec: Dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def ckpt_load(path: Path) -> Dict[int, str]:
    done = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(line)
                done[int(obj["row"])] = obj.get("out","")
            except Exception:
                pass
    return done

def ckpt_append(path: Path, row: int, out: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"row": row, "out": out}, ensure_ascii=False) + "\n")

# ------------------ Core translate ------------------
def call_chat(client, model: str, system_prompt: str, user_prompt: str) -> Tuple[str, float, bool]:
    t0 = time.time()
    got_429 = False
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role":"system","content":system_prompt},
                {"role":"user","content":user_prompt},
            ],
            temperature=0.2,
            top_p=1.0,
        )
        out = (resp.choices[0].message.content or "").strip()
        return out, time.time()-t0, False
    except Exception as e:
        s = str(e).lower()
        if "429" in s or "rate limit" in s:
            got_429 = True
        raise
    finally:
        pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True, help="Excel path")
    ap.add_argument("--sheet-index", type=int, default=0, help="Sheet index")
    ap.add_argument("--sheet-name", default=None, help="Sheet name (override index)")
    ap.add_argument("--target-lang", default="zh-CN", help="Target language tag (default zh-CN)")
    ap.add_argument("--settings", default="config/settings.local.yaml", help="YAML/JSON settings with provider/api_key/base_url/model")
    ap.add_argument("--provider", default="auto", choices=["auto","deepseek","openai"], help="Provider")
    ap.add_argument("--glossary", default="data/name_map.json", help="Glossary JSON path")
    ap.add_argument("--glossary-max", type=int, default=300, help="Max glossary items in prompt excerpt")
    ap.add_argument("--context-mode", default="scene", choices=["scene","none"], help="Context mode")
    ap.add_argument("--scenes", default="artifacts/scenes.json", help="Scenes json path")
    ap.add_argument("--row-range", default=None, help="e.g. 0:1000 (inclusive start:end)")
    ap.add_argument("--scene-range", default=None, help="e.g. 0:10 (scene index range, if using scenes)")
    ap.add_argument("--speaker", default=None, help="glob filter, e.g. student_* ; multiple split by ,")
    ap.add_argument("--retranslate", action="store_true", help="Overwrite col5 even if non-empty")
    ap.add_argument("--dry-run", action="store_true", help="Only print plan, not calling API")
    ap.add_argument("--show-lines", action="store_true", help="Print RU/EN/OUT streaming")
    ap.add_argument("--max-chars", type=int, default=160, help="Max context chars from scene")
    # concurrency & limits
    ap.add_argument("--workers", type=int, default=8, help="Initial workers")
    ap.add_argument("--min-workers", type=int, default=2)
    ap.add_argument("--max-workers", type=int, default=32)
    ap.add_argument("--rpm", type=int, default=200, help="Initial RPM")
    ap.add_argument("--rpm-min", type=int, default=60)
    ap.add_argument("--rpm-max", type=int, default=1000)
    ap.add_argument("--tpm-max", type=int, default=None)
    # persistence
    ap.add_argument("--autosave-every", type=int, default=300, help="Save to Excel every N rows translated")
    ap.add_argument("--autosave-seconds", type=int, default=90, help="Save to Excel every N seconds")
    ap.add_argument("--checkpoint-file", default="artifacts/ckpt.translate.jsonl")
    ap.add_argument("--wal-file", default="artifacts/translate.wal.jsonl")
    ap.add_argument("--wal-every", type=int, default=10, help="Append to WAL every N rows")
    ap.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    ap.add_argument("--out", default=None, help="Output path. Default: data/<ExcelName>.<lang>.llm.xlsx")

    args = ap.parse_args()

    excel_path = Path(args.excel)
    settings = load_settings(Path(args.settings))
    provider = select_provider(args, settings)
    client, model, rpm_cap_from_cfg = build_client(provider, settings)

    # rpm init
    rpm_init = args.rpm or rpm_cap_from_cfg
    rpm_min = args.rpm_min
    rpm_max = args.rpm_max

    # Load Excel
    df = read_excel(excel_path, args.sheet_index, args.sheet_name)
    if df.shape[1] < 5:
        # 确保有第5列
        missing = 5 - df.shape[1]
        for _ in range(missing):
            df[df.shape[1]] = ""
        # 重新命名列索引方便阅读（可选）
    # planning indices
    total = len(df)

    # row range
    row_mask = [True] * total
    if args.row_range:
        m = re.match(r"^\s*(\d+)\s*:\s*(\d+)\s*$", args.row_range)
        if not m:
            raise SystemExit(f"Bad --row-range: {args.row_range}")
        st, ed = int(m.group(1)), int(m.group(2))
        for i in range(total):
            row_mask[i] = (st <= i <= ed)

    # speaker filter
    if args.speaker:
        import fnmatch
        pats = [x.strip() for x in args.speaker.split(",") if x.strip()]
        def sp_ok(s):
            return any(fnmatch.fnmatch(s, p) for p in pats)
    else:
        def sp_ok(s): return True

    # resume support
    done_map = ckpt_load(Path(args.checkpoint_file)) if args.resume else {}
    # scene filter
    scene_map = load_scenes(Path(args.scenes)) if args.context_mode == "scene" else {}

    # Glossary
    gloss = None
    if _GLOSS is not None:
        try:
            gloss = _GLOSS.load(args.glossary, target_lang=args.target_lang)
        except Exception as e:
            eprint(f"[WARN] glossary load failed: {e}")
            gloss = None
    excerpt = ""
    if gloss is not None:
        try:
            excerpt = gloss.build_prompt_excerpt(max_items=args.glossary_max, max_chars=4000)
        except Exception:
            excerpt = ""

    # Output path
    if args.out:
        out_path = Path(args.out)
    else:
        out_name = f"{excel_path.stem}.{args.target_lang}.llm.xlsx"
        out_path = excel_path.parent / out_name

    # Build to-translate index list
    idxs: List[int] = []
    for i in range(total):
        if not row_mask[i]:
            continue
        sp = str(df.iloc[i, 1]) if i < total else ""
        if not sp_ok(sp):
            continue
        # col5 empty?
        col5 = str(df.iloc[i, 4]) if df.shape[1] >= 5 else ""
        if (not col5) or args.retranslate:
            idxs.append(i)

    to_translate = len(idxs)
    print(f"[CFG] provider={provider} rpm_init={rpm_init} tpm_max={args.tpm_max} workers={args.workers} min/max={args.min_workers}/{args.max_workers}")
    print(f"[PLAN] total={total} to_translate={to_translate}")

    if args.dry_run:
        print("[DRY] no API calls. Exiting.")
        return

    # Compose final system prompt
    system_prompt = BASE_SYSTEM_PROMPT
    if excerpt:
        system_prompt += "\n\nGLOSSARY (Longest-first, strict):\n" + excerpt

    # concurrency
    bucket = TokenBucket(rpm_init)
    pool_cfg = PoolConfig(min_workers=args.min_workers, max_workers=args.max_workers, init_workers=args.workers,
                          rpm_init=rpm_init, rpm_min=rpm_min, rpm_max=rpm_max, tpm_max=args.tpm_max)
    adapt = AdaptivePool(pool_cfg)

    q_in: "queue.Queue[int]" = queue.Queue()
    for i in idxs:
        q_in.put(i)

    q_out: "queue.Queue[Tuple[int, str, float, Optional[Exception]]]" = queue.Queue()

    stop_sig = {"stop": False}
    inflight = 0
    inflight_lock = threading.Lock()

    last_save_t = time.time()
    done_since_save = 0
    processed = 0

    def worker_loop():
        nonlocal inflight, processed
        while not stop_sig["stop"]:
            try:
                # 队列空则退出
                i = q_in.get(timeout=0.2)
            except queue.Empty:
                return
            # 自适应 in-flight 限制
            while True:
                with inflight_lock:
                    if inflight < adapt.inflight_cap:
                        inflight += 1
                        break
                time.sleep(0.01)
            try:
                bucket.take()
                ru = str(df.iloc[i, 0]) if i < total else ""
                sp = str(df.iloc[i, 1]) if i < total else ""
                en = str(df.iloc[i, 2]) if i < total else ""
                ctx = ""
                if args.context_mode == "scene":
                    try:
                        ctx = build_context(scene_map, i, df, max_chars=args.max_chars)
                    except Exception:
                        ctx = ""
                user_prompt = USER_PROMPT_TMPL.format(speaker=sp, row_id=i, ru=ru, en=en, ctx=ctx)
                t0 = time.time()
                out_text, lat, got429 = "", 0.0, False
                err = None
                try:
                    out_text, lat, got429 = call_chat(client, model, system_prompt, user_prompt)
                    # enforce glossary
                    if gloss is not None:
                        out_text = gloss.enforce(out_text)
                    # 清理尾部引号/多余空行
                    out_text = out_text.strip().strip('"').strip()
                except Exception as ex:
                    lat = time.time()-t0
                    err = ex
                finally:
                    adapt.on_result(lat, err is None, got429)
                q_out.put((i, out_text, lat, err))
            finally:
                with inflight_lock:
                    inflight -= 1

    # 启动固定数量线程（inflight_cap 由 adapt 控制实际并发）
    threads = []
    n_threads = args.max_workers  # 线程上限，实际 in-flight 受 adapt 管
    for _ in range(n_threads):
        t = threading.Thread(target=worker_loop, daemon=True)
        t.start()
        threads.append(t)

    # main loop: collect and save
    wal_path = Path(args.wal_file)
    ckpt_path = Path(args.checkpoint_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 应用 resume：先把已完成写回 df 第5列
    if done_map:
        for r, text in done_map.items():
            if 0 <= r < total:
                df.iat[r, 4] = text

    last_adjust_t = time.time()
    wal_batch = 0

    while True:
        try:
            i, out_text, lat, err = q_out.get(timeout=0.2)
        except queue.Empty:
            # 调整并发节流
            adapt.maybe_adjust(bucket)
            # 结束判定
            alive = any(t.is_alive() for t in threads)
            if not alive and q_out.empty():
                break
            # 周期落盘（按秒）
            if time.time() - last_save_t >= args.autosave_seconds:
                df.to_excel(out_path, index=False)
                last_save_t = time.time()
                print(f"[AUTO] saved -> {out_path}")
            continue

        processed += 1
        if err:
            eprint(f"[ERR ] row={i} {err}")
        else:
            df.iat[i, 4] = out_text  # 写入第5列
            done_since_save += 1
            if args.show_lines:
                ru = str(df.iloc[i, 0]) if i < total else ""
                en = str(df.iloc[i, 2]) if i < total else ""
                print(f"[{now_ts()}] RU: {ru}")
                print(f"[{now_ts()}] EN: {en}")
                print(f"[{now_ts()}] OUT: {out_text}")
            # WAL & checkpoint
            if wal_batch % max(1, args.wal_every) == 0:
                wal_append(wal_path, {"row": i, "out": out_text, "ts": time.time()})
            ckpt_append(ckpt_path, i, out_text)

        # autosave by count
        if done_since_save >= args.autosave_every:
            df.to_excel(out_path, index=False)
            last_save_t = time.time()
            done_since_save = 0
            print(f"[AUTO] saved -> {out_path}")

        # 定期自调
        if time.time() - last_adjust_t >= 2.0:
            adapt.maybe_adjust(bucket)
            last_adjust_t = time.time()

        wal_batch += 1

    # 最终保存
    df.to_excel(out_path, index=False)
    print(f"[OK] Done. Output -> {out_path}")

if __name__ == "__main__":
    main()
