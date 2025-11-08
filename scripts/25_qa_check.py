#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
25_qa_check.py — QA report for col5
Checks: placeholders, links/@/#, numbers, length ratio, empty lines.
Outputs: artifacts/qa_report.json
"""
import argparse, json, re
from pathlib import Path
import pandas as pd

ARTI_DIR = Path(__file__).resolve().parent.parent / "artifacts"
ARTI_DIR.mkdir(parents=True, exist_ok=True)

VAR_RE = re.compile(r"(\[[^\]]+\]|{[^}]+}|<[^>]+>|{{[^}]+}})")
LINK_RE = re.compile(r"(https?://\S+|@[A-Za-z0-9_]+|#[^\s#]+)")
NUM_RE = re.compile(r"\d+")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default="0")
    ap.add_argument("--out", default=str(ARTI_DIR/"qa_report.json"))
    args = ap.parse_args()

    df = pd.read_excel(args.excel, sheet_name=args.sheet)
    while df.shape[1] < 5: df[f"col_{df.shape[1]}"] = ""

    issues = []
    for i in range(df.shape[0]):
        en = str(df.iloc[i,2]) if pd.notna(df.iloc[i,2]) else ""
        zh = str(df.iloc[i,4]) if pd.notna(df.iloc[i,4]) else ""
        if not zh.strip():
            issues.append({"row": i, "type": "empty_output"}); continue

        # placeholders parity
        en_vars = VAR_RE.findall(en)
        zh_vars = VAR_RE.findall(zh)
        if set(en_vars) - set(zh_vars):
            issues.append({"row": i, "type": "placeholder_mismatch", "en": en_vars, "zh": zh_vars})

        # link/@/# parity
        en_link = bool(LINK_RE.search(en))
        zh_link = bool(LINK_RE.search(zh))
        if en_link and not zh_link:
            issues.append({"row": i, "type": "link_missing_in_zh"})

        # number parity
        en_nums = NUM_RE.findall(en)
        zh_nums = NUM_RE.findall(zh)
        if len(en_nums) != len(zh_nums):
            issues.append({"row": i, "type": "number_count_diff", "en": en_nums, "zh": zh_nums})

        # length ratio
        if len(en) > 0:
            ratio = len(zh)/max(1, len(en))
            if ratio < 0.4 or ratio > 3.5:
                issues.append({"row": i, "type": "length_ratio_suspect", "ratio": round(ratio,2)})

    Path(args.out).write_text(json.dumps({"file": args.excel, "issues": issues}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] QA done. Issues: {len(issues)}")
    print(f"Output -> {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
