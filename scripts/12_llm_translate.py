# -*- coding: utf-8 -*-
"""
12_llm_translate.py
以【第4列】为源，进行本地化翻译，写入【第5列】。
特点：
- 读取 config/settings.local.yaml，支持 provider: deepseek/openai（OpenAI兼容协议，DeepSeek 走 SiliconFlow）
- 伸缩线程池 + 自适应 RPM/TPM（遇 429/超时 降并发、通过延迟/成功率 逐步升并发）
- WAL/断点续： --wal-file JSONL 持续写入；--checkpoint-file 记录已完成行，--resume 自动跳过
- 支持：覆盖重译/行号范围/Speaker 过滤(*通配)/仅预览(show-lines)/sheet-index|sheet-name
- 注入 name_map（最长匹配TOPK术语）到 Prompt；翻译后仍不改已有中文/占位符（由 20 预占位）
- 成人/学院语境强 Prompt（地点规则、对话/目标语气、Objective指引）
- 输出另存 *.llm.xlsx（不改第4列）

使用示例：
python -u -m scripts.12_llm_translate --excel data/MLS Chinese.xlsx --target-lang zh-CN --glossary data/name_map.json --sheet-index 0 --show-lines --resume
"""

import argparse, asyncio, concurrent.futures, json, os, re, sys, time, threading
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import yaml

# 列索引（0-based）
RU_COL = 0
SPEAKER_COL = 1
EN_COL = 2
SRC_COL = 3     # 第4列：20 步生成的“带中文守护的英文底稿”
DST_COL = 4     # 第5列：LLM 输出

# 默认限速
DEFAULT_RPM = 200
DEFAULT_MIN_WORKERS = 2
DEFAULT_MAX_WORKERS = 32

# —— 读 settings.local.yaml —— #
def load_settings(path: str) -> Dict[str,Any]:
    if not os.path.exists(path): return {}
    with open(path,'r',encoding='utf-8') as f:
        return yaml.safe_load(f) or {}

def build_client(provider: str, cfg: Dict[str,Any]):
    """
    返回 (client, model_name, rpm_cap, tpm_cap)
    使用 OpenAI 兼容 SDK。DeepSeek通过 SiliconFlow base_url。
    """
    from openai import OpenAI
    if provider == "deepseek":
        ds = (((cfg.get("llm") or {}).get("deepseek")) or {})
        key = ds.get("api_key") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("SILICONFLOW_API_KEY")
        base= ds.get("base_url") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.siliconflow.cn"
        model = ((cfg.get("model") or {}).get("deepseek") or {}).get("name") or "deepseek-ai/DeepSeek-V3.2-Exp"
        if not key:
            raise RuntimeError("Missing DeepSeek/SiliconFlow API key (settings.local.yaml or env DEEPSEEK_API_KEY/SILICONFLOW_API_KEY).")
        client = OpenAI(api_key=key, base_url=f"{base}/v1")
        rpm_cap = (cfg.get("rate_limit") or {}).get("rpm", DEFAULT_RPM)
        tpm_cap = (cfg.get("rate_limit") or {}).get("tpm", None)
        return client, model, rpm_cap, tpm_cap
    else:
        oa = (((cfg.get("llm") or {}).get("openai")) or {})
        key = oa.get("api_key") or os.getenv("OPENAI_API_KEY")
        base= oa.get("base_url") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        model = ((cfg.get("model") or {}).get("openai") or {}).get("name") or "gpt-4o-mini"
        if not key:
            raise RuntimeError("Missing OPENAI_API_KEY (settings.local.yaml or env).")
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url=base)
        rpm_cap = (cfg.get("rate_limit") or {}).get("rpm", DEFAULT_RPM)
        tpm_cap = (cfg.get("rate_limit") or {}).get("tpm", None)
        return client, model, rpm_cap, tpm_cap

