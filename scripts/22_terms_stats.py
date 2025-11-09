
import argparse, json, pandas as pd, os, re
from collections import Counter

def load_glossary(path):
    data = json.load(open(path,encoding="utf-8"))
    keys = []
    if isinstance(data, dict):
        keys.extend(list(data.keys()))
        for v in data.values():
            if isinstance(v, dict):
                src = v.get("src") or v.get("en")
                if src: keys.append(src)
    elif isinstance(data, list):
        for it in data:
            if isinstance(it, dict):
                src = it.get("src") or it.get("en") or it.get("key")
                if src: keys.append(src)
    # unique, sort by len desc
    keys = sorted(set([k for k in keys if k]), key=len, reverse=True)
    return keys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default=0)
    ap.add_argument("--glossary", default="data/name_map.json")
    ap.add_argument("--out", default="artifacts/terms_stats.csv")
    args = ap.parse_args()
    df = pd.read_excel(args.excel, sheet_name=args.sheet)
    while df.shape[1] < 5:
        df[df.shape[1]] = ""
    keys = load_glossary(args.glossary)
    cnt = Counter()
    for s in df.iloc[:,4].astype(str):
        t = s or ""
        for k in keys:
            if k and k in t:
                cnt[k]+=1
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    pd.DataFrame([{"term":k,"hits":v} for k,v in cnt.most_common()]).to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"[OK] terms stats -> {os.path.abspath(args.out)}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
