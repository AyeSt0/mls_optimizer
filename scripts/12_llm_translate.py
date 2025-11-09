
import argparse, os, time, json, re, threading, queue, math, pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List

# OpenAI-compatible client (works for OpenAI or SiliconFlow DeepSeek gateway)
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

from glossary_utils import load_glossary, inject_glossary_prompt, unguard_placeholders

PROMPT_RULES = """You are a senior localization writer for an ADULT visual novel set in Sunville (阳光镇),
mostly inside a COLLEGE（学院）. Output MUST be natural, colloquial Chinese for players.

GENERAL:
- Base literal meaning on EN; use RU for mood & sensual nuance when helpful.
- STRICTLY apply the glossary with LONGEST MATCH FIRST; never contradict it.
- Preserve placeholders/tags exactly: [like_this], {vars}, {{vars}}, <tags>.
- Keep any EXISTING CHINESE and placeholders in the seed text UNCHANGED; only translate/complete the English parts around them.
- Keep brand/product names in Latin (Patreon, Instagram, Lovense).
- Use colloquial “你”; avoid stiff, bookish phrasing.
- You MAY restructure English syntax for natural Chinese（意合优先）; merge or split clauses as needed.
- Use Chinese punctuation and spoken word order; avoid copying EN period-per-fragment habit.
- Output ONLY the final Chinese line (no quotes, no extra text).

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
(or otherwise looks like a map/room/UI location), translate as a PLACE NAME, not a school subject:
- SUBJECT + CLASS → “X教室”：Computer Class→计算机教室; Arts Class→美术教室
- Lone SUBJECT words (BIOLOGY/PHYSICS/ENGLISH/GEOGRAPHY/ALGEBRA) in this context → “X教室”
- ...’S OFFICE:
  - DOCTOR’S OFFICE → 医务室
  - STEWARD’S OFFICE → 管理员办公室
  - (others) “某某办公室”
- LOCKER (singular) → 储物柜区; LOCKER ROOMS (plural) → 更衣室
- GIRL’S/BOY’S CHANGING ROOM → 女生/男生更衣室
- BOYS/GIRLS TOILET(S) → 男厕 / 女厕（或“洗手间”，全局统一）
- GYM → 体育馆; POOL → 泳池; LIBRARY → 图书馆; ASSEMBLY HALL → 学院礼堂
- COLLEGE ENTRANCE → 学院正门
- TOWN → 镇上（地图/导航标签时更自然）

SPEAKER-AWARE TONE:
- Principal/Teacher/Librarian (incl. *_t thoughts) → 正式、克制、不搔首弄姿。
- System/Operator/Post/Help/Hotel_staff/Secretary/Policeman → 简明 UI/服务语气。
- Punk/Whore/Stripper/Showman → 更大胆、街头感、可直白但不低俗堆砌。
- Students/Girls/Actresses/Models → 年轻、随性、轻松调情；有场景时可适度露骨。

OBJECTIVES / TASK HINTS（非对话）:
If the English is a short imperative objective (e.g., “Go to Sean’s. Meet his mother. Talk to Sean.”),
render as a natural Chinese checklist/flow, not literal one-sentence-per-dot:
- Prefer: “前往肖恩家、见见他妈妈、和肖恩聊聊。”
- Or: “去趟肖恩家，先见他妈妈，再跟肖恩聊聊。”
Avoid stiff “认识他妈妈”; prefer “见见他妈妈/见肖恩的妈妈”。

DIALOGUE（大多数行）:
If it reads like human speech, treat as dialogue:
- 保持口语节奏与情色张力，不要医学化或回避露骨细节。
- 叹息/呻吟（“嗯…/哈啊…/啊…”）自然不过度。

DISAMBIGUATION HEURISTICS:
- ALL-CAPS 1–4 nouns with campus/town semantics + speaker=string → 按地点规则翻译。
- 多段“Go to/Meet/Talk/Find…” → 视作目标提示，使用自然中文清单/顺序句式。
- 其他 → 作为对话/普通 UI 本地化。

FORMAT:
- Output only the final Chinese line (no quotes or extra markings).
"""

def _now():
    return datetime.now().strftime("%H:%M:%S")