# —— 术语注入（只注入，不后替；后替由21执行） —— #
def load_glossary(glossary_path: Optional[str]) -> Dict[str,str]:
    if not glossary_path or not os.path.exists(glossary_path): return {}
    with open(glossary_path,'r',encoding='utf-8') as f:
        data=json.load(f)
    flat={}
    def walk(n):
        if isinstance(n,dict):
            if set(n.keys()) & {"en_to_zh","ru_to_zh","map","terms","glossary"}:
                for k in n: walk(n[k])
            else:
                for k,v in n.items():
                    if isinstance(v,str) and k:
                        flat[str(k)]=v
                    elif isinstance(v,dict) and "zh" in v and k:
                        flat[str(k)]=str(v["zh"])
        elif isinstance(n,list):
            for it in n: walk(it)
    walk(data)
    return {k:v for k,v in flat.items() if v and str(k)!=str(v)}

def longest_match_topk(glossary: Dict[str,str], text: str, k: int=300) -> List[Tuple[str,str]]:
    if not text: return []
    # 简单地以长度排序后筛选出现过的
    items=sorted(glossary.items(), key=lambda kv: len(kv[0]), reverse=True)
    hits=[]
    t=text
    for src,dst in items:
        if len(hits)>=k: break
        if src in t:
            hits.append((src,dst))
    return hits

# —— 场景上下文（可选） —— #
def load_scenes(path="artifacts/scenes.json") -> Dict[str,Any]:
    if not os.path.exists(path): return {}
    with open(path,'r',encoding='utf-8') as f:
        return json.load(f) or {}

def build_context(df: pd.DataFrame, idx: int, scenes: Dict[str,Any]) -> str:
    # 简化：若有 scenes，按覆盖范围找到 scene 内的若干行拼 EN/RU/SRC 信息。
    # 你之前的 05 已经写入 scenes.json 的 covered rows；这里做一个温和上下文拼接即可。
    return ""  # 保持轻量，主要靠第4列守护+Prompt 规则

# —— Prompt —— #
PINNED_WORLD = """You are a senior localization writer for an ADULT visual novel set in Sunville (阳光镇), mostly inside a COLLEGE (学院). Output MUST be natural, colloquial Chinese for players.

GENERAL:
- Base literal meaning on EN; use RU for mood & sensual nuance when helpful.
- STRICTLY apply the glossary with LONGEST MATCH FIRST; never contradict it.
- Preserve placeholders/tags exactly: [like_this], {vars}, {{vars}}, <tags>.
- Keep brand/product names in Latin (Patreon, Instagram, Lovense).
- Use colloquial “你”; avoid stiff, bookish phrasing.
- YOU MAY restructure English syntax for natural Chinese; merge or split clauses as needed.
- Use Chinese punctuation and spoken word order; do NOT copy EN period-per-fragment habit.
- DO NOT alter any Chinese text already present in the source. Only translate the non-Chinese parts around it.
- Output ONLY the final Chinese line (no quotes or explanations).

WORLD TERMS (PINNED):
- Sunville → 阳光镇
- College → 学院
- Principal → 院长
- Steward → 管理员
- Doctor’s Office → 医务室
- Locker Rooms → 更衣室
- College Entrance → 学院正门

CAMPUS & TOWN LOCATION RULES (CRITICAL for speaker=string/map labels):
- SUBJECT + CLASS → “X教室”：Computer Class→计算机教室; Arts Class→美术教室
- Lone SUBJECT words (BIOLOGY/PHYSICS/ENGLISH/GEOGRAPHY/ALGEBRA) → “X教室”
- XX’S OFFICE: Doctor’s Office→医务室; Steward’s Office→管理员办公室; others→“某某办公室”
- LOCKER (sing.) → 储物柜区; LOCKER ROOMS (pl.) → 更衣室
- GIRL’S/BOY’S CHANGING ROOM → 女生/男生更衣室
- BOYS/GIRLS TOILET(S) → 男厕/女厕（全局一致）
- GYM → 体育馆; POOL → 泳池; LIBRARY → 图书馆; ASSEMBLY HALL → 学院礼堂
- COLLEGE ENTRANCE → 学院正门
- Map/room/UI labels should be concise place names, not course subjects.

SPEAKER-AWARE TONE:
- Principal/Teacher/Librarian (incl. *_t thoughts) → formal, calm; no slang.
- System/Operator/Post/Hotel_staff/Secretary/Policeman → concise UI/service tone.
- Punk/Whore/Stripper/Showman → bolder, street tone, explicit but not gratuitous.
- Students/Girls/Actresses/Models → youthful, casual, flirty; explicit when needed.

OBJECTIVES (short imperative sequences):
- Render as a natural checklist/flow, e.g., “去趟肖恩家，先见见他妈妈，再跟肖恩聊聊。” NOT one dot per sentence.
"""

