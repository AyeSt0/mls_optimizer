#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
22_terms_stats.py — rough glossary hit statistics
Counts occurrences of glossary entries in col5.
"""
import argparse, json, re
from pathlib import Path
import pandas as pd

def load_glossary(path):
    data = json.loads(Path(path).read_text("utf-8"))
    if isinstance(data, dict):
        return data
    flat = {}
    for it in data:
        if isinstance(it, dict):
            flat.update(it)
    return flat

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default="0")
    ap.add_argument("--glossary", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    df = pd.read_excel(args.excel, sheet_name=args.sheet)
    while df.shape[1] < 5: df[f"col_{df.shape[1]}"] = ""

    gl = load_glossary(args.glossary)
    keys = sorted(gl.keys(), key=len, reverse=True)
    regs = [(k, re.compile(re.escape(gl[k]))) for k in keys]

    stats = []
    text = "\n".join(str(x) for x in df.iloc[:,4].fillna("").tolist())
    for k, rx in regs:
        cnt = len(rx.findall(text))
        stats.append({"term": gl[k], "src": k, "count": cnt})
    out = Path(args.out) if args.out else Path(args.excel).with_suffix("").with_name(Path(args.excel).stem + ".terms.stats.json")
    out.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Terms stats written.")
    print(f"Output -> {out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
