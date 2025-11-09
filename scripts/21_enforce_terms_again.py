# -*- coding: utf-8 -*-
"""
对第5列（译文列）进行“翻译后再统一”：术语强替换（最长匹配优先）+ 占位符修正 + 品牌拉丁化。
默认另存为 *.terms.xlsx
"""

import argparse, os, re, sys, json, time
from typing import Dict, List, Tuple
import pandas as pd

TARGET_COL_INDEX = 4  # 第5列
CANONICAL_BRACKETS = "square"
KNOWN_VARS = {"mcname","mcsurname","mc_surname"}
BRAND_LATIN_MAP = {"Ins":"Instagram","ins":"Instagram","Instagram":"Instagram","Lovense":"Lovense","帕特伦":"Patreon","爱发电":"Patreon","罗嗨斯":"Lovense"}

def canonical_wrap(v:str)->str:
    return f"[{v}]" if CANONICAL_BRACKETS=="square" else f"{{{v}}}"

BROKEN_PLACEHOLDER_RX = re.compile(r'([\[\{\<]|{{)\s*([A-Za-z_][A-Za-z0-9_]*)\s*([\]\}\>]|}})')
NESTED_BRACKET_RX   = re.compile(r'[\{\[]\s*[\[\<\{]+.*?[\]\>\}]+\s*[\}\]]')

def fix_placeholders(text:str, canonize_bare=False)->str:
    if not isinstance(text,str) or not text: return text
    def repl(m):
        var=m.group(2).lower()
        if var in KNOWN_VARS: return canonical_wrap(var)
        return m.group(0)
    s = BROKEN_PLACEHOLDER_RX.sub(repl, text)
    def rn(m):
        raw=m.group(0)
        v=re.search(r'([A-Za-z_][A-Za-z0-9_]*)', raw)
        if v and v.group(1).lower() in KNOWN_VARS:
            return canonical_wrap(v.group(1).lower())
        return raw
    s = NESTED_BRACKET_RX.sub(rn, s)
    if canonize_bare:
        for v in KNOWN_VARS:
            rx=re.compile(r'(?<![A-Za-z0-9_])'+re.escape(v)+r'(?![A-Za-z0-9_])',re.I)
            s = rx.sub(canonical_wrap(v), s)
    return s

def enforce_brand_latin(s:str)->str:
    if not isinstance(s,str) or not s: return s
    for bad,good in BRAND_LATIN_MAP.items():
        s=s.replace(bad,good)
    return s

def load_glossary(path:str)->Dict[str,str]:
    with open(path,'r',encoding='utf-8') as f:
        data=json.load(f)
    flat={}
    def walk(n):
        if isinstance(n,dict):
            if set(n.keys()) & {"en_to_zh","ru_to_zh","map","terms","glossary"}:
                for k in n: walk(n[k])
            else:
                for k,v in n.items():
                    if isinstance(v,str) and k: flat[str(k)]=v
                    elif isinstance(v,dict) and "zh" in v and k: flat[str(k)]=str(v["zh"])
        elif isinstance(n,list):
            for it in n: walk(it)
    walk(data)
    return {k:v for k,v in flat.items() if v and str(k)!=str(v)}

def build_patterns(mapping:Dict[str,str])->List[Tuple[re.Pattern,str]]:
    items=list(mapping.items()); items.sort(key=lambda kv: len(kv[0]), reverse=True)
    out=[]
    for src,dst in items:
        if re.search(r'[A-Za-z0-9]', src):
            rx=re.compile(r'(?<![A-Za-z0-9_])'+re.escape(src)+r'(?![A-Za-z0-9_])')
        else:
            rx=re.compile(re.escape(src))
        out.append((rx,dst))
    return out

def apply_terms(s:str, pats:List[Tuple[re.Pattern,str]])->str:
    if not isinstance(s,str) or not s: return s
    t=s
    for rx,repl in pats: t=rx.sub(repl,t)
    return t

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet-name")
    ap.add_argument("--sheet-index", type=int, default=0)
    ap.add_argument("--glossary", required=True)
    ap.add_argument("--out", type=str, default=None)
    ap.add_argument("--autosave-every", type=int, default=1000)
    ap.add_argument("--autosave-seconds", type=int, default=120)
    ap.add_argument("--canonize-bare-vars", action="store_true")
    args=ap.parse_args()

    sheet=args.sheet_name if args.sheet_name else args.sheet_index
    base,ext=os.path.splitext(args.excel)
    out=args.out or f"{base}.terms.xlsx"

    df=pd.read_excel(args.excel, sheet_name=sheet)
    if df.shape[1] < TARGET_COL_INDEX+1:
        print(f"[ERROR] sheet has {df.shape[1]} cols; expect ≥ {TARGET_COL_INDEX+1}")
        return 1

    mapping=load_glossary(args.glossary)
    pats=build_patterns(mapping)

    last=time.time(); changed=0
    for i in range(len(df)):
        val=df.iat[i, TARGET_COL_INDEX]
        if not isinstance(val,str) or not val.strip(): continue
        orig=val
        v=enforce_brand_latin(orig)
        v=apply_terms(v, pats)
        v=fix_placeholders(v, canonize_bare=args.canonize_bare_vars)
        if v!=orig:
            df.iat[i, TARGET_COL_INDEX]=v; changed+=1
        if (i+1)%args.autosave_every==0 or (time.time()-last)>=args.autosave_seconds:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            df.to_excel(out, index=False); last=time.time()
            print(f"[AUTO-SAVE] rows={i+1} → {out}", flush=True)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_excel(out, index=False)
    print(f"[OK] changed={changed}/{len(df)} → {out}")
    return 0

if __name__=="__main__":
    sys.exit(main())
