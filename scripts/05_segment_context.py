#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
05_segment_context.py
- Build scene segmentation to artifacts/scenes.json
- Heuristics: group rows into scenes by blank english lines or 'string' location labels,
  otherwise chunk by fixed window size.
"""
import argparse, json, os, math, pandas as pd

def load_excel(path, sheet):
    return pd.read_excel(path, sheet_name=sheet)

def guess_cols(df):
    # Try to guess columns: RU, EN, SPEAKER
    cols = list(df.columns)
    ru = 0
    en = 1 if len(cols) > 1 else None
    speaker = 2 if len(cols) > 2 else None
    return {"ru": ru, "en": en, "speaker": speaker}

def build_scenes(df, col_en=1, col_speaker=2, window=25):
    n = len(df)
    scenes = []
    cur = []
    def flush():
        nonlocal cur, scenes
        if cur:
            scenes.append({"start": cur[0], "end": cur[-1]})
            cur = []

    for i in range(n):
        en = str(df.iloc[i, col_en]) if col_en is not None and col_en < df.shape[1] else ""
        sp = str(df.iloc[i, col_speaker]) if col_speaker is not None and col_speaker < df.shape[1] else ""
        cur.append(i)
        # Split on likely UI/location lines or empty English
        if not en.strip():
            flush()
        elif sp.strip().lower() == "string" and en.isupper() and 1 <= len(en.split()) <= 4:
            flush()
        elif len(cur) >= window:
            flush()
    flush()
    return scenes

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet-index", default=0, type=int)
    ap.add_argument("--out", default="artifacts/scenes.json")
    args = ap.parse_args()
    df = load_excel(args.excel, args.sheet_index)
    cols = guess_cols(df)
    scenes = build_scenes(df, col_en=cols.get("en"), col_speaker=cols.get("speaker"))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"sheet": args.sheet_index, "scenes": scenes, "total_rows": len(df)}, f, ensure_ascii=False, indent=2)
    print(f"[OK] Scenes built: {len(scenes)}  (covered rows: {len(df)})")
    print(f"[OK] Scenes saved to {os.path.abspath(args.out)}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
