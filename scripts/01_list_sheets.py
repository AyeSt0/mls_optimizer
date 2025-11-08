
import argparse, pandas as pd
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    args = ap.parse_args()
    x = pd.ExcelFile(args.excel)
    print(x.sheet_names)
