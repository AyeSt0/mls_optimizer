
"""
scripts/05_segment_context.py  (v3.1)
- Always part of one-click pipeline.
- Real-time progress prints (flush).
- Uses mls_optimizer.segment.segment_dataframe if available.
- Safe fallback segmenter if the above is missing.
- Writes artifacts/scenes.json (compatible with 12_llm_translate).
"""

import json
import argparse
from pathlib import Path

import pandas as pd

SYSTEM_SPEAKERS = {"system", "operator", "help", "post"}

def load_df(path, sheet):
    df = pd.read_excel(path, sheet_name=sheet)
    return df

def fallback_segment_dataframe(df, include_system=False):
    """
    A pragmatic scene segmenter:
    - New scene when a SYSTEM row appears (unless include_system) — system rows form their own small scenes.
    - New scene when encounter a fully blank line (ru & en empty).
    - Otherwise, contiguous dialogue stays in one scene.
    """
    scenes = []
    cur = []
    n = len(df)

    def flush_scene():
        nonlocal cur, scenes
        if cur:
            scenes.append({"id": len(scenes), "rows": cur})
            cur = []

    for i in range(n):
        if i % 500 == 0 and i > 0:
            print(f"[PROG] segment: {i}/{n} ({i/n:.1%})", flush=True)

        speaker = str(df.iloc[i, 1]).strip().lower() if df.shape[1] >= 2 else ""
        ru = str(df.iloc[i, 0]).strip() if df.shape[1] >= 1 else ""
        en = str(df.iloc[i, 2]).strip() if df.shape[1] >= 3 else ""

        is_blank = (not ru) and (not en)
        is_system = speaker in SYSTEM_SPEAKERS

        # system -> separate scene unless include_system
        if is_system and not include_system:
            flush_scene()
            scenes.append({"id": len(scenes), "rows": [i], "meta": {"system": True}})
            flush_scene()
            continue

        # blank -> scene boundary
        if is_blank:
            flush_scene()
            continue

        # normal dialogue
        cur.append(i)

    flush_scene()
    return scenes

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default=0)
    ap.add_argument("--out", default="artifacts/scenes.json")
    ap.add_argument("--include-system", action="store_true", help="Include system/operator/help/post inside scenes")
    args = ap.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    out_path = project_root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] reading: {args.excel}", flush=True)
    df = load_df(args.excel, args.sheet)
    print(f"[INFO] rows: {len(df)}", flush=True)

    scenes = None
    try:
        # Prefer project segmenter if available
        print("[INFO] using mls_optimizer.segment.segment_dataframe", flush=True)
        from mls_optimizer.segment import segment_dataframe as seg_df
        scenes = seg_df(df, {"include_system": args.include_system})
    except Exception as e:
        print(f"[WARN] fallback segmenter due to: {e}", flush=True)
        scenes = fallback_segment_dataframe(df, include_system=args.include_system)

    # Sanity and summary
    if not isinstance(scenes, list):
        print("[WARN] bad scenes shape, forcing empty list", flush=True)
        scenes = []

    total_rows = sum(len(s.get("rows", [])) for s in scenes)
    print(f"[OK] Scenes built: {len(scenes)}  (covered rows: {total_rows})", flush=True)

    payload = {"scenes": scenes}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Scenes saved to {out_path.as_posix()}", flush=True)

if __name__ == "__main__":
    main()
