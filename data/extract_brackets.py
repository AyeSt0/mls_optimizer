#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Excel 第三列提取括号变量（支持 [] / ［］ / [[ ]] 变体），去重保留括号本体，写入新表。
可选 --all-cols 扫描所有列用于排查。
"""

import re
import argparse
from pathlib import Path
import pandas as pd

# 1) [[name]]  2) [name]  3) ［［name］］  4) ［name］
COMBINED_PATTERN = re.compile(
    r"(\[\[[^\]]+\]\]|\[[^\[\]]+\]|［［[^］]+］］|［[^］]+］)"
)

def gather_matches_from_series(s: pd.Series) -> list[str]:
    out = []
    for val in s.dropna():
        text = str(val)
        out.extend(COMBINED_PATTERN.findall(text))
    return out

def main():
    parser = argparse.ArgumentParser(description="Extract unique bracketed tokens from Excel.")
    parser.add_argument("input", help="输入文件路径，如 MLS Chinese.xlsx")
    parser.add_argument("--sheet", default=0, help="工作表名或索引，默认0（第一个表）")
    parser.add_argument("--output", default=None, help="输出文件路径，默认同目录 *_brackets.xlsx")
    parser.add_argument("--all-cols", action="store_true", help="扫描所有列（用于排查列错位）")
    args = parser.parse_args()

    src = Path(args.input).expanduser().resolve()
    out = Path(args.output).expanduser().resolve() if args.output else src.with_name(f"{src.stem}_brackets.xlsx")

    # 强制按原样读取，不推断表头
    df = pd.read_excel(src, sheet_name=args.sheet, header=None, dtype=str, engine="openpyxl")

    if not args.all_cols and df.shape[1] < 3:
        raise ValueError("源文件列数不足3列，无法读取第三列。你也可以加 --all-cols 做一次兜底扫描。")

    # 收集匹配
    if args.all_cols:
        matches = []
        col_hit_stats = []
        for i in range(df.shape[1]):
            col_matches = gather_matches_from_series(df.iloc[:, i])
            col_hit_stats.append((i + 1, len(col_matches)))  # 1-based 列号
            matches.extend(col_matches)
    else:
        third_col = df.iloc[:, 2]  # 第三列（0-based 2）
        matches = gather_matches_from_series(third_col)
        col_hit_stats = [(3, len(matches))]

    unique = sorted(set(matches), key=lambda x: (x.replace("［","[").replace("］","]"), x))

    # 写出结果
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        pd.DataFrame({"Bracketed": unique}).to_excel(writer, sheet_name="Bracketed", index=False)

        # 诊断信息：各列命中数、总览
        diag_rows = []
        total = 0
        for col_idx, hits in col_hit_stats:
            diag_rows.append({"Column": col_idx, "Hits": hits})
            total += hits
        diag_df = pd.DataFrame(diag_rows)
        summary_df = pd.DataFrame(
            {
                "Metric": ["TotalMatches", "UniqueTokens", "ScannedColumns", "Mode"],
                "Value": [total, len(unique), df.shape[1] if args.all_cols else 1, "all-cols" if args.all_cols else "third-col"],
            }
        )
        diag_df.to_excel(writer, sheet_name="Diagnostics", index=False, startrow=0)
        summary_df.to_excel(writer, sheet_name="Diagnostics", index=False, startrow=len(diag_df)+2)

    print(f"✅ 提取完成，共 {len(unique)} 个唯一条目。已写入：{out}")

if __name__ == "__main__":
    main()
