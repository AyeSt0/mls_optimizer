#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Auto-generate a Conventional Commit message based on staged changes and commit (Windows-safe + root-safe).

import argparse
import os
import subprocess
from pathlib import Path

KEYWORDS_FIX = ("fix", "bug", "error", "issue", "hotfix")
PROJECT_ROOT_FALLBACK = Path(__file__).resolve().parents[1]

def sh(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    """
    Run a shell command with UTF-8 I/O, never crash on decode.
    """
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

def out(cp: subprocess.CompletedProcess) -> str:
    return (cp.stdout or "").strip()

def ensure_git_root(debug: bool = False) -> Path:
    """
    cd 到仓库顶层（git rev-parse --show-toplevel），否则用脚本上级作为兜底。
    """
    cp = sh("git rev-parse --show-toplevel", check=False)
    root = out(cp)
    if not root:
        # 兜底：脚本上级目录
        root = str(PROJECT_ROOT_FALLBACK)
    try:
        os.chdir(root)
    except Exception:
        # 如果切换失败，保持当前目录，但尽量继续
        pass
    if debug:
        print(f"[debug] git-root = {root}")
        # 查看当前是否真的在仓库中
        print(f"[debug] git rev-parse exit = {cp.returncode}")
        print(f"[debug] CWD = {os.getcwd()}")
    return Path(root)

def staged_files():
    cp = sh("git diff --cached --name-status", check=False)
    files = []
    for line in out(cp).splitlines():
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
        diff_text = out(sh("git diff --cached", check=False)).lower()
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
    parser.add_argument("--debug", action="store_true", help="print debug info")
    args = parser.parse_args()

    # 先定位仓库根目录
    repo_root = ensure_git_root(debug=args.debug)

    if args.all:
        sh("git add -A", check=False)

    # 无暂存改动则退出
    rc = sh("git diff --cached --quiet", check=False).returncode
    if args.debug:
        print(f"[debug] diff --cached --quiet rc = {rc}")
        print(f"[debug] short status (staged view):")
        print(out(sh("git diff --cached --name-status", check=False)))
    if rc == 0:
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
        ver_path = repo_root / "VERSION"
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
