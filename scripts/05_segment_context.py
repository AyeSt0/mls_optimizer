#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
05_segment_context.py — scene segmentation
Input: Excel (col0=RU, col1=speaker, col2=EN, col3=CN(raw))
Output: artifacts/scenes.json  (list of scenes; each scene is list of row indices)
Heuristics: split on speaker changes and long "string"/system breaks; keep contiguous dialogue blocks together.
"""
import argparse, json
from pathlib import Path
import pandas as pd

ARTI_DIR = Path(__file__).resolve().parent.parent / "artifacts"
ARTI_DIR.mkdir(parents=True, exist_ok=True)

def load_excel(path, sheet):
    df = pd.read_excel(path, sheet_name=sheet)
    # normalize columns to 4+
    ncols = df.shape[1]
    for _ in range(max(0, 4 - ncols)):
        df[f"col_{ncols+_}"] = ""
    return df

def segment_dataframe(df: pd.DataFrame):
    # expected columns: 0 RU, 1 speaker, 2 EN, 3 CN, (4 CN_llm target)
    scenes = []
    cur = []
    prev_s = None
    def flush():
        nonlocal cur
        if cur:
            scenes.append(cur)
            cur = []
    for i, row in df.iterrows():
        s = str(row.iloc[1]).strip().lower()
        ru = str(row.iloc[0]).strip() if not pd.isna(row.iloc[0]) else ""
        en = str(row.iloc[2]).strip() if not pd.isna(row.iloc[2]) else ""
        is_break = (s in {"help","operator","post"} and (not ru and not en))  # empty tech lines
        if prev_s is None:
            cur = [int(i)]
        else:
            if s != prev_s or is_break:
                flush()
                cur = [int(i)]
            else:
                cur.append(int(i))
        prev_s = s
    flush()
    return scenes

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default="0")
    ap.add_argument("--out", default=str(ARTI_DIR / "scenes.json"))
    args = ap.parse_args()

    df = load_excel(args.excel, args.sheet)
    scenes = segment_dataframe(df)
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Scenes built: {len(scenes)}  (covered rows: {df.shape[0]})")
    print(f"[OK] Scenes saved to {outp}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
