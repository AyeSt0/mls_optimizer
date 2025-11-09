#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
glossary_utils.py — load & apply glossary / name-map with longest-match-first.
Glossary JSON supports several shapes:
1) {"en2zh": {"Sunville":"阳光镇", "College":"学院", ...}, "protect": ["[mcname]","[mcsurname]"]}
2) [{"src":"Sunville","dst":"阳光镇"}, {"src":"College Entrance","dst":"学院正门"}]
3) {"Sunville":"阳光镇","College Entrance":"学院正门"}  # default mapping (assumed EN->ZH)

We build a single list of (pattern, replacement) in descending length for longest-match-first apply.
We also protect placeholder-like tokens by skipping replacements inside brackets if needed.
"""

import json, re
from typing import Dict, List, Tuple, Any

PLACEHOLDER_RE = re.compile(r"(\[[^\]]+\]|\{[^}]+\}|\{\{[^}]+\}\}|<[^>]+>)")

def load_glossary(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

def _flatten_pairs(data: Any) -> Dict[str, str]:
    # Try to normalize various glossary shapes into {src: dst}
    if isinstance(data, dict):
        # common patterns
        if "en2zh" in data and isinstance(data["en2zh"], dict):
            return dict(data["en2zh"])
        # plain mapping
        return dict(data)
    elif isinstance(data, list):
        out = {}
        for item in data:
            if isinstance(item, dict) and "src" in item and "dst" in item:
                out[str(item["src"])] = str(item["dst"])
        return out
    return {}

def build_longest_rules(glossary: Dict[str, Any], key: str = None) -> List[Tuple[re.Pattern, str]]:
    """
    Build [(regex, replacement)] list sorted by src len desc.
    If `key` is provided (e.g., "en2zh"), try that sub-map first.
    """
    mapping = {}
    if key and key in glossary:
        mapping = _flatten_pairs(glossary[key])
    else:
        mapping = _flatten_pairs(glossary)
    # Drop empties
    mapping = {k: v for k, v in mapping.items() if k and v}
    # Sort by length desc for longest-match-first
    items = sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True)
    rules = []
    for src, dst in items:
        # escape regex special chars; match whole-word-ish with boundary fallback
        pat = re.escape(src)
        # Don't force word boundaries (English & UI labels often not word-delimited)
        rx = re.compile(pat)
        rules.append((rx, dst))
    return rules

def apply_rules(text: str, rules: List[Tuple[re.Pattern, str]]) -> str:
    """Apply rules outside placeholder spans. Placeholders are kept intact."""
    if not text:
        return text
    # Split by placeholders to avoid rewriting them
    parts = PLACEHOLDER_RE.split(text)
    # parts alternates: text, placeholder, text, placeholder...
    for i in range(0, len(parts), 2):  # only non-placeholder segments
        seg = parts[i]
        if not seg:
            continue
        for rx, repl in rules:
            seg = rx.sub(repl, seg)
        parts[i] = seg
    return "".join(parts)

def protect_tokens(text: str, protect_list: List[str]) -> str:
    """Optionally wrap protected tokens with zero-width markers to reduce model changes (heuristic)."""
    if not text or not protect_list:
        return text
    safe = text
    for tok in sorted(set(protect_list), key=len, reverse=True):
        if not tok:
            continue
        safe = safe.replace(tok, f"\u2063{tok}\u2063")  # INVISIBLE SEPARATOR around token
    return safe

def strip_protect(text: str) -> str:
    if not text:
        return text
    return text.replace("\u2063", "")
