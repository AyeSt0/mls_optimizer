#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
00_doctor.py - Environment doctor for MLS Optimizer
Checks Python version, required packages, and API keys in env/settings.local.yaml.
"""
import sys, os, importlib, json
from pathlib import Path

REQ_PKGS = ["pandas", "openpyxl", "tqdm", "pyyaml", "openai"]
ENV_KEYS = ["OPENAI_API_KEY", "DEEPSEEK_API_KEY", "SILICONFLOW_API_KEY"]

def has_pkg(name):
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False

def check_settings_yaml():
    try:
        import yaml
    except Exception:
        return {}, False, "PyYAML not installed"
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "settings.local.yaml"
    if not cfg_path.exists():
        return {}, False, "settings.local.yaml not found"
    try:
        data = yaml.safe_load(cfg_path.read_text("utf-8")) or {}
        return data, True, ""
    except Exception as e:
        return {}, False, f"failed to parse settings.local.yaml: {e}"

def main():
    print(f"[doctor] Python: {sys.version.split()[0]} ({sys.executable})")
    for p in REQ_PKGS:
        print(f"[doctor] dep {p}: {'OK' if has_pkg(p) else 'MISSING'}")
    for k in ENV_KEYS:
        print(f"[doctor] env {k}: {'set' if os.getenv(k) else 'missing'}")
    cfg, ok, msg = check_settings_yaml()
    if ok:
        prov = (cfg.get("provider") or "deepseek").lower()
        dsc = ((cfg.get('llm') or {}).get('deepseek') or {})
        oai = ((cfg.get('llm') or {}).get('openai') or {})
        print(f"[doctor] settings.local.yaml: OK (provider={prov})")
        print(f"[doctor]   deepseek/base_url={dsc.get('base_url','')!r} model={dsc.get('name','')!r} api_key={'set' if dsc.get('api_key') else 'missing'}")
        print(f"[doctor]   openai/base_url={oai.get('base_url','')!r} model={oai.get('name','')!r} api_key={'set' if oai.get('api_key') else 'missing'}")
    else:
        print(f"[doctor] settings.local.yaml: {msg}")
    if not all(has_pkg(p) for p in REQ_PKGS):
        print("[doctor] Some dependencies missing. Try: pip install pandas openpyxl tqdm pyyaml openai")
        sys.exit(2)
    print("[doctor] Ready.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
