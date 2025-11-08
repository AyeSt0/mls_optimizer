
import pandas as pd
from typing import List
from .config import OptimConfig

SYSTEM_LIKE = {"help","operator","post","unknown","unknown_woman","showman"}  # can extend by project

def _cfg_get(cfg, key, default=None):
    # dot access preferred
    if hasattr(cfg, key):
        return getattr(cfg, key)
    # dict fallback
    if isinstance(cfg, dict):
        return cfg.get(key, default)
    return default

def is_system_row(speaker: str) -> bool:
    if not speaker: return False
    s = str(speaker).strip().lower()
    return s in SYSTEM_LIKE

def segment_dataframe(df: pd.DataFrame, cfg: OptimConfig, include_system_in_scene: bool = False) -> List[List[int]]:
    scenes: List[List[int]] = []
    cur: List[int] = []
    for i, row in df.iterrows():
        spk = "" if pd.isna(row.iloc[cfg.col_speaker]) else str(row.iloc[cfg.col_speaker])
        sysline = is_system_row(spk)
        if sysline and not include_system_in_scene:
            if cur:
                scenes.append(cur); cur = []
            continue
        if sysline and include_system_in_scene:
            if cur:
                scenes.append(cur); cur = []
            scenes.append([i])
            continue
        # non-system dialogue
        cur.append(i)
        # if too long, cut scene to avoid huge prompts
        if len(cur) >= 40:
            scenes.append(cur); cur = []
    if cur: scenes.append(cur)
    return scenes
