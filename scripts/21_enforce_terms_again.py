
import argparse, pandas as pd, os, re
from glossary_utils import load_glossary, apply_longest_map, unguard_placeholders

def run(excel, sheet, glossary, out):
    pairs = load_glossary(glossary)
    df = pd.read_excel(excel, sheet_name=sheet)
    while df.shape[1] < 5:
        df[f"col{df.shape[1]}"] = ""
    col4 = df.columns[4]
    df[col4] = df[col4].astype(str).map(unguard_placeholders).map(lambda s: apply_longest_map(s, pairs))
    if out is None:
        out = excel
    df.to_excel(out, index=False)
    print(f"[OK] 21_enforce_terms_again -> {out}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default=0)
    ap.add_argument("--glossary", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    run(args.excel, args.sheet, args.glossary, args.out)
