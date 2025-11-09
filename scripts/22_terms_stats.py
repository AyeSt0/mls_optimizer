#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, pandas as pd, re, os, json
from glossary_utils import load_glossary

def ensure_cols(df, n=5):
    while df.shape[1] < n:
        df[df.shape[1]] = ""
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default=0)
    ap.add_argument("--glossary", required=True)
    ap.add_argument("--out", default="artifacts/22_terms_stats.json")
    args = ap.parse_args()
    df = pd.read_excel(args.excel, sheet_name=args.sheet)
    ensure_cols(df, 5)
    gloss = load_glossary(args.glossary)
    keys = []
    if isinstance(gloss, dict):
        if "en2zh" in gloss and isinstance(gloss["en2zh"], dict):
            keys = list(gloss["en2zh"].keys())
        else:
            keys = list(gloss.keys())
    terms_hit = {k:0 for k in keys}
    col = df.iloc[:,4].astype(str)
    for s in col:
        for k in keys:
            if k and k in s:
                terms_hit[k] += 1
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out,"w",encoding="utf-8") as f:
        json.dump({"hits":terms_hit}, f, ensure_ascii=False, indent=2)
    print(f"[OK] terms stats -> {os.path.abspath(args.out)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
