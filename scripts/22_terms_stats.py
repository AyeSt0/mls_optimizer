
import argparse, json, pandas as pd, re
from mls_optimizer.io_utils import load_excel, save_excel
from mls_optimizer.config import OptimConfig

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Term hit dashboard (rough)")
    ap.add_argument("--excel", required=True)
    ap.add_argument("--name-map", required=True)
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--out", default="artifacts/terms_stats.xlsx")
    args = ap.parse_args()

    cfg = OptimConfig()
    df = load_excel(args.excel, args.sheet)
    with open(args.name_map, "r", encoding="utf-8") as f:
        nm = json.load(f)

    rows = []
    terms = nm.keys() if isinstance(nm, dict) else [x.get("src") for x in nm if isinstance(x, dict) and x.get("src")]
    for k in terms:
        en_hits = df.iloc[:, cfg.col_en].astype(str).str.contains(re.escape(k), na=False).sum()
        out_hits = df.iloc[:, cfg.col_out].astype(str).str.contains("", na=False).sum()  # placeholder metric
        rows.append({"term": k, "en_hits": en_hits, "out_hits(rough)": out_hits})
    rep = pd.DataFrame(rows)
    save_excel(rep, args.out)
    print("[OK] Term stats ->", args.out)
