
import json, re
from typing import Dict, List, Tuple

_ZWJ = "\u200d"  # zero width joiner (used to guard placeholders)

PLACEHOLDER_PAT = re.compile(r"(\{\{.*?\}\}|\{.*?\}|\[.*?\]|<.*?>)")

def load_glossary(path: str) -> List[Tuple[str, str]]:
    """
    Load name_map/glossary file in flexible formats.
    Returns list of (src, dst) pairs sorted by src length desc (longest match first).
    Supported structures:
      - {"en2zh": {"Professor Richardson": "理查森教授", "Richardson":"理查森", ...}}
      - {"map":[{"src":"Professor Richardson","dst":"理查森教授"}, ...]}
      - flat dict: {"Professor Richardson":"理查森教授", "Richardson":"理查森"}
    """
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    pairs = []
    if isinstance(obj, dict):
        if "en2zh" in obj and isinstance(obj["en2zh"], dict):
            for k, v in obj["en2zh"].items():
                pairs.append((str(k), str(v)))
        elif "map" in obj and isinstance(obj["map"], list):
            for it in obj["map"]:
                if isinstance(it, dict) and "src" in it and "dst" in it:
                    pairs.append((str(it["src"]), str(it["dst"])))
        else:
            # assume flat dict
            for k, v in obj.items():
                if isinstance(v, str):
                    pairs.append((str(k), v))
    # longest match first
    pairs.sort(key=lambda kv: len(kv[0]), reverse=True)
    return pairs

def apply_longest_map(text: str, pairs: List[Tuple[str, str]]) -> str:
    for src, dst in pairs:
        # word boundary is unsafe for names, do plain replace but avoid overlapping by using regex escape
        pattern = re.escape(src)
        text = re.sub(pattern, dst, text)
    return text

def guard_placeholders(text: str) -> str:
    """
    Insert ZWJ around placeholders so LLM is less likely to alter them.
    It is visually identical.
    """
    def _wrap(m):
        s = m.group(1)
        if _ZWJ in s:
            return s
        return _ZWJ + s + _ZWJ
    return PLACEHOLDER_PAT.sub(_wrap, text)

def unguard_placeholders(text: str) -> str:
    return text.replace(_ZWJ, "")

def inject_glossary_prompt(pairs: List[Tuple[str, str]], max_items: int = 300) -> str:
    """
    Build a compact glossary instruction block for the system prompt.
    """
    items = pairs[:max_items]
    lines = [f"- {src} → {dst}" for src, dst in items]
    block = "\n".join(lines)
    return f"Glossary (strict, longest match first):\n{block}\n"