def load_settings(path="config/settings.local.yaml") -> Dict[str, Any]:
    try:
        import yaml
    except Exception:
        print("[WARN] PyYAML not installed, env-only mode")
        return {}
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def build_client(provider: str, settings: Dict[str, Any]):
    """
    Build OpenAI-compatible client for 'deepseek' (SiliconFlow) or 'openai'
    """
    if OpenAI is None:
        raise RuntimeError("openai package not installed. pip install openai")

    prov = provider or (settings.get("provider") or "deepseek")

    if prov == "deepseek":
        ds = ((settings.get("llm") or {}).get("deepseek") or {})
        api_key = ds.get("api_key") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("SILICONFLOW_API_KEY")
        base_url = ds.get("base_url") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.siliconflow.cn"
        model = ((settings.get("model") or {}).get("deepseek") or {}).get("name") or os.getenv("DEEPSEEK_MODEL") or "deepseek-ai/DeepSeek-V3.2-Exp"
        if not api_key:
            raise RuntimeError("Missing DeepSeek/SiliconFlow API key (settings or env).")
        client = OpenAI(api_key=api_key, base_url=base_url)
        rpm_init = ((settings.get("rate_limit") or {}).get("rpm") or 200)
        return client, model, rpm_init

    elif prov == "openai":
        oa = ((settings.get("llm") or {}).get("openai") or {})
        api_key = oa.get("api_key") or os.getenv("OPENAI_API_KEY")
        base_url = oa.get("base_url") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        model = ((settings.get("model") or {}).get("openai") or {}).get("name") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY (settings or env).")
        client = OpenAI(api_key=api_key, base_url=base_url)
        rpm_init = ((settings.get("rate_limit") or {}).get("rpm") or 200)
        return client, model, rpm_init

    else:
        raise RuntimeError(f"Unknown provider: {prov}")

def want_row(idx: int, speaker: str, row_range: Optional[Tuple[int,int]], speaker_glob: Optional[str]) -> bool:
    if row_range:
        a,b = row_range
        if idx < a or idx > b:
            return False
    if speaker_glob:
        # simple glob: '*' suffix/prefix or contains
        pat = speaker_glob.replace("*", "")
        if "*" in speaker_glob:
            if speaker_glob.startswith("*") and speaker_glob.endswith("*"):
                return pat in speaker
            elif speaker_glob.startswith("*"):
                return speaker.endswith(pat)
            elif speaker_glob.endswith("*"):
                return speaker.startswith(pat)
        else:
            return speaker == speaker_glob
    return True

def make_messages(glossary_pairs: List, target_lang: str, speaker: str, seed: str, en: str, ru: str) -> List[Dict[str,str]]:
    gblock = inject_glossary_prompt(glossary_pairs, 300)
    sys_prompt = PROMPT_RULES + "\n" + gblock + f"\nTarget language: {target_lang}\n"
    user = f"SPEAKER: {speaker}\nSEED (keep existing Chinese/holders unchanged): {seed}\nEN: {en}\nRU: {ru or ''}\n\nReturn only the final Chinese line."
    return [
        {"role":"system", "content": sys_prompt},
        {"role":"user", "content": user}
    ]

def translate_batch(client, model, batch: List[Tuple[int, Dict[str, Any]]], args):
    out = []
    for idx, row in batch:
        try:
            msgs = make_messages(
                args._pairs, args.target_lang, str(row["speaker"] or ""),
                str(row["seed"] or ""), str(row["en"] or ""), str(row["ru"] or "")
            )
            if args.dry_run:
                cn = row["seed"]
            else:
                resp = client.chat.completions.create(
                    model=model,
                    messages=msgs,
                    temperature=0.3,
                )
                cn = resp.choices[0].message.content.strip()
            out.append((idx, cn))
        except Exception as e:
            out.append((idx, f"[ERROR:{type(e).__name__}] {e}"))
    return out

