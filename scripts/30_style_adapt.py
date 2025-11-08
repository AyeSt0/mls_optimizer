#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
30_style_adapt.py — micro style adaptation + punctuation mapping
- If speaker is 'string' and value looks like campus labels, map to Chinese place names.
- Apply punctuation mapping after translation to col5.
"""
import argparse, json, re
from pathlib import Path
import pandas as pd

CAMPUS_MAP = {
    "BIOLOGY": "生物教室",
    "CHEMISTRY": "化学教室",
    "GEOGRAPHY": "地理教室",
    "COMPUTER CLASS": "计算机教室",
    "ASSEMBLY HALL": "礼堂",
    "LOCKER": "储物柜",
    "LOCKER ROOMS": "更衣室",
    "GYM": "体育馆",
    "DOCTOR'S OFFICE": "校医室",
    "STEWARD'S OFFICE": "教务处办公室",
    "COLLEGE ENTRANCE": "学院正门",
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default="0")
    ap.add_argument("--punct-map", default=None, help="JSON mapping file for punctuation")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    df = pd.read_excel(args.excel, sheet_name=args.sheet)
    while df.shape[1] < 5: df[f"col_{df.shape[1]}"] = ""

    # load punct map
    pmap = {}
    if args.punct_map and Path(args.punct_map).exists():
        try:
            pmap = json.loads(Path(args.punct_map).read_text("utf-8"))
        except Exception:
            pmap = {}
    # defaults
    if not pmap:
        pmap = { "...": "…", "....":"…", "—":"—", "--":"——", "!?":"？！", "?!":"？！" }

    for i in range(df.shape[0]):
        speaker = str(df.iloc[i,1]).strip().lower()
        en = str(df.iloc[i,2]).strip()
        out = str(df.iloc[i,4])
        if speaker == "string":
            key = en.upper()
            # try exact
            if key in CAMPUS_MAP and out:
                df.iat[i,4] = CAMPUS_MAP[key]
                continue
            # fuzzy contains
            for k,v in CAMPUS_MAP.items():
                if k in key and out:
                    df.iat[i,4] = v
                    break
        # punctuation mapping
        s = df.iat[i,4]
        for k,v in pmap.items():
            s = s.replace(k, v)
        df.iat[i,4] = s

    outp = Path(args.out) if args.out else Path(args.excel).with_suffix("").with_name(Path(args.excel).stem + ".styled.xlsx")
    df.to_excel(outp, index=False)
    print(f"[OK] Style adapted.")
    print(f"Output -> {outp}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
