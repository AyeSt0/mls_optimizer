
import argparse, os
from tqdm import tqdm
import pandas as pd
from mls_optimizer.io_utils import load_excel, save_excel
from mls_optimizer.config import OptimConfig
from mls_optimizer.terms import load_name_map, longest_first_pairs, enforce_terms
from mls_optimizer.checkpoint import Checkpointer

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Enforce glossary terms (longest-first) with progress/resume/autosave")
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--name-map", required=True)
    ap.add_argument("--target-lang", default="zh-CN")
    ap.add_argument("--guard-by", default="BOTH", choices=["EN","RU","BOTH","NONE"])
    ap.add_argument("--start-row", type=int, default=0)
    ap.add_argument("--end-row", type=int, default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--checkpoint-file", default="artifacts/ckpt.enforce.jsonl")
    ap.add_argument("--autosave-every", type=int, default=500)
    args = ap.parse_args()

    os.makedirs("artifacts", exist_ok=True)
    df = load_excel(args.excel, args.sheet)
    cfg = OptimConfig()
    out_col = df.columns[cfg.col_out]

    nm = load_name_map(args.name_map if hasattr(args, "name-map") else args.__dict__["name-map"], target_lang=args.target_lang)
    pairs = longest_first_pairs(nm)

    ckpt = Checkpointer(args.checkpoint_file)

    n = len(df)
    end = args.end_row if args.end_row is not None else n

    bar = tqdm(total=(end - args.start_row), desc="Enforce terms")
    changed = 0
    for i in range(args.start_row, end):
        if args.resume and (i in ckpt.processed):
            bar.update(1); continue
        row = df.iloc[i]
        zh = "" if pd.isna(row.iloc[cfg.col_out]) else str(row.iloc[cfg.col_out])
        en = "" if pd.isna(row.iloc[cfg.col_en]) else str(row.iloc[cfg.col_en])
        ru = "" if pd.isna(row.iloc[cfg.col_ru]) else str(row.iloc[cfg.col_ru])
        if not zh:
            bar.update(1); ckpt.mark(i, {"skip":"empty"}); continue
        new_zh, changes = enforce_terms(zh, en, ru, pairs, guard_by=args.guard_by)
        if new_zh != zh:
            df.at[i, out_col] = new_zh
            changed += 1
        ckpt.mark(i, {"changed": bool(new_zh != zh), "n": len(changes)})
        if i % max(1, args.autosave_every) == 0 and i != 0:
            tmp = args.excel.replace(".xlsx", f".{args.target_lang}.terms.part.xlsx")
            save_excel(df, tmp)
        bar.update(1)
    bar.close()

    out_path = args.out or (args.excel.replace(".xlsx", f".{args.target_lang}.terms.xlsx"))
    save_excel(df, out_path)
    print(f"[OK] Enforce done: {changed} changed -> {out_path}")