def make_messages(speaker: str, ru: str, en: str, src4: str, glossary_items: List[Tuple[str,str]], target_lang: str):
    glossary_lines = []
    for s,d in glossary_items[:300]:
        glossary_lines.append(f"- {s} → {d}")
    glossary_block = "\n".join(glossary_lines) if glossary_lines else "（无特别术语）"

    user_block = f"""SPEAKER: {speaker or 'unknown'}
TARGET_LANG: {target_lang}

SOURCE (Use this as main content. It already contains protected Chinese segments and placeholders you MUST keep untouched):
{src4 or ''}

REFERENCE EN (literal meaning):
{en or ''}

REFERENCE RU (mood & nuance):
{ru or ''}

GLOSSARY (apply LONGEST MATCH FIRST; do not contradict):
{glossary_block}
"""
    return [
        {"role":"system","content":PINNED_WORLD},
        {"role":"user","content":user_block.strip()}
    ]

# —— 并发与速率控制（简化实现，稳定优先） —— #
class TokenBucket:
    def __init__(self, rpm:int):
        self.lock = threading.Lock()
        self.rpm = max(1,rpm)
        self.tokens = self.rpm
        self.last = time.time()
    def take(self):
        while True:
            with self.lock:
                now=time.time()
                elapsed=now-self.last
                refill = elapsed * (self.rpm/60.0)
                if refill>=1:
                    self.tokens = min(self.rpm, self.tokens + int(refill))
                    self.last = now
                if self.tokens>0:
                    self.tokens -=1
                    return
            time.sleep(0.05)
    def set_rpm(self, rpm:int):
        with self.lock:
            self.rpm = max(1,rpm)
            self.tokens = min(self.tokens, self.rpm)

def parse_range_spec(spec: Optional[str], n:int) -> Tuple[int,int]:
    # "start:end" 1-based, inclusive；支持单值"100"；为空则全量
    if not spec: return 1, n
    if ":" in spec:
        a,b=spec.split(":",1)
        a=int(a) if a.strip() else 1
        b=int(b) if b.strip() else n
        return max(1,a), min(n,b)
    else:
        i=int(spec); return i,i

