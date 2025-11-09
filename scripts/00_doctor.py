
import sys, os, importlib, yaml, textwrap
REQ = ["pandas","openpyxl","tqdm","pyyaml","requests"]
def check_mod(m):
    try:
        importlib.import_module(m)
        print(f"[doctor] dep {m}: OK")
        return True
    except Exception as e:
        print(f"[doctor] dep {m}: MISSING ({e})")
        return False
def main():
    print(f"[doctor] Python: {sys.version.split()[0]} ({sys.version.split()[1]})")
    ok = True
    for m in REQ:
        ok &= check_mod(m)
    # env keys
    for k in ["OPENAI_API_KEY","DEEPSEEK_API_KEY","SILICONFLOW_API_KEY"]:
        print(f"[doctor] env {k}: {'set' if os.getenv(k) else 'missing'}")
    # settings.local.yaml
    cfg_path = os.path.join("config","settings.local.yaml")
    if os.path.exists(cfg_path):
        try:
            cfg = yaml.safe_load(open(cfg_path,encoding="utf-8")) or {}
            provider = cfg.get("provider")
            print(f"[doctor] settings.local.yaml: FOUND (provider={provider})")
            # Normalize access to keys
            llm = cfg.get("llm") or {}
            ds = (llm.get("deepseek") or {})
            oa = (llm.get("openai") or {})
            print(f"[doctor] deepseek.api_key: {'set' if ds.get('api_key') else 'missing'} base={ds.get('base_url')}")
            print(f"[doctor] openai.api_key  : {'set' if oa.get('api_key') else 'missing'} base={oa.get('base_url')}")
        except Exception as e:
            print(f"[doctor] settings.local.yaml: READ ERROR {e}")
    else:
        print("[doctor] settings.local.yaml: NOT FOUND")
    if not ok:
        print("[doctor] Some dependencies missing. Try: pip install pandas openpyxl tqdm pyyaml requests")
        return 1
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
