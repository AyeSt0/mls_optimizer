
import json, re
from typing import Dict, List, Tuple, Optional
from .protect import _compile_boundary_regex

def _norm_lang(s: Optional[str]) -> str:
    return s.strip() if s else ""

def load_name_map(path: str, target_lang: str = "zh-CN") -> Dict[str,dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    t = _norm_lang(target_lang) or "zh-CN"
    out: Dict[str,dict] = {}

    def _add(src: str, dst: str, regex: bool=False, morph: Optional[str]=None):
        if not regex and morph == "ru-simple":
            patt = r"%s(а|я|у|ю|ом|ем|е|ы|и)?" % re.escape(src)
            out[src] = {"dst": dst, "regex": True, "pattern": re.compile(patt)}
            return
        if regex:
            out[src] = {"dst": dst, "regex": True, "pattern": re.compile(src)}
        else:
            patt = _compile_boundary_regex(src)
            out[src] = {"dst": dst, "regex": True, "pattern": patt}

    if isinstance(data, dict):
        for k, v in data.items():
            if v is None: continue
            _add(str(k), str(v), regex=False)
        return out
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict): continue
            src = item.get("src") or item.get("en") or item.get("from")
            if not src: continue
            regex = bool(item.get("regex"))
            morph = item.get("morph")
            dst = None
            if "map" in item and isinstance(item["map"], dict):
                val = item["map"].get(t)
                if val: dst = str(val)
            else:
                cand = item.get("dst") or item.get("zh") or item.get(t)
                lang = _norm_lang(item.get("lang"))
                if cand and (not lang or lang == t):
                    dst = str(cand)
            if dst:
                _add(str(src), dst, regex=regex, morph=morph)
        return out
    raise ValueError("Unsupported name_map structure.")

def longest_first_pairs(mapping: Dict[str,dict]) -> List[Tuple[str,dict]]:
    return sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True)

def enforce_terms(text: str, en_text: str, ru_text: str, term_pairs: List[Tuple[str,dict]], guard_by: str="EN"):
    guard_by = (guard_by or "EN").upper()
    changes = []
    out = text
    mp = {k:v for k,v in term_pairs}

    def ok(src: str):
        if guard_by == "NONE": return True
        patt = mp[src]["pattern"]
        if guard_by == "EN":
            return bool(en_text and patt.search(en_text))
        if guard_by == "RU":
            return bool(ru_text and patt.search(ru_text))
        if guard_by == "BOTH":
            a = bool(en_text and patt.search(en_text))
            b = bool(ru_text and patt.search(ru_text))
            return a or b
        return True

    for src, meta in term_pairs:
        if not ok(src): continue
        patt = meta["pattern"]
        if patt.search(out):
            out = patt.sub(meta["dst"], out)
            changes.append(f'{src}->{meta["dst"]}')
    return out, changes

def build_glossary_lines(term_pairs: List[Tuple[str,dict]], max_items: int = 300) -> str:
    lines = []
    count = 0
    for src, meta in term_pairs:
        dst = meta.get("dst")
        if not dst: continue
        # keep short list to avoid exploding tokens
        lines.append(f"- {src} -> {dst}")
        count += 1
        if count >= max_items:
            break
    return "\n".join(lines)