class RateGate:
    def __init__(self, rpm:int):
        self.rpm = max(10, rpm)
        self.period = 60.0/self.rpm
        self._lock = threading.Lock()
        self._t = 0.0
    def wait(self):
        with self._lock:
            now = time.time()
            dt = self.period - (now - self._t)
            if dt > 0:
                time.sleep(dt)
            self._t = time.time()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet-index", type=int, default=0)
    ap.add_argument("--target-lang", default="zh-CN")
    ap.add_argument("--settings", default="config/settings.local.yaml")
    ap.add_argument("--provider", default=None, help="deepseek|openai (default from settings)")
    ap.add_argument("--glossary", default=None)
    ap.add_argument("--row-range", default=None, help="e.g., 1800-2100")
    ap.add_argument("--speaker-filter", default=None, help="supports * prefix/suffix/both")
    ap.add_argument("--override", action="store_true", help="override existing col4 (re-translate)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--autosave-every", type=int, default=300)
    ap.add_argument("--autosave-seconds", type=int, default=90)
    ap.add_argument("--wal-file", default="artifacts/translate.wal.jsonl")
    ap.add_argument("--checkpoint-file", default="artifacts/ckpt.translate.jsonl")
    ap.add_argument("--show-lines", action="store_true")
    ap.add_argument("--rpm", type=int, default=None)
    ap.add_argument("--tpm-max", type=int, default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--min-workers", type=int, default=2)
    ap.add_argument("--max-workers", type=int, default=32)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    settings = load_settings(args.settings)
    client, model, rpm_init = build_client(args.provider, settings)
    if args.rpm is not None:
        rpm_init = args.rpm
    print(f"[CFG] provider={settings.get('provider', args.provider)} rpm_init={rpm_init} workers={args.workers} min/max={args.min_workers}/{args.max_workers}")

    pairs = load_glossary(args.glossary) if args.glossary else []
    args._pairs = pairs  # stash

    df = pd.read_excel(args.excel, sheet_name=args.sheet_index)
    while df.shape[1] < 5:
        df[f"col{df.shape[1]}"] = ""
    col0, col1, col2, col3, col4 = df.columns[:5]

    total = len(df)
    # choose rows
    row_rng = None
    if args.row_range:
        m = re.match(r"(\d+)-(\d+)", args.row_range)
        if m:
            row_rng = (int(m.group(1)), int(m.group(2)))

    todo: List[Tuple[int, Dict[str, Any]]] = []
    for i in range(total):
        ru = str(df.iloc[i,0]) if not pd.isna(df.iloc[i,0]) else ""
        en = str(df.iloc[i,1]) if not pd.isna(df.iloc[i,1]) else ""
        speaker = str(df.iloc[i,2]) if not pd.isna(df.iloc[i,2]) else ""
        seed = str(df.iloc[i,4]) if not pd.isna(df.iloc[i,4]) else ""  # use col4 as seed
        if not want_row(i, speaker, row_rng, args.speaker_filter):
            continue
        if (not args.override) and seed.strip():
            # skip already translated
            continue
        todo.append((i, {"ru":ru, "en":en, "speaker":speaker, "seed":seed}))

    to_translate = len(todo)
    print(f"[PLAN] total={total} to_translate={to_translate}")
    if to_translate == 0 and not args.dry_run:
        # if nothing to do, still write output copy for traceability
        outp = args.out or args.excel.replace(".xlsx", f".{args.target_lang}.llm.xlsx")
        df.to_excel(outp, index=False)
        print(f"[OK] Done. Output -> {outp}")
        return

    # rate gate
    gate = RateGate(rpm_init)
    lock = threading.Lock()
    idxq = queue.Queue()
    for item in todo:
        idxq.put(item)

    # WAL & autosave
    last_save_t = time.time()
    wal_path = args.wal_file
    wal_fp = open(wal_path, "a", encoding="utf-8")

    def save_progress():
        nonlocal df, last_save_t
        outp = args.out or args.excel.replace(".xlsx", f".{args.target_lang}.llm.xlsx")
        df.to_excel(outp, index=False)
        last_save_t = time.time()
        print(f"[AUTOSAVE] -> {outp}")

    # worker
    def worker_loop(tid:int):
        nonlocal df
        while True:
            try:
                item = idxq.get_nowait()
            except queue.Empty:
                return
            i, row = item
            gate.wait()
            res = translate_batch(client, model, [(i,row)], args)[0]
            with lock:
                df.iloc[res[0], 4] = unguard_placeholders(res[1])
                # WAL line
                wal_fp.write(json.dumps({"row":res[0], "out":res[1], "t": time.time()})+"\n")
                wal_fp.flush()
                if args.show_lines:
                    ru = row["ru"]; en = row["en"]
                    print(f"[{_now()}] RU: {ru}")
                    print(f"[{_now()}] EN: {en}")
                    print(f"[{_now()}] OUT: {res[1]}\n")
            # periodic autosave
            if args.autosave_every and (todo.index(item)+1) % args.autosave_every == 0:
                save_progress()
            if args.autosave_seconds and (time.time() - last_save_t) > args.autosave_seconds:
                save_progress()

    # Start workers (fixed for stability; you can scale dynamically in future)
    n_workers = max(args.min_workers, min(args.workers, args.max_workers))
    threads = []
    for t in range(n_workers):
        th = threading.Thread(target=worker_loop, args=(t,), daemon=True)
        th.start()
        threads.append(th)
    for th in threads:
        th.join()

    # final save
    save_progress()
    wal_fp.close()
    print("[OK] Finished.")

if __name__ == "__main__":
    main()
