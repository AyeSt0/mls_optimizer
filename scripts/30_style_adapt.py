
import argparse, pandas as pd, os, re

PUNCT_MAP = {
    "...":"…","....":"…","..":"…",
    ",":"，",":":"：",";":"；","?":"？","!":"！",
    "(": "（", ")":"）","[":"[","]":"]"
}

def tidy(s:str)->str:
    if not isinstance(s,str): return s
    t = s
    # punctuation normalize
    for k,v in PUNCT_MAP.items():
        t = t.replace(k,v)
    # remove double spaces
    t = re.sub(r"\s{2,}"," ",t)
    # Chinese spacing cleanup
    t = re.sub(r"\s+([，。：；！？）])", r"\1", t)
    t = re.sub(r"（\s+", "（", t)
    return t.strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default=0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    df = pd.read_excel(args.excel, sheet_name=args.sheet)
    while df.shape[1] < 5:
        df[df.shape[1]] = ""
    for i in range(len(df)):
        out = df.iat[i,4]
        if pd.isna(out) or not out:
            continue
        df.iat[i,4] = tidy(str(out))
    out_path = args.out or args.excel
    with pd.ExcelWriter(out_path, engine="openpyxl", mode="w", if_sheet_exists="replace") as w:
        df.to_excel(w, index=False, sheet_name=str(args.sheet))
    print(f"[OK] style adapted -> {os.path.abspath(out_path)}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
