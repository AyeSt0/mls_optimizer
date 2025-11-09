
import argparse, json, os, re
import pandas as pd

KEYWORDS = ("CLASS","OFFICE","ROOM","HALL","GYM","POOL","LIBRARY","ENTRANCE","LOCKER","TOILET","CHANGING","COLLEGE","LAB","CABINET","STAFF")

def looks_like_location_label(text:str)->bool:
    if not isinstance(text,str): return False
    t = text.strip()
    if not t: return False
    # short label & mostly uppercase or title-ish
    if len(t) <= 30 and (t.isupper() or any(k in t.upper() for k in KEYWORDS)):
        return True
    return False

def load_excel(path, sheet=None, sheet_index=0):
    if sheet is not None:
        df = pd.read_excel(path, sheet_name=sheet)
    else:
        df = pd.read_excel(path, sheet_name=sheet_index)
    # Expect 4 columns at least
    df = df.copy()
    while df.shape[1] < 5:
        df[df.shape[1]] = ""
    return df

def build_scenes(df):
    # Columns: 0=RU, 1=Speaker, 2=EN, 3=CN(old), 4=CN(new)
    scenes = []
    start = 0
    N = len(df)
    for i in range(N):
        speaker = str(df.iat[i,1]) if i < N else ""
        en = str(df.iat[i,2]) if i < N else ""
        # boundary if a location-ish label row by 'string' speaker
        if i>start and (speaker.lower()=="string" and looks_like_location_label(en)):
            scenes.append({"start":start,"end":i-1})
            start = i
    if start < N:
        scenes.append({"start":start,"end":N-1})
    return scenes

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet-name", default=None)
    ap.add_argument("--sheet-index", type=int, default=0)
    ap.add_argument("--out", default="artifacts/scenes.json")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    df = load_excel(args.excel, args.sheet_name, args.sheet_index)
    scenes = build_scenes(df)
    with open(args.out,"w",encoding="utf-8") as f:
        json.dump({"scenes":scenes, "rows":len(df)}, f, ensure_ascii=False, indent=2)
    print(f"[OK] Scenes built: {len(scenes)}  (covered rows: {len(df)})")
    print(f"[OK] Scenes saved to {os.path.abspath(args.out)}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
