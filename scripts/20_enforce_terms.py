
import argparse, pandas as pd, os, json, re
from glossary_utils import load_glossary, apply_longest_map, guard_placeholders

def run(excel, sheet, glossary, overwrite, out):
    pairs = load_glossary(glossary)
    df = pd.read_excel(excel, sheet_name=sheet)
    # col map: 0 RU, 1 EN, 2 speaker, 3 EN-mixed, 4 zh
    while df.shape[1] < 5:
        df[f"col{df.shape[1]}"] = ""

    # seed col4 from col3 if overwrite or col4 empty
    col3 = df.columns[3]; col4 = df.columns[4]
    def seed_row(v3, v4):
        if overwrite or (pd.isna(v4) or str(v4).strip()==""):
            return v3
        return v4
    df[col4] = [seed_row(df.iloc[i,3], df.iloc[i,4] if i < len(df) else "") for i in range(len(df))]

    # apply glossary & guard placeholders
    df[col4] = df[col4].astype(str).map(lambda s: guard_placeholders(apply_longest_map(s, pairs)))

    if out is None:
        out = excel
    df.to_excel(out, index=False)
    print(f"[OK] 20_enforce_terms -> {out}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default=0)
    ap.add_argument("--glossary", required=True)
    ap.add_argument("--overwrite", action="store_true", help="seed col4 from col3 even if col4 already has text")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    run(args.excel, args.sheet, args.glossary, args.overwrite, args.out)
