
import os
import pandas as pd

def load_excel(path: str, sheet=None) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet)
    # Auto-pick first sheet if multiple returned
    if isinstance(df, dict):
        # preserve file's sheet order if available
        first_key = next(iter(df.keys()))
        df = df[first_key]
    return df

def save_excel(df: pd.DataFrame, path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_excel(path, index=False)
