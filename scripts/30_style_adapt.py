
import argparse, os, json
from tqdm import tqdm
import pandas as pd
from mls_optimizer.io_utils import load_excel, save_excel
from mls_optimizer.config import OptimConfig

# Very light style pass: punctuation map + small whitespace normalization
def apply_style(s: str, punct_map: dict) -> str:
    if not s: return s
    out = s
    for k, v in punct_map.items():
        out = out.replace(k, v)
    # collapse excessive spaces around Chinese punctuation
    out = out.replace(" ，", "，").replace(" 。", "。").replace(" ！", "！").replace(" ？", "？")
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Style & punctuation pass with progress/resume/autosave")
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--punct-map", required=True)
    ap.add_argument("--target-lang", default="zh-CN")
    ap.add_argument("--start-row", type=int, default=0)
    ap.add_argument("--end-row", type=int, default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--checkpoint-file", default="artifacts/ckpt.style.jsonl")
    ap.add_argument("--autosave-every", type=int, default=800)
    args = ap.parse_args()

    os.makedirs("artifacts", exist_ok=True)
    df = load_excel(args.excel, args.sheet)
    cfg = OptimConfig()
    out_col = df.columns[cfg.col_out]

    with open(args.punct_map, "r", encoding="utf-8") as f:
        punct = json.load(f) if args.punct_map.lower().endswith(".json") else None
        if punct is None:
            # try yaml
            try:
                import yaml
                punct = yaml.safe_load(f)
            except Exception:
                raise RuntimeError("punct-map must be JSON or YAML")

    from mls_optimizer.checkpoint import Checkpointer
    ckpt = Checkpointer(args.checkpoint_file)

    n = len(df)
    end = args.end_row if args.end_row is not None else n
    bar = tqdm(total=(end - args.start_row), desc="Style pass")
    changed = 0
    for i in range(args.start_row, end):
        if args.resume and (i in ckpt.processed):
            bar.update(1); continue
        row = df.iloc[i]
        zh = "" if pd.isna(row.iloc[cfg.col_out]) else str(row.iloc[cfg.col_out])
        if not zh:
            ckpt.mark(i, {"skip": "empty"}); bar.update(1); continue
        new_zh = apply_style(zh, punct)
        if new_zh != zh:
            df.at[i, out_col] = new_zh
            changed += 1
        ckpt.mark(i, {"changed": bool(new_zh != zh)})
        if i % max(1, args.autosave_every) == 0 and i != 0:
            tmp = args.excel.replace(".xlsx", f".{args.target_lang}.styled.part.xlsx")
            save_excel(df, tmp)
        bar.update(1)
    bar.close()

    out_path = args.out or (args.excel.replace(".xlsx", f".{args.target_lang}.styled.xlsx"))
    save_excel(df, out_path)
    print(f"[OK] Style pass changed={changed} -> {out_path}")
