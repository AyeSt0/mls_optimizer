
import os, sys, time, json, math, argparse, threading, fnmatch
from typing import Optional, Dict, Any, List, Set
import pandas as pd

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore

def build_argparser():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True, help="Input Excel file")
    ap.add_argument("--sheet-index", type=int, default=0, help="Sheet index (default 0)")
    ap.add_argument("--sheet-name", type=str, default=None, help="Sheet name (override index)")
    ap.add_argument("--target-lang", type=str, default="zh-CN", help="Target language code")

    ap.add_argument("--settings", type=str, default="config/settings.local.yaml", help="Settings YAML path")
    ap.add_argument("--provider", type=str, choices=["deepseek","openai"], default=None, help="Provider override")
    ap.add_argument("--glossary", type=str, default=None, help="Glossary name_map.json")

    ap.add_argument("--autosave-every", type=int, default=200, help="Autosave every N rows")
    ap.add_argument("--autosave-seconds", type=int, default=120, help="Autosave every N seconds")
    ap.add_argument("--checkpoint-file", type=str, default="artifacts/ckpt.translate.jsonl", help="Checkpoint jsonl path")
    ap.add_argument("--wal-file", type=str, default=None, help="Write-ahead log jsonl")
    ap.add_argument("--wal-every", type=int, default=10, help="WAL every N rows")

    ap.add_argument("--show-lines", action="store_true", help="Print RU/EN/OUT grouped lines")
    ap.add_argument("--max-chars", type=int, default=160, help="Max characters hint")

    ap.add_argument("--rpm", type=int, default=60, help="Rate limit: requests per minute")
    ap.add_argument("--tpm-max", type=int, default=100000, help="Token limit per minute (hint only)")

    # advanced/compat flags
    ap.add_argument("--workers", type=int, default=8, help="Parallel workers (placeholder)")
    ap.add_argument("--min-workers", type=int, default=2, help="Min workers (placeholder)")
    ap.add_argument("--max-workers", type=int, default=32, help="Max workers (placeholder)")
    ap.add_argument("--rpm-min", type=int, default=30, help="Min rpm (placeholder)")
    ap.add_argument("--rpm-max", type=int, default=1000, help="Max rpm (placeholder)")
    ap.add_argument("--auto-tune", action="store_true", help="Auto tune (placeholder)")
    ap.add_argument("--resume", action="store_true", help="Resume (placeholder)")

    # selective rerun controls
    ap.add_argument("--overwrite", action="store_true", help="Retranslate even if column 5 already has text")
    ap.add_argument("--row-range", type=str, default=None, help="Only rows in range start:end (0-based, end exclusive)")
    ap.add_argument("--speakers", type=str, default=None, help="Comma separated speaker filters, supports wildcard, e.g. student_*,teacher_*")
    ap.add_argument("--scene-range", type=str, default=None, help="Only scenes a:b (0-based indices). requires artifacts/scenes.json")
    ap.add_argument("--dry-run", action="store_true", help="Show planned rows count then exit")

    ap.add_argument("--out", type:str, default=None, help="Output Excel path")
    return ap

def load_yaml(path: str) -> Dict[str, Any]:
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

def resolve_provider(args, cfg):
    prov = args.provider or cfg.get("provider") or "deepseek"
    model_cfg = cfg.get("model") or cfg.get("llm") or {}
    if "deepseek" not in model_cfg and "llm" in cfg and "deepseek" in cfg["llm"]:
        model_cfg["deepseek"] = cfg["llm"]["deepseek"]
    if "openai" not in model_cfg and "llm" in cfg and "openai" in cfg["llm"]:
        model_cfg["openai"] = cfg["llm"]["openai"]
    return prov, model_cfg

