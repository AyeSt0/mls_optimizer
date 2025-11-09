#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
25_qa_check.py — simple QA for placeholders, numbers, and length ratio.
Writes artifacts/25_qa_report.csv
"""
import argparse, pandas as pd, re, os

PH_RE = re.compile(r"(\[[^\]]+\]|\{[^}]+\}|\{\{[^}]+\}\}|<[^>]+>)")

def ensure_cols(df, n=5):
    while df.shape[1] < n:
        df[df.shape[1]] = ""
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default=0)
    ap.add_argument("--out", default="artifacts/25_qa_report.csv")
    args = ap.parse_args()

    df = pd.read_excel(args.excel, sheet_name=args.sheet)
    ensure_cols(df, 5)
    src = df.iloc[:,1].astype(str)  # EN for baseline
    tgt = df.iloc[:,4].astype(str)  # CN
    rows = []
    for i, (s, t) in enumerate(zip(src, tgt)):
        ph_src = set(PH_RE.findall(s))
        ph_tgt = set(PH_RE.findall(t))
        ph_missing = list(ph_src - ph_tgt)
        nums_src = re.findall(r"\d+\.?\d*", s)
        nums_tgt = re.findall(r"\d+\.?\d*", t)
        missing_num = [n for n in nums_src if n not in nums_tgt]
        ratio = (len(t)/len(s)) if len(s)>0 else 1.0
        rows.append({
            "row": i,
            "src_len": len(s),
            "tgt_len": len(t),
            "len_ratio": ratio,
            "missing_placeholders": "|".join(ph_missing),
            "missing_nums": "|".join(missing_num),
        })
    rep = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    rep.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"[OK] QA report -> {os.path.abspath(args.out)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
