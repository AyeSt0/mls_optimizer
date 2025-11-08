
import sys, os, subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def ask(prompt, default=None):
    s = input(f"{prompt} [{default}]: ").strip()
    return s or default

if __name__ == "__main__":
    excel = ask("Excel path", str(PROJECT_ROOT / "data" / "MLS Chinese.xlsx"))
    namemap = ask("name_map.json", str(PROJECT_ROOT / "data" / "name_map.json"))
    lang = ask("Target language", "zh-CN")
    mode = ask("Context mode (scene/window)", "scene")
    workers = ask("Workers", "8")
    minw = ask("Min workers", "2")
    maxw = ask("Max workers", "12")
    rpm = ask("RPM", "60")
    resume = ask("Resume? (y/n)", "y").lower().startswith("y")

    cmds = [
        [sys.executable, "-m", "scripts.05_segment_context", "--excel", excel],
        [sys.executable, "-m", "scripts.12_llm_translate", "--excel", excel, "--target-lang", lang,
         "--context-mode", mode, "--glossary", namemap, "--glossary-max", "300",
         "--workers", workers, "--min-workers", minw, "--max-workers", maxw, "--rpm", rpm,
         "--autosave-every", "200", "--checkpoint-file", "artifacts/ckpt.translate.jsonl"] + (["--resume"] if resume else []),
        [sys.executable, "-m", "scripts.20_enforce_terms", "--excel", excel.replace(".xlsx", f".{lang}.llm.xlsx"),
         "--name-map", namemap, "--target-lang", lang, "--guard-by", "BOTH",
         "--autosave-every", "500", "--checkpoint-file", "artifacts/ckpt.enforce.jsonl"] + (["--resume"] if resume else []),
        [sys.executable, "-m", "scripts.30_style_adapt", "--excel", excel.replace(".xlsx", f".{lang}.llm.terms.xlsx"),
         "--target-lang", lang, "--punct-map", "config/punct.zh-CN.yaml",
         "--autosave-every", "800", "--checkpoint-file", "artifacts/ckpt.style.jsonl"] + (["--resume"] if resume else []),
        [sys.executable, "-m", "scripts.21_enforce_terms_again", "--excel", excel.replace(".xlsx", f".{lang}.llm.terms.styled.xlsx"),
         "--name-map", namemap, "--target-lang", lang, "--guard-by", "BOTH"],
        [sys.executable, "-m", "scripts.25_qa_check", "--excel", excel.replace(".xlsx", f".{lang}.llm.terms.styled.{lang}.terms.xlsx"),
         "--out", f"data/report.{lang}.qa.xlsx"]
    ]

    for i, cmd in enumerate(cmds, 1):
        print(f"\n== Step {i}/{len(cmds)}: {' '.join(cmd)}")
        rc = subprocess.call(cmd, cwd=str(PROJECT_ROOT))
        if rc != 0:
            print(f"[ERROR] Step {i} failed: {rc}")
            sys.exit(rc)
    print("\n== DONE ==")