class LLM:
    def __init__(self, provider: str, model_cfg: Dict[str, Any]):
        self.provider = provider
        self.client = None
        self.model = None
        self.base_url = None
        self.ok = False
        sec = (model_cfg.get(provider) or {})
        self.api_key = sec.get("api_key") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        self.base_url = sec.get("base_url") or os.getenv("OPENAI_BASE_URL") or None
        self.model = sec.get("name") or sec.get("model") or "gpt-4o-mini"
        if OpenAI is not None and self.api_key:
            try:
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url) if self.base_url else OpenAI(api_key=self.api_key)
                self.ok = True
            except Exception:
                self.client = None
                self.ok = False

    def translate(self, ru: str, en: str, speaker: str, target: str, glossary: Dict[str,str], max_chars: int) -> str:
        sys_prompt = (
            "You are an expert adult visual-novel localizer. Translate and LOCALIZE into fluent {lang} for a college-set adult VN in 'Sunville'. "
            "Honor speaker role for tone (teacher/principal/coach/ladies/system). "
            "Keep placeholders intact ([mcname], [mcsurname], {{var}}, <tags>). "
            "Do NOT translate brand names (Patreon, Instagram, Lovense), keep UI tech terms consistent. "
            "For campus location strings by 'string' speaker, translate as real in-campus places (e.g., 化学教室/实验室, 生物教室, 更衣室, 礼堂, 学院入口). "
            "Keep erotic details explicit but tasteful; dialogues must be natural spoken Chinese; avoid checklist style. "
            "Prefer longest-phrase matches from glossary. College = 学院."
        ).format(lang=target)

        user_payload = {
            "speaker": speaker,
            "ru": ru or "",
            "en": en or "",
            "glossary": glossary,
            "rules": [
                "Keep placeholders exactly as-is.",
                "Do not translate brand names.",
                "Dialogue colloquial and seductive; system strings concise."
            ]
        }

        content = json.dumps(user_payload, ensure_ascii=False)
        if self.ok and self.client is not None:
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role":"system","content":sys_prompt},
                        {"role":"user","content":content}
                    ],
                    temperature=0.2,
                )
                txt = (resp.choices[0].message.content or "").strip()
                return txt
            except Exception:
                pass
        return (en or ru or "").strip()

class RateLimiter:
    def __init__(self, rpm: int):
        self.lock = threading.Lock()
        self.min_interval = 60.0 / max(1, rpm)
        self.last = 0.0
    def wait(self):
        with self.lock:
            now = time.time()
            dt = now - self.last
            if dt < self.min_interval:
                time.sleep(self.min_interval - dt)
            self.last = time.time()

def is_blank_cell(v) -> bool:
    if v is None: return True
    try:
        if isinstance(v, float) and math.isnan(v): return True
    except Exception:
        pass
    s = str(v).strip()
    if s == "": return True
    if s.lower() in {"nan","none","null"}: return True
    return False

def parse_row_range(rr: Optional[str], n: int) -> Optional[Set[int]]:
    if not rr: return None
    try:
        a, b = rr.split(":")
        a = int(a) if a else 0
        b = int(b) if b else n
        a = max(0, a); b = min(n, b)
        return set(range(a, b))
    except Exception:
        return None

def parse_speakers(sp: Optional[str]) -> Optional[List[str]]:
    if not sp: return None
    parts = [x.strip() for x in sp.split(",") if x.strip()]
    return parts or None

def load_scenes_rows(scene_range: Optional[str]) -> Optional[Set[int]]:
    if not scene_range: return None
    try:
        a, b = scene_range.split(":")
        a = int(a) if a else 0
        b = int(b) if b else 1<<30
    except Exception:
        return None
    path = "artifacts/scenes.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            scenes = json.load(f)
        rows: Set[int] = set()
        for i, sc in enumerate(scenes):
            if i < a or i >= b: continue
            r = sc.get("rows") or sc.get("line_ids") or []
            for rid in r:
                try:
                    rows.add(int(rid))
                except Exception:
                    pass
        return rows
    except Exception:
        return None

def write_excel(df: pd.DataFrame, path: str):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        df.to_excel(path, index=False)
    except Exception as e:
        print(f"[WARN] snapshot save failed: {e}", flush=True)

def make_out_path(excel: str, lang: str) -> str:
    base = os.path.splitext(os.path.basename(excel))[0]
    d = os.path.dirname(os.path.abspath(excel))
    return os.path.join(d, f"{base}.{lang}.llm.xlsx")

