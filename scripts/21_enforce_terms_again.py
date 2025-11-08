
import argparse, subprocess, sys

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Re-enforce terms after style pass")
    ap.add_argument("--excel", required=True)
    ap.add_argument("--name-map", required=True)
    ap.add_argument("--target-lang", default="zh-CN")
    ap.add_argument("--guard-by", default="BOTH", choices=["EN","RU","BOTH","NONE"])
    args, rest = ap.parse_known_args()
    cmd = [sys.executable, "scripts/20_enforce_terms.py", "--excel", args.excel, "--name-map", args.name_map, "--target-lang", args.target_lang, "--guard-by", args.guard_by]
    sys.exit(subprocess.call(cmd + rest))
