
from typing import List, Dict
import pandas as pd
from .config import OptimConfig

def _fmt_line(idx: int, ru: str, en: str, spk: str) -> str:
    ru = ru or ""
    en = en or ""
    spk = spk or ""
    return f"[{idx}] speaker={spk}\nRU: {ru}\nEN: {en}"

def build_window_context(df: pd.DataFrame, i: int, cfg: OptimConfig, k: int = 2) -> Dict[str, str]:
    n = len(df)
    start = max(0, i - k)
    end = min(n, i + k + 1)
    blocks = []
    for j in range(start, end):
        if j == i: continue
        row = df.iloc[j]
        ru = "" if pd.isna(row.iloc[cfg.col_ru]) else str(row.iloc[cfg.col_ru])
        en = "" if pd.isna(row.iloc[cfg.col_en]) else str(row.iloc[cfg.col_en])
        spk = "" if pd.isna(row.iloc[cfg.col_speaker]) else str(row.iloc[cfg.col_speaker])
        blocks.append(_fmt_line(j, ru, en, spk))
    return {"window_context": "\n\n".join(blocks)}

def build_scene_context(df: pd.DataFrame, rows: List[int], cfg: OptimConfig) -> List[Dict[str, str]]:
    packs = []
    for i in rows:
        row = df.iloc[i]
        ru = "" if pd.isna(row.iloc[cfg.col_ru]) else str(row.iloc[cfg.col_ru])
        en = "" if pd.isna(row.iloc[cfg.col_en]) else str(row.iloc[cfg.col_en])
        spk = "" if pd.isna(row.iloc[cfg.col_speaker]) else str(row.iloc[cfg.col_speaker])
        packs.append({"row": i, "ru": ru, "en": en, "speaker": spk})
    return packs
