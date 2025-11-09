#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
30_style_adapt.py — basic CN punctuation normalization for col5.
"""
import argparse, os, pandas as pd, re

def ensure_cols(df, n=5):
    while df.shape[1] < n:
        df[df.shape[1]] = ""
    return df

def norm_cn_punct(s: str) -> str:
    if not s:
        return s
    # naive mapping
    s = s.replace("...", "…")
    s = s.replace(" .", "。").replace(".", "。")
    s = s.replace(",", "，")
    s = s.replace("?", "？")
    s = s.replace("!", "！")
    # remove double spaces
    s = re.sub(r"\s{2,}", " ", s)
    # trim
    return s.strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default=0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    df = pd.read_excel(args.excel, sheet_name=args.sheet)
    ensure_cols(df, 5)
    tgt_col = 4
    changed = 0
    for i in range(len(df)):
        s = str(df.iloc[i, tgt_col])
        fixed = norm_cn_punct(s)
        if fixed != s:
            df.iloc[i, tgt_col] = fixed
            changed += 1

    out_path = args.out or args.excel
    with pd.ExcelWriter(out_path, engine="openpyxl", mode="w") as xw:
        df.to_excel(xw, index=False, sheet_name=str(args.sheet))
    os.makedirs("artifacts", exist_ok=True)
    out2 = os.path.join("artifacts", "30_style_fixed.xlsx")
    with pd.ExcelWriter(out2, engine="openpyxl", mode="w") as xw:
        df.to_excel(xw, index=False, sheet_name=str(args.sheet))
    print(f"[OK] Style normalized rows: {changed}")
    print(f"Output -> {os.path.abspath(out_path)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
