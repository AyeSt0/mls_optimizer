
import yaml, os, re

def load_punct_map(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

def apply_punct_map(text: str, mapping: dict) -> str:
    out = text
    for k, v in (mapping.get("replace") or {}).items():
        out = out.replace(k, v)
    if mapping.get("normalize_ellipsis_to"):
        out = re.sub(r"\.\.\.|…{1,3}", mapping["normalize_ellipsis_to"], out)
    return out
