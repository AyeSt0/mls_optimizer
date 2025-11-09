#!/usr/bin/env python3
# Auto-generate a Conventional Commit message based on staged changes and commit (Windows-safe).

import argparse
import os
import subprocess
from pathlib import Path

KEYWORDS_FIX = ("fix", "bug", "error", "issue", "hotfix")
PROJECT_ROOT = Path(__file__).resolve().parents[1]

def sh(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return CompletedProcess with UTF-8 decoding, never crashing on decode."""
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("GIT_PAGER", "cat")
    return subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=check,
    )

def _out(cp: subprocess.CompletedProcess) -> str:
    return (cp.stdout or "").strip()

def staged_files():
    out = _out(sh("git diff --cached --name-status", check=False))
    files = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status, path = parts[0], parts[-1]
        files.append((status, path))
    return files

def infer_type(files):
    added = [p for s, p in files if s.startswith("A")]
    changed = [p for s, p in files if s.startswith("M")]
    if added and any(p.startswith("src/") for p in added):
        return "feat"
    if changed:
        diff_text = _out(sh("git diff --cached", check=False)).lower()
        if any(k in diff_text for k in KEYWORDS_FIX):
            return "fix"
    if files and all(p.endswith(".md") for _, p in files):
        return "docs"
    return "chore"

def infer_scope(files):
    scopes = set()
    for _, p in files:
        head = p.split("/", 1)[0]
        if head in {"src", "scripts", "docs", "tests"}:
            scopes.add(head)
    return ",".join(sorted(scopes)) or "repo"

def summarize(files, limit=6):
    names = [Path(p).name for _, p in files]
    uniq = []
    for n in names:
        if n not in uniq:
            uniq.append(n)
    if len(uniq) > limit:
        return ", ".join(uniq[:limit]) + f", +{len(uniq)-limit} more"
    return ", ".join(uniq) if uniq else "files"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", dest="ctype", default=None)
    parser.add_argument("--scope", dest="scope", default=None)
    parser.add_argument("--tag", action="store_true", help="also bump patch version & tag")
    parser.add_argument("--all", action="store_true", help="stage all changes before commit")
    args = parser.parse_args()

    if args.all:
        sh("git add -A", check=False)

    # 濡傛灉娌℃湁鏆傚瓨鏀瑰姩锛岀洿鎺ユ彁绀哄苟閫€鍑?    if sh("git diff --cached --quiet", check=False).returncode == 0:
        print("Nothing staged. Use `git add -A` or pass --all.")
        return

    files = staged_files()
    ctype = args.ctype or infer_type(files)
    scope = args.scope or infer_scope(files)
    subject = summarize(files)
    msg = f"{ctype}({scope}): update {subject}"

    sh(f'git commit -m "{msg}"', check=False)
    print(f"Committed: {msg}")

    if args.tag:
        ver_path = PROJECT_ROOT / "VERSION"
        if not ver_path.exists():
            ver_path.write_text("0.1.0\n", encoding="utf-8")
        cur = (ver_path.read_text(encoding="utf-8").strip() or "0.1.0")
        try:
            major, minor, patch = [int(x) for x in cur.split(".")]
        except Exception:
            major, minor, patch = 0, 1, 0
        patch += 1
        next_ver = f"{major}.{minor}.{patch}"
        ver_path.write_text(next_ver + "\n", encoding="utf-8")
        sh("git add VERSION", check=False)
        sh(f'git commit -m "chore(release): bump VERSION to {next_ver}"', check=False)
        sh(f"git tag v{next_ver}", check=False)
        print(f"Tagged v{next_ver}")

if __name__ == "__main__":
    main()