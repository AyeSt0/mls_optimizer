
from pathlib import Path
import os, sys, re, json, time, math, threading, queue, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import pandas as pd

try:
    import yaml
except Exception:
    yaml = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

def load_settings(p: Path) -> dict:
    if not p.exists():
        return {}
    text = p.read_text("utf-8")
    try:
        return json.loads(text)
    except Exception:
        if yaml:
            try:
                return yaml.safe_load(text) or {}
            except Exception:
                return {}
        return {}

def get_cfg_value(cfg: dict, path: str, default=None):
    cur = cfg
    for part in path.split("."):
        if not isinstance(cur, dict): return default
        cur = cur.get(part)
    return default if cur is None else cur

def load_excel(path: str, sheet):
    try:
        if sheet is None or sheet == "":
            return pd.read_excel(path)
        try:
            si = int(sheet)
            return pd.read_excel(path, sheet_name=si)
        except Exception:
            return pd.read_excel(path, sheet_name=sheet)
    except Exception as e:
        raise RuntimeError(f"Failed to read Excel: {e}")

def ensure_col5(df: pd.DataFrame) -> pd.DataFrame:
    if df.shape[1] < 5:
        for _ in range(5 - df.shape[1]):
            df[df.shape[1]] = ""
    return df

def detect_empty_rows(df: pd.DataFrame) -> list:
    col = df.columns[4]
    empty_mask = df[col].isna() | (df[col].astype(str).str.strip() == "")
    return list(df.index[empty_mask])

def load_glossary(glossary_path: str, glossary_max: int|None=None) -> dict:
    if not glossary_path or not os.path.exists(glossary_path):
        return {}
    try:
        g = json.loads(Path(glossary_path).read_text("utf-8"))
    except Exception:
        return {}
    flat = {}
    def walk(d):
        if isinstance(d, dict):
            for k,v in d.items():
                if isinstance(v, (str,int,float)):
                    flat[str(k)] = str(v)
                elif isinstance(v, dict):
                    walk(v)
                elif isinstance(v, list):
                    if len(v) >= 6 and isinstance(v[5], str):
                        flat[str(k)] = v[5]
    walk(g)
    items = sorted(flat.items(), key=lambda kv: len(kv[0]), reverse=True)
    if glossary_max and glossary_max > 0:
        items = items[:glossary_max]
    return dict(items)

def build_domain_rules():
    return {
        "BIOLOGY": "生物教室",
        "CHEMISTRY": "化学教室",
        "GEOGRAPHY": "地理教室",
        "COMPUTER CLASS": "计算机教室",
        "GYM": "体育馆",
        "LOCKER ROOMS": "更衣室",
        "LOCKER": "储物柜间",
        "ASSEMBLY HALL": "礼堂",
        "DOCTOR'S OFFICE": "医务室",
        "STEWARD'S OFFICE": "教务处",
        "COLLEGE ENTRANCE": "学院大门"
    }

def build_prehint_for_scene(glossary: dict, speaker: str|None) -> str:
    keep_raw = ["Patreon","Instagram","Lovense","OnlyFans","Twitter","Discord"]
    placeholders_examples = ["[mcname]","[mcsurname]","mcname","{{var}}","<tag>"]
    s_rules = []
    if speaker and speaker.lower() == "string":
        room_like = build_domain_rules()
        s_rules.append("当文本是学院内的设施/课程/房间名称时，用“X 教室/办公室/体育馆/更衣室/储物柜间/医务室/礼堂/学院大门”等自然中文表达，而不是单个学科名。")
        s_rules.append("如果是城镇地点名称，翻译为自然的中文地名风格，但保留专有名固有名的辨识度。")
        for en, zh in room_like.items():
            s_rules.append(f"{en} → {zh}")
    s_rules.append("保留品牌/平台名原文不译：" + "、".join(keep_raw))
    s_rules.append("占位符/变量/标签必须原样保留，例如：" + "、".join(placeholders_examples))
    terms_lines = [f"{src} → {tgt}" for src, tgt in glossary.items()]
    pre = "术语与风格提示（仅供生成参考，不改原文）\n" + "\n".join(s_rules[:12])
    if terms_lines:
        pre += "\n\n优先级：最长匹配优先；以下术语必须一致（仅供参考）：\n" + "\n".join(terms_lines[:200])
    return pre

def make_prompt(target_lang: str, prehint: str, speaker: str|None, ru: str, en: str, ctx: str) -> str:
    role = "你是一名资深成人视觉小说本地化写手（College 场景，全部角色均为成年）。"
    tone = "中文要自然、口语化但不低级，保持露骨细节（不审查、不错译）。"
    addr = "若为对话，遵循中文对话语序与语气；若为系统/地点字符串（string speaker），按地点/设施自然表达。"
    keep = "保留所有占位符/变量/标签（如 [mcname]、[mcsurname]、mcname、{{var}}、<tag>）原样不动；品牌名原文保留。"
    names = "人名/地名若术语表已有固定译名，严格使用；否则保持与上下文一致，不强行音译。"
    style = "避免清单式/指令式直译；把短句合并为自然短语或句群；不要加入解释。"
    output = "只输出最终译文，不要引号、不加任何说明。"
    speaker_hint = f"当前说话者：{speaker or 'unknown'}。"
    ctx_snip = f"【上下文】\n{ctx}" if ctx else ""
    en_ru = f"【英文参考】\n{en}\n【俄文参考】\n{ru}"
    pre = f"【术语/风格提示】\n{prehint}" if prehint else ""
    return "\n".join([role, tone, addr, keep, names, style, speaker_hint, pre, ctx_snip, en_ru, "【输出语言】"+target_lang, output]).strip()

