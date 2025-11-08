#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
20_enforce_terms.py — glossary enforcement on col5 with guard
- Longest-match-first replacements from name_map.json
- Guard modes: --guard en|ru|both|none  (default: none)
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
    ap.add_argument("--guard", choices=["none","en","ru","both"], default="none")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    df = pd.read_excel(args.excel, sheet_name=args.sheet)
    while df.shape[1] < 5: df[f"col_{df.shape[1]}"] = ""
    gl = load_glossary(args.glossary)
    keys = sorted(gl.keys(), key=len, reverse=True)

    def can_apply(i, key):
        if args.guard == "none":
            return True
        en = str(df.iloc[i,2])
        ru = str(df.iloc[i,0])
        if args.guard == "en":
            return key.lower() in en.lower()
        if args.guard == "ru":
            return key.lower() in ru.lower()
        return (key.lower() in en.lower()) and (key.lower() in ru.lower())

    # precompile regex dict (word-boundary-ish)
    regs = [(re.compile(re.escape(k), re.I), gl[k]) for k in keys]

    replaced = 0
    for i in range(df.shape[0]):
        s = str(df.iloc[i,4])
        if not s: continue
        for rx, repl in regs:
            if not can_apply(i, rx.pattern.strip("\\").lower()):
                continue
            s2 = rx.sub(repl, s)
            if s2 != s:
                s = s2
                replaced += 1
        df.iat[i,4] = s

    out = Path(args.out) if args.out else Path(args.excel).with_suffix("").with_name(Path(args.excel).stem + ".terms.xlsx")
    df.to_excel(out, index=False)
    print(f"[OK] Terms enforced. Replacements: {replaced}")
    print(f"Output -> {out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
