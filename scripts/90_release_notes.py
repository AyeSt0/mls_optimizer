#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, pandas as pd, os, datetime as dt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default=0)
    ap.add_argument("--out", default="artifacts/RELEASE_NOTES.md")
    args = ap.parse_args()
    df = pd.read_excel(args.excel, sheet_name=args.sheet)
    while df.shape[1] < 5:
        df[df.shape[1]] = ""
    total = len(df)
    filled = df.iloc[:,4].astype(str).str.len().gt(0).sum()
    old_cn = df.iloc[:,3].astype(str).str.len().gt(0).sum()
    new_only = (df.iloc[:,4].astype(str).str.len().gt(0) & df.iloc[:,3].astype(str).str.len().eq(0)).sum()
    both = (df.iloc[:,4].astype(str).str.len().gt(0) & df.iloc[:,3].astype(str).str.len().gt(0)).sum()
    pct = (filled/total*100) if total else 0
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out,"w",encoding="utf-8") as f:
        f.write(f"# Release Notes ({dt.datetime.now():%Y-%m-%d %H:%M})\n\n")
        f.write(f"- Source file: `{args.excel}` (sheet `{args.sheet}`)\n")
        f.write(f"- Total rows: **{total}**\n")
        f.write(f"- New CN (col5) filled: **{filled}**  ({pct:.2f}%)\n")
        f.write(f"- Old CN (col4) existed: **{old_cn}**\n")
        f.write(f"- Newly translated (only col5): **{new_only}**\n")
        f.write(f"- Overwritten/Both existed: **{both}**\n")
    print(f"[OK] release notes -> {os.path.abspath(args.out)}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
