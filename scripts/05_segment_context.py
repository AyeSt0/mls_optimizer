
import argparse, json, os
import pandas as pd

def main():
    p = argparse.ArgumentParser(description="Segment MLS excel into scenes.json")
    p.add_argument("--excel", required=True, help="Path to Excel file")
    p.add_argument("--sheet-index", type=int, default=0, help="0-based sheet index (default 0)")
    p.add_argument("--sheet-name", type=str, default=None, help="Sheet name (overrides --sheet-index)")
    p.add_argument("--out", type=str, default="artifacts/scenes.json", help="Output scenes json")
    args = p.parse_args()

    sheet = args.sheet_name if args.sheet_name else args.sheet_index

    # Read excel
    df = pd.read_excel(args.excel, sheet_name=sheet, header=None)
    # Expected columns:
    # 0: RU, 1: speaker, 2: EN, 3: ZH (current), 4: target (will be written later)
    # We will build very light scenes by contiguous speaker blocks (string/system will break)
    scenes = []
    cur = {"start": 0, "end": 0}
    def is_break(spk):
        # treat system/strings as separators of scenes
        return str(spk).strip().lower() in ("string", "system", "post", "help")

    last_break = 0
    for i in range(len(df)):
        spk = df.iat[i,1] if df.shape[1] > 1 else ""
        if is_break(spk) and i>last_break:
            scenes.append({"start": int(last_break), "end": int(i-1)})
            last_break = i
    # tail
    if last_break < len(df):
        scenes.append({"start": int(last_break), "end": int(len(df)-1)})

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"scenes": scenes}, f, ensure_ascii=False, indent=2)
    print(f"[OK] Scenes built: {len(scenes)}  (covered rows: {len(df)})")
    print(f"[OK] Scenes saved to {os.path.abspath(args.out)}")

if __name__ == "__main__":
    raise SystemExit(main())