def openai_client_from_settings(cfg: dict, provider: str):
    if OpenAI is None:
        raise RuntimeError("openai package missing. pip install openai")
    if provider == "deepseek":
        api_key = get_cfg_value(cfg, "llm.deepseek.api_key", os.getenv("DEEPSEEK_API_KEY") or os.getenv("SILICONFLOW_API_KEY"))
        base_url = get_cfg_value(cfg, "llm.deepseek.base_url", os.getenv("DEEPSEEK_BASE_URL") or os.getenv("SILICONFLOW_BASE_URL") or "https://api.siliconflow.cn/v1")
        model = get_cfg_value(cfg, "llm.deepseek.name", "deepseek-ai/DeepSeek-V3.2-Exp")
        if not api_key: raise RuntimeError("Missing DeepSeek/SiliconFlow API key")
        cli = OpenAI(api_key=api_key, base_url=base_url)
        return cli, model
    else:
        api_key = get_cfg_value(cfg, "llm.openai.api_key", os.getenv("OPENAI_API_KEY"))
        base_url = get_cfg_value(cfg, "llm.openai.base_url", os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1")
        model = get_cfg_value(cfg, "llm.openai.name", "gpt-4o-mini")
        if not api_key: raise RuntimeError("Missing OPENAI_API_KEY")
        cli = OpenAI(api_key=api_key, base_url=base_url)
        return cli, model

def scenes_from_file() -> dict:
    p = Path("artifacts/scenes.json")
    if not p.exists(): return {}
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return {}

def context_for_row(scenes: dict, idx: int, df: pd.DataFrame, max_chars: int) -> str:
    if scenes and "scenes" in scenes:
        for sc in scenes["scenes"]:
            if idx in sc.get("rows", []):
                rows = sc.get("rows", [])
                try:
                    pos = rows.index(idx)
                except ValueError:
                    break
                win = rows[max(0,pos-3): pos+4]
                chunks = []
                for r in win:
                    orig = str(df.iloc[r,0]) if r < len(df) else ""
                    eng = str(df.iloc[r,2]) if r < len(df.columns) else ""
                    if orig or eng:
                        chunks.append(f"RU:{orig} / EN:{eng}")
                s = "\n".join(chunks)
                return s[-max_chars:]
    start = max(0, idx-3); end = min(len(df), idx+4)
    pieces = []
    for r in range(start, end):
        orig = str(df.iloc[r,0])
        eng = str(df.iloc[r,2]) if df.shape[1] > 2 else ""
        if orig or eng:
            pieces.append(f"RU:{orig} / EN:{eng}")
    s = "\n".join(pieces)
    return s[-max_chars:]

class RPMController:
    def __init__(self, rpm_init=400, rpm_min=60, rpm_max=1000, auto=True):
        self.lock = threading.Lock()
        self.rpm = rpm_init
        self.rpm_min = rpm_min
        self.rpm_max = rpm_max
        self.auto = auto
        self.last = 0.0

    def before_send(self):
        with self.lock:
            now = time.time()
            if self.rpm <= 0: return
            interval = 60.0 / self.rpm
            if self.last == 0.0:
                self.last = now
                return
            delta = now - self.last
            if delta < interval:
                time.sleep(interval - delta)
            self.last = time.time()

    def after_ok(self):
        pass

    def after_error(self, e: Exception):
        if not self.auto: return
        msg = str(e)
        if "429" in msg or "rate" in msg.lower():
            with self.lock:
                self.rpm = max(self.rpm_min, int(self.rpm * 0.7))

def call_llm(cli, model, prompt, rpm_controller):
    rpm_controller.before_send()
    try:
        rsp = cli.chat.completions.create(
            model=model,
            messages=[
                {"role":"system","content":"You are a professional adult VN localization writer."},
                {"role":"user","content":prompt}
            ],
            temperature=0.6
        )
        txt = rsp.choices[0].message.content.strip()
        rpm_controller.after_ok()
        return txt
    except Exception as e:
        rpm_controller.after_error(e)
        raise

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default="0")
    ap.add_argument("--target-lang", default="zh-CN")
    ap.add_argument("--settings", default="config/settings.local.yaml")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--glossary", default=None)
    ap.add_argument("--glossary-max", type=int, default=200)
    ap.add_argument("--context-mode", default="scene", choices=["scene","nearby","none"])
    ap.add_argument("--autosave-every", type=int, default=300)
    ap.add_argument("--autosave-seconds", type=int, default=90)
    ap.add_argument("--checkpoint-file", default="artifacts/ckpt.translate.jsonl")
    ap.add_argument("--wal-file", default="artifacts/translate.wal.jsonl")
    ap.add_argument("--wal-every", type=int, default=10)
    ap.add_argument("--show-lines", action="store_true")
    ap.add_argument("--max-chars", type=int, default=160)
    ap.add_argument("--rpm", type=int, default=400)
    ap.add_argument("--rpm-min", type=int, default=60)
    ap.add_argument("--rpm-max", type=int, default=1000)
    ap.add_argument("--tpm-max", type=int, default=100000)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--min-workers", type=int, default=4)
    ap.add_argument("--max-workers", type=int, default=32)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--est-input-ratio", type=float, default=3.2)
    ap.add_argument("--est-output-tokens", type=int, default=220)
    ap.add_argument("--auto-tune", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    df = load_excel(args.excel, args.sheet)
    df = ensure_col5(df)

    needs = detect_empty_rows(df)
    total = len(df)
    to_do = len(needs)
    print(f"[CFG] provider={(args.provider or 'auto')} rpm_init={args.rpm} tpm_max={args.tpm_max} context_mode={args.context_mode} workers={args.workers} min/max={args.min_workers}/{args.max_workers}")
    print(f"[PLAN] total={total}, empty(col5)={to_do}, to_translate={to_do}")

    if to_do == 0:
        outp = args.out or (str(Path(args.excel).with_suffix(f".{args.target_lang}.llm.xlsx")))
        df.to_excel(outp, index=False)
        print(f"[OK] Done. Output -> {outp}")
        return

    cfg = load_settings(Path(args.settings))
    provider = args.provider or cfg.get("provider") or "deepseek"
    client, model = openai_client_from_settings(cfg, provider)

    scenes = scenes_from_file()
    glossary = load_glossary(args.glossary, args.glossary_max)
    rpmc = RPMController(args.rpm, args.rpm_min, args.rpm_max, auto=args.auto_tune)

    outp = args.out or (str(Path(args.excel).with_suffix(f".{args.target_lang}.llm.xlsx")))
    ckpt = Path(args.checkpoint_file)
    wal = Path(args.wal_file)
    wal.parent.mkdir(parents=True, exist_ok=True)

    if args.resume and Path(outp).exists():
        try:
            df_existing = pd.read_excel(outp)
            if df_existing.shape[1] >= 5:
                df.iloc[:,4] = df_existing.iloc[:,4]
                needs = detect_empty_rows(df)
                to_do = len(needs)
                print(f"[INFO] resume: loaded previous output, remaining={to_do}")
        except Exception:
            pass

    q_idx = queue.Queue()
    for i in needs:
        q_idx.put(i)
    lock_write = threading.Lock()

    stats = {"done":0,"ok":0,"err":0}
    t_last_save = time.time()
    wal_buf = []

    initial_workers = max(args.min_workers, min(args.workers, args.max_workers))
    executor = ThreadPoolExecutor(max_workers=initial_workers)
    futures = []

    def worker_loop():
        nonlocal t_last_save, wal_buf
        while True:
            try:
                i = q_idx.get_nowait()
            except queue.Empty:
                break
            try:
                ru = str(df.iloc[i,0]) if df.shape[1] > 0 else ""
                speaker = str(df.iloc[i,1]) if df.shape[1] > 1 else ""
                en = str(df.iloc[i,2]) if df.shape[1] > 2 else ""
                prehint = build_prehint_for_scene(glossary, speaker)
                ctx = ""
                if args.context_mode != "none":
                    ctx = context_for_row(scenes, i, df, args.max_chars)
                prompt = make_prompt(args.target_lang, prehint, speaker, ru, en, ctx)
                if args.show_lines:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] RU: {ru}")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] EN: {en}")
                out = call_llm(client, model, prompt, rpmc)
                if args.show_lines:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] OUT: {out}")
                with lock_write:
                    df.iat[i,4] = out
                wal_buf.append({"i":i,"out":out})
                stats["ok"] += 1
            except Exception as e:
                stats["err"] += 1
                print(f"[WARN] row={i} failed: {e}")
            finally:
                stats["done"] += 1
                now = time.time()
                if (stats["done"] % max(1,args.autosave_every) == 0) or (now - t_last_save >= args.autosave_seconds):
                    with lock_write:
                        if wal_buf:
                            with wal.open("a", encoding="utf-8") as wf:
                                for rec in wal_buf:
                                    wf.write(json.dumps(rec, ensure_ascii=False) + "\\n")
                            wal_buf.clear()
                        df.to_excel(outp, index=False)
                    print(f"[OK] autosave -> {outp}")
                    t_last_save = now
            q_idx.task_done()

    for _ in range(initial_workers):
        futures.append(executor.submit(worker_loop))

    print(f"[INFO] running with {initial_workers} workers (fixed in this build).")

    for f in as_completed(futures):
        pass

    with open(wal, "a", encoding="utf-8") as wf:
        for rec in wal_buf:
            wf.write(json.dumps(rec, ensure_ascii=False) + "\\n")
    df.to_excel(outp, index=False)
    print(f"[OK] Done. Output -> {outp}")

if __name__ == "__main__":
    main()
