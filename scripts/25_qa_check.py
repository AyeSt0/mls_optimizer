
import argparse, pandas as pd, os, re, csv

PLACEHOLDER_RE = re.compile(r"(\[[^\]]+\]|\{\{?[^}]+\}?\}|<[^>]+>)")
URL_RE = re.compile(r"https?://\S+")
AT_RE = re.compile(r"(^|[^A-Za-z0-9_])@[A-Za-z0-9_]+")
HASH_RE = re.compile(r"(?:^|\s)#\w+")

def count_tokens(s):
    return len(re.findall(r"\w+|[^\w\s]", s or ""))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default=0)
    ap.add_argument("--out", default="artifacts/qa_report.csv")
    args = ap.parse_args()
    df = pd.read_excel(args.excel, sheet_name=args.sheet)
    while df.shape[1] < 5:
        df[df.shape[1]] = ""
    rows = []
    for i in range(len(df)):
        ru = str(df.iat[i,0]) if pd.notna(df.iat[i,0]) else ""
        en = str(df.iat[i,2]) if pd.notna(df.iat[i,2]) else ""
        out = str(df.iat[i,4]) if pd.notna(df.iat[i,4]) else ""
        issues = []
        # placeholder parity
        src_ph = set(PLACEHOLDER_RE.findall(ru+" "+en))
        out_ph = set(PLACEHOLDER_RE.findall(out))
        miss = src_ph - out_ph
        if miss:
            issues.append(f"missing placeholders: {','.join(sorted(miss))}")
        # urls/@/# copied?
        if URL_RE.search(ru+en) and not URL_RE.search(out):
            issues.append("url lost")
        if AT_RE.search(ru+en) and not AT_RE.search(out):
            issues.append("@ mention lost")
        if HASH_RE.search(ru+en) and not HASH_RE.search(out):
            issues.append("#tag lost")
        # digit counts
        src_digits = re.findall(r"\d+", ru+en)
        out_digits = re.findall(r"\d+", out)
        if sorted(src_digits) != sorted(out_digits):
            issues.append(f"digits mismatch src={src_digits} out={out_digits}")
        # length ratio
        if en:
            ratio = len(out)/max(1,len(en))
            if ratio<0.4 or ratio>2.5:
                issues.append(f"length ratio abnormal {ratio:.2f}")
        if issues:
            rows.append({"row":i+1,"issues":"; ".join(issues),"en":en,"out":out})
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    pd.DataFrame(rows).to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"[OK] QA report -> {os.path.abspath(args.out)}  (problems: {len(rows)})")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
