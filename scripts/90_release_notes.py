
import argparse, os, datetime as dt
from mls_optimizer.io_utils import load_excel

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate release notes")
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--qa", required=False)
    ap.add_argument("--out", default="artifacts/release_notes.md")
    args = ap.parse_args()

    a = load_excel(args.after)
    rows, cols = a.shape

    issues = "N/A"
    if args.qa and os.path.exists(args.qa):
        q = load_excel(args.qa)
        try:
            issues = str(int(q["has_issue"].sum()))
        except Exception:
            pass

    md = []
    md.append("# Localization Release Notes\n")
    md.append(f"- Date: {dt.datetime.utcnow().isoformat()}Z\n")
    md.append(f"- Rows x Cols (after): {rows} x {cols}\n")
    md.append(f"- QA Issues: {issues}\n")
    md.append("\n## Highlights\n- Context-aware translation\n- Term consistency with regex/morph guard\n- QA checks on placeholders/links/numbers/length\n")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("".join(md))
    print("[OK] Release notes ->", args.out)
