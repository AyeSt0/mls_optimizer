
import argparse, pandas as pd
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    args = ap.parse_args()
    x = pd.ExcelFile(args.excel)
    for i, name in enumerate(x.sheet_names):
        print(f"{i}\t{name}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
