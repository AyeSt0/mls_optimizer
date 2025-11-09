
import argparse, pandas as pd, json, os

def run(excel, sheet, out):
    df = pd.read_excel(excel, sheet_name=sheet)
    # simple segmenter: split when speaker changes to 'string' (likely map/UI) or blank lines
    scenes = []
    cur = {"rows":[]}
    prev_spk = None
    for i in range(len(df)):
        spk = str(df.iloc[i,2]) if i < len(df) else ""
        if prev_spk is not None and (spk == "string" or spk != prev_spk):
            if cur["rows"]:
                scenes.append(cur); cur = {"rows":[]}
        cur["rows"].append(i)
        prev_spk = spk
    if cur["rows"]:
        scenes.append(cur)
    if out is None:
        out = "artifacts/scenes.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"count":len(scenes), "scenes": scenes}, f, ensure_ascii=False, indent=2)
    print(f"[OK] Scenes built: {len(scenes)}  (covered rows: {len(df)})")
    print(f"[OK] Scenes saved to {os.path.abspath(out)}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet-index", type=int, default=0)
    ap.add_argument("--out", default="artifacts/scenes.json")
    args = ap.parse_args()
    run(args.excel, args.sheet_index, args.out)