def main():
    args = build_argparser().parse_args()
    cfg = load_yaml(args.settings)
    prov, model_cfg = resolve_provider(args, cfg)
    print(f"[CFG] provider={prov} rpm_init={args.rpm} tpm_max={args.tpm_max} workers={args.workers} min/max={args.min_workers}/{args.max_workers}", flush=True)

    # load glossary
    glossary: Dict[str,str] = {}
    if args.glossary and os.path.exists(args.glossary):
        try:
            with open(args.glossary, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                glossary = {str(k):str(v) for k,v in data.items() if isinstance(v,(str,int,float))}
        except Exception:
            glossary = {}

    # read excel
    sheet = args.sheet_name if args.sheet_name else args.sheet_index
    df = pd.read_excel(args.excel, sheet_name=sheet)
    while df.shape[1] < 5:
        df[df.shape[1]] = ""
    COL_RU, COL_SPK, COL_EN, COL_CN_CURR, COL_OUT = 0, 1, 2, 3, 4

    n = len(df)
    # base mask: empty or overwrite (robust NaN/None handling)
    if args.overwrite:
        base_mask = pd.Series([True]*n)
    else:
        base_mask = df.iloc[:, COL_OUT].apply(is_blank_cell)

    # row-range filter
    rowset = parse_row_range(args.row_range, n)
    if rowset is not None:
        mask_rr = pd.Series([False]*n)
        for i in rowset:
            if 0 <= i < n: mask_rr.iat[i] = True
        base_mask = base_mask & mask_rr

    # speaker filter
    sp_filters = parse_speakers(args.speakers)
    if sp_filters:
        mask_sp = pd.Series([False]*n)
        col = df.iloc[:, COL_SPK].astype(str).fillna("")
        for i, v in enumerate(col):
            if any(fnmatch.fnmatch(v, pat) for pat in sp_filters):
                mask_sp.iat[i] = True
        base_mask = base_mask & mask_sp

    # scene-range filter
    sc_rows = load_scenes_rows(args.scene_range)
    if sc_rows is not None:
        mask_sc = pd.Series([False]*n)
        for i in sc_rows:
            if 0 <= i < n: mask_sc.iat[i] = True
        base_mask = base_mask & mask_sc

    todo_idx = list(df.index[base_mask])
    total = int(df.shape[0])
    to_translate = int(base_mask.sum())
    print(f"[PLAN] total={total} to_translate={to_translate}", flush=True)

    if args.dry_run:
        print("[DRYRUN] nothing executed.", flush=True)
        return 0

    if to_translate == 0:
        out_path = args.out or make_out_path(args.excel, args.target_lang)
        write_excel(df, out_path)
        print(f"[OK] Done. Output -> {os.path.abspath(out_path)}", flush=True)
        return 0

    llm = LLM(prov, model_cfg)
    rl = RateLimiter(rpm=args.rpm)

    out_path = args.out or make_out_path(args.excel, args.target_lang)
    autosave_every = max(1, args.autosave_every)
    autosave_seconds = max(15, args.autosave_seconds)
    last_snap = time.time()

    wal_fd = None
    if args.wal_file:
        os.makedirs(os.path.dirname(os.path.abspath(args.wal_file)), exist_ok=True)
        wal_fd = open(args.wal_file, "a", encoding="utf-8")
        wal_every = max(1, args.wal_every)
    else:
        wal_every = 1<<30  # never

    done = 0
    for i, idx in enumerate(todo_idx, 1):
        ru = str(df.iat[idx, COL_RU]) if not pd.isna(df.iat[idx, COL_RU]) else ""
        en = str(df.iat[idx, COL_EN]) if not pd.isna(df.iat[idx, COL_EN]) else ""
        sp = str(df.iat[idx, COL_SPK]) if not pd.isna(df.iat[idx, COL_SPK]) else "string"

        rl.wait()
        out = llm.translate(ru=ru, en=en, speaker=sp, target=args.target_lang, glossary=glossary, max_chars=args.max_chars)
        df.iat[idx, COL_OUT] = out

        if args.show_lines:
            sys.stdout.write(f"RU: {ru}\nEN: {en}\nOUT: {out}\n")
            sys.stdout.flush()

        done += 1
        q = to_translate - done
        pct = (done / max(1, to_translate)) * 100.0
        print(f"[PROGRESS] q={q} ({pct:.1f}%)", flush=True)

        if wal_fd and (i % wal_every == 0):
            wal_fd.write(json.dumps({"row": int(idx), "out": out}, ensure_ascii=False) + "\n")
            wal_fd.flush()

        tnow = time.time()
        if (i % autosave_every == 0) or (tnow - last_snap >= autosave_seconds):
            write_excel(df, out_path)
            print(f"[SNAPSHOT] Output -> {os.path.abspath(out_path)}", flush=True)
            last_snap = tnow

    write_excel(df, out_path)
    if wal_fd: wal_fd.close()
    print(f"[OK] Done. Output -> {os.path.abspath(out_path)}", flush=True)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as e:
        raise
    except Exception as e:
        print(f"[ERROR] {e}", flush=True)
        sys.exit(1)
