
import argparse, os
from tqdm import tqdm
import pandas as pd
from mls_optimizer.io_utils import load_excel, save_excel
from mls_optimizer.config import OptimConfig

def row_issues(ru, en, zh):
    issues = []
    # variables / placeholders
    for tok in ["[mcname]", "[mcsurname]", "mcname", "{{mcname}}", "{{var}}", "[var]", "<tag>"]:
        if tok in en and tok not in zh:
            issues.append(f"missing placeholder {tok}")
    # links / handles / numbers consistency (very light)
    import re
    en_nums = re.findall(r"\d+", en or "")
    for num in en_nums:
        if num not in (zh or ""):
            issues.append(f"num {num} mismatch")
    return "; ".join(issues)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="QA check (lightweight) with progress")
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    df = load_excel(args.excel, args.sheet)
    cfg = OptimConfig()

    rows = []
    from tqdm import tqdm
    for i in tqdm(range(len(df)), desc="QA"):
        row = df.iloc[i]
        ru = "" if pd.isna(row.iloc[cfg.col_ru]) else str(row.iloc[cfg.col_ru])
        en = "" if pd.isna(row.iloc[cfg.col_en]) else str(row.iloc[cfg.col_en])
        zh = "" if pd.isna(row.iloc[cfg.col_out]) else str(row.iloc[cfg.col_out])
        issues = row_issues(ru, en, zh)
        if issues:
            rows.append({"row": i, "issues": issues, "en": en, "zh": zh})

    outdf = pd.DataFrame(rows, columns=["row","issues","en","zh"])
    save_excel(outdf, args.out)
    print(f"[OK] QA report -> {args.out} (rows={len(outdf)})")
