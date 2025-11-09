# -*- coding: utf-8 -*-
"""
20_enforce_terms.py
作用：读取 Excel（第1列RU / 第2列speaker / 第3列EN / 第4列CN待优化 / 第5列LLM结果），
以【第3列(EN)】为基准，进行术语“预占位”和保护性替换，写入【第4列】，
给 LLM 当“带中文守护的英文底稿”（LLM 在 prompt 里会被要求不修改已存在的中文和占位符）。

- 术语（最长匹配优先）：把人名地名机构名等预替成目标中文
- 品牌名：强制保持拉丁文
- 占位符修正：把 { mcname } / <mcname> / {{ mcname }} / {[]} 等统一为 [mcname] 等规范
- 不动第1~3列；默认若第4列已有内容且未开启 --overwrite，不覆盖
- 输出默认另存为 *.guard.xlsx（可用 --out 指定）
"""

import argparse, os, re, sys, json, time
import pandas as pd
from typing import Dict, List, Tuple

TARGET_COL_INDEX = 3  # 第4列 0-based
EN_COL_INDEX = 2      # 第3列 0-based

# —— 品牌保持拉丁 ——（可继续扩展）
BRAND_LATIN_MAP = {
    "帕特伦": "Patreon",
    "爱发电": "Patreon",
    "Ins": "Instagram",
    "ins": "Instagram",
    "Instagram": "Instagram",
    "罗嗨斯": "Lovense",
    "洛芬斯": "Lovense",
    "Lovense": "Lovense",
}

KNOWN_VARS = {"mcname", "mcsurname", "mc_surname"}
CANONICAL_BRACKETS = "square"  # square|curly|angle|double_curly

def canonical_wrap(v: str) -> str:
    if CANONICAL_BRACKETS == "square": return f"[{v}]"
    if CANONICAL_BRACKETS == "curly": return f"{{{v}}}"
    if CANONICAL_BRACKETS == "angle": return f"<{v}>"
    if CANONICAL_BRACKETS == "double_curly": return f"{{{{{v}}}}}"
    return f"[{v}]"

BROKEN_PLACEHOLDER_RX = re.compile(r'([\[\{\<]|{{)\s*([A-Za-z_][A-Za-z0-9_]*)\s*([\]\}\>]|}})')
NESTED_BRACKET_RX   = re.compile(r'[\{\[]\s*[\[\<\{]+.*?[\]\>\}]+\s*[\}\]]')

def fix_placeholders(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    def repl(m):
        var = m.group(2).lower()
        if var in KNOWN_VARS:
            return canonical_wrap(var)
        return m.group(0)
    s = BROKEN_PLACEHOLDER_RX.sub(repl, text)
    def repl_nested(m):
        raw = m.group(0)
        v = re.search(r'([A-Za-z_][A-Za-z0-9_]*)', raw)
        if v and v.group(1).lower() in KNOWN_VARS:
            return canonical_wrap(v.group(1).lower())
        return raw
    s = NESTED_BRACKET_RX.sub(repl_nested, s)
    return s

def enforce_brand_latin(text: str) -> str:
    if not isinstance(text, str) or not text: return text
    s = text
    for bad, good in BRAND_LATIN_MAP.items():
        s = s.replace(bad, good)
    return s

def load_glossary(path: str) -> Dict[str, str]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    flat = {}
    def walk(node):
        if isinstance(node, dict):
            if set(node.keys()) & {"en_to_zh","ru_to_zh","map","terms","glossary"}:
                for k in node: walk(node[k])
            else:
                for k,v in node.items():
                    if isinstance(v,str) and k:
                        flat[str(k)] = v
                    elif isinstance(v,dict) and "zh" in v and k:
                        flat[str(k)] = str(v["zh"])
        elif isinstance(node,list):
            for it in node: walk(it)
    walk(data)
    flat = {k:v for k,v in flat.items() if v and str(k)!=str(v)}
    return flat

def build_patterns(mapping: Dict[str,str]) -> List[Tuple[re.Pattern,str]]:
    items = list(mapping.items()); items.sort(key=lambda kv: len(kv[0]), reverse=True)
    out=[]
    for src,dst in items:
        if re.search(r'[A-Za-z0-9]', src):
            rx = re.compile(r'(?<![A-Za-z0-9_])'+re.escape(src)+r'(?![A-Za-z0-9_])')
        else:
            rx = re.compile(re.escape(src))
        out.append((rx,dst))
    return out

def apply_terms(s: str, patterns: List[Tuple[re.Pattern,str]]) -> str:
    if not isinstance(s,str) or not s: return s
    t=s
    for rx,repl in patterns:
        t = rx.sub(repl,t)
    return t

def autosave(df, path, tick, every=2000, seconds=120):
    now=time.time()
    if (tick%every==0) or (now-autosave.last>=seconds):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df.to_excel(path, index=False)
        autosave.last = now
autosave.last = 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet-name")
    ap.add_argument("--sheet-index", type=int, default=0)
    ap.add_argument("--glossary", required=True)
    ap.add_argument("--overwrite", action="store_true", help="覆盖已有第4列")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    sheet = args.sheet_name if args.sheet_name else args.sheet_index
    base,ext = os.path.splitext(args.excel)
    out = args.out or f"{base}.guard.xlsx"

    df = pd.read_excel(args.excel, sheet_name=sheet)
    while df.shape[1] < TARGET_COL_INDEX+1:
        df.insert(df.shape[1], f"col{df.shape[1]+1}", "")

    mapping = load_glossary(args.glossary)
    patterns = build_patterns(mapping)

    changed=0
    for i in range(len(df)):
        en = df.iat[i, EN_COL_INDEX]
        col4 = df.iat[i, TARGET_COL_INDEX] if df.shape[1] > TARGET_COL_INDEX else ""
        if (not args.overwrite) and isinstance(col4,str) and col4.strip():
            continue  # 不覆盖已有第4列
        s = en if isinstance(en,str) else ""
        s = enforce_brand_latin(s)
        s = apply_terms(s, patterns)     # 把术语先替成规范中文（LLM 会保持不变）
        s = fix_placeholders(s)
        df.iat[i, TARGET_COL_INDEX] = s
        changed += 1
        autosave(df, out, i+1)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_excel(out, index=False)
    print(f"[OK] {changed} rows → {out}")
    return 0

if __name__=="__main__":
    sys.exit(main())