def match_speaker(sp: str, pattern: Optional[str]) -> bool:
    if not pattern: return True
    # 简单 glob：* 通配
    pat = "^"+re.escape(pattern).replace(r"\*", ".*")+"$"
    return re.match(pat, sp or "", flags=re.IGNORECASE) is not None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet-name")
    ap.add_argument("--sheet-index", type=int, default=0)
    ap.add_argument("--target-lang", default="zh-CN")
    ap.add_argument("--settings", default="config/settings.local.yaml")
    ap.add_argument("--provider", choices=["deepseek","openai"], default=None)
    ap.add_argument("--glossary", default=None)

    ap.add_argument("--rpm", type=int, default=None)
    ap.add_argument("--tpm-max", type=int, default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--min-workers", type=int, default=2)
    ap.add_argument("--max-workers", type=int, default=32)

    ap.add_argument("--autosave-every", type=int, default=300)
    ap.add_argument("--autosave-seconds", type=int, default=90)
    ap.add_argument("--checkpoint-file", default="artifacts/ckpt.translate.jsonl")
    ap.add_argument("--wal-file", default="artifacts/translate.wal.jsonl")

    ap.add_argument("--overwrite", action="store_true", help="覆盖已有第5列译文（重译）")
    ap.add_argument("--row-range", default=None, help="行号范围 1-based，如 100:500 或 120")
    ap.add_argument("--speaker-like", default=None, help="Speaker 过滤，支持 * 通配")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show-lines", action="store_true")

    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    df = pd.read_excel(args.excel, sheet_name=args.sheet_name if args.sheet_name else args.sheet_index)
    # 确保第5列存在
    while df.shape[1] < DST_COL+1:
        df.insert(df.shape[1], f"col{df.shape[1]+1}", "")

    n = len(df)
    start,end = parse_range_spec(args.row_range, n)

    # 设置/客户端
    cfg = load_settings(args.settings)
    provider = args.provider or (cfg.get("provider") or "deepseek")
    client, model, rpm_cap, tpm_cap = build_client(provider, cfg)
    if args.rpm: rpm_cap = args.rpm
    if args.tpm_max: tpm_cap = args.tpm_max

    glossary = load_glossary(args.glossary)

    # 输出路径
    base,ext = os.path.splitext(args.excel)
    out = args.out or f"{base}.llm.xlsx"

    # WAL/断点续
    done_rows=set()
    if os.path.exists(args.checkpoint_file):
        with open(args.checkpoint_file,'r',encoding='utf-8') as f:
            for line in f:
                try:
                    obj=json.loads(line)
                    if obj.get("ok") and isinstance(obj.get("row"), int):
                        done_rows.add(obj["row"])
                except: pass

    wal_fp = open(args.wal_file,'a',encoding='utf-8')

    # 速率/并发
    bucket = TokenBucket(rpm_cap or DEFAULT_RPM)
    cur_workers = max(args.min_workers, min(args.workers, args.max_workers))
    failures=0; successes=0; last_adjust=time.time()

    # 自动保存
    last_save_time=0
    def autosave():
        nonlocal last_save_time
        now=time.time()
        if (now-last_save_time)>=args.autosave_seconds:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            df.to_excel(out, index=False)
            last_save_time=now

    # 发送请求（同步，在线程中调用）
    def call_one(idx:int) -> Tuple[int,str,bool,str]:
        nonlocal failures,successes
        ru = df.iat[idx, RU_COL] if df.shape[1]>RU_COL else ""
        en = df.iat[idx, EN_COL] if df.shape[1]>EN_COL else ""
        sp = df.iat[idx, SPEAKER_COL] if df.shape[1]>SPEAKER_COL else ""
        src4 = df.iat[idx, SRC_COL] if df.shape[1]>SRC_COL else ""
        src_cn = df.iat[idx, DST_COL] if df.shape[1]>DST_COL else ""

        if (not args.overwrite) and isinstance(src_cn,str) and src_cn.strip():
            return idx, src_cn, True, "skip_nonempty"

        if not match_speaker(sp, args.speaker_like):
            return idx, src_cn, True, "skip_speaker"

        # 只处理范围内
        if not (start-1 <= idx <= end-1):
            return idx, src_cn, True, "skip_range"

        # 速率令牌
        bucket.take()

        # 注入术语TOPK（从第4列/EN中粗选）
        sample_text = (src4 or "") + "\n" + (en or "")
        terms = longest_match_topk(glossary, sample_text, 300)

        messages = make_messages(str(sp or ""), str(ru or ""), str(en or ""), str(src4 or ""), terms, args.target_lang)

        t0=time.time()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3,
            )
            out_text = resp.choices[0].message.content.strip()
            latency = time.time()-t0
            successes += 1
            return idx, out_text, True, f"ok:{latency:.2f}s"
        except Exception as e:
            failures += 1
            return idx, str(e), False, "error"

    # 任务队列
    indices = list(range(n))
    # 先根据 resume/wal 跳过已完成行
    if done_rows:
        indices = [i for i in indices if (i+1) not in done_rows]

    # 主循环：伸缩线程池
    q = []
    results=[]
    lock = threading.Lock()

    def submit_batch(exe, batch):
        futs=[]
        for i in batch:
            fut = exe.submit(call_one, i)
            futs.append(fut)
        return futs

    with concurrent.futures.ThreadPoolExecutor(max_workers=cur_workers) as exe, open(args.checkpoint_file,'a',encoding='utf-8') as ck:
        pending=[]
        ptr=0
        while True:
            # 动态补任务
            while len(pending)<cur_workers and ptr < len(indices):
                pending.append(exe.submit(call_one, indices[ptr]))
                ptr+=1

            if not pending:
                break

            done, pending = concurrent.futures.wait(pending, timeout=0.2, return_when=concurrent.futures.FIRST_COMPLETED)

            for fut in done:
                idx, payload, ok, tag = fut.result()
                if ok and not args.dry_run:
                    df.iat[idx, DST_COL] = payload
                # WAL
                wal_obj = {"row": idx+1, "ok": ok, "tag": tag}
                if ok: wal_obj["out"] = payload
                else:  wal_obj["err"] = payload
                wal_fp.write(json.dumps(wal_obj, ensure_ascii=False) + "\n")
                wal_fp.flush()

                # CKPT
                if ok:
                    ck.write(json.dumps({"row": idx+1, "ok": True}, ensure_ascii=False)+"\n")
                    ck.flush()

                if args.show_lines:
                    ru = df.iat[idx, RU_COL] if df.shape[1]>RU_COL else ""
                    en = df.iat[idx, EN_COL] if df.shape[1]>EN_COL else ""
                    sp = df.iat[idx, SPEAKER_COL] if df.shape[1]>SPEAKER_COL else ""
                    print(f"[{time.strftime('%H:%M:%S')}] RU: {str(ru)[:120]}")
                    print(f"[{time.strftime('%H:%M:%S')}] EN: {str(en)[:120]}")
                    print(f"[{time.strftime('%H:%M:%S')}] OUT: {str(payload)[:120]}")
                    print(f"[SEND] row={idx+1} speaker={sp}")

                autosave()

            # 自适应并发（每2秒评估）
            now=time.time()
            if now - last_adjust >= 2.0:
                last_adjust = now
                err_rate = failures / max(1,(successes+failures))
                # 简单策略：高错误/疑似限流 -> 降并发；反之缓慢升
                if err_rate >= 0.05 and cur_workers > args.min_workers:
                    cur_workers = max(args.min_workers, cur_workers-1)
                elif err_rate < 0.02 and cur_workers < args.max_workers:
                    cur_workers = min(args.max_workers, cur_workers+1)
                # RPM 微调：错误高时按需降一档
                if err_rate >= 0.05 and bucket.rpm > 60:
                    bucket.set_rpm(bucket.rpm - 20)
                elif err_rate < 0.02 and bucket.rpm < (args.rpm or DEFAULT_RPM):
                    bucket.set_rpm(min((args.rpm or DEFAULT_RPM), bucket.rpm + 20))
                print(f"[PROGRESS] i={ptr}/{len(indices)} workers~{cur_workers} rpm~{bucket.rpm} ok={successes} err={failures}")

    # 最终保存
    if not args.dry_run:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        df.to_excel(out, index=False)
        print(f"[OK] Done. Output -> {out}")
    else:
        print("[DRY-RUN] Done.")
    return 0

if __name__=="__main__":
    sys.exit(main())
