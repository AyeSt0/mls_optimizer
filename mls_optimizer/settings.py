
import os, yaml, copy

def _deep_update(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base) if isinstance(base, dict) else {}
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_update(out[k], v)
        else:
            out[k] = v
    return out

def load_settings(default_path: str = "config/settings.yaml"):
    with open(default_path, "r", encoding="utf-8") as f:
        base = yaml.safe_load(f) or {}
    # local override
    local_path = os.path.join(os.path.dirname(default_path), "settings.local.yaml")
    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            local = yaml.safe_load(f) or {}
        base = _deep_update(base, local)

    # env override (optional)
    env_openai = os.environ.get("OPENAI_API_KEY")
    env_deepseek = os.environ.get("DEEPSEEK_API_KEY")
    if env_openai:
        base.setdefault("llm", {}).setdefault("openai", {})["api_key"] = env_openai
    if env_deepseek:
        base.setdefault("llm", {}).setdefault("deepseek", {})["api_key"] = env_deepseek
    return base

def get_provider_config(settings: dict, provider: str) -> dict:
    prov = (provider or settings.get("provider") or "deepseek").lower()
    return (settings.get("llm") or {}).get(prov, {})
