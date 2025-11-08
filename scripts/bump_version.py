#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
bump_version.py — simple SemVer bumper for this repo.
Supports pre-releases like 0.1.0-alpha.1

Usage examples:
  python scripts/bump_version.py --to 0.1.0-alpha.2 --commit --tag --push
  python scripts/bump_version.py --part patch --commit --tag
  python scripts/bump_version.py --preonly alpha --commit

It updates:
  - VERSION (root)
  - mls_optimizer/__init__.py (__version__ = "...")
  - pyproject.toml (version = "...") if present

Then optionally commits, creates a tag (default 'vX.Y.Z[-pre.N]'), and pushes.
"""

import argparse
import os
import re
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # repo root assuming scripts/
PKG_INIT = ROOT / "mls_optimizer" / "__init__.py"
VERSION_FILE = ROOT / "VERSION"
PYPROJECT = ROOT / "pyproject.toml"

SEMVER_RE = re.compile(
    r'^(?P<maj>0|[1-9]\d*)\.(?P<min>0|[1-9]\d*)\.(?P<pat>0|[1-9]\d*)'
    r'(?:-(?P<pre>(alpha|beta|rc))\.(?P<pren>[1-9]\d*))?$'
)

def read_current_version():
    if VERSION_FILE.exists():
        v = VERSION_FILE.read_text(encoding="utf-8").strip()
        if v: return v
    if PKG_INIT.exists():
        m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", PKG_INIT.read_text(encoding="utf-8"))
        if m: return m.group(1)
    if PYPROJECT.exists():
        m = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', PYPROJECT.read_text(encoding="utf-8"), re.M)
        if m: return m.group(1)
    return "0.1.0-alpha.1"

def validate(v: str):
    if not SEMVER_RE.match(v):
        raise SystemExit(f"[ERR] Invalid SemVer (expect X.Y.Z or X.Y.Z-alpha.N/beta.N/rc.N): {v}")

def bump_parts(cur: str, part: str, pre: str=None, pre_num: int=1) -> str:
    m = SEMVER_RE.match(cur)
    if not m:
        raise SystemExit(f"[ERR] Current version not SemVer: {cur}")
    maj, mi, pa = int(m.group('maj')), int(m.group('min')), int(m.group('pat'))
    # ignore existing prerelease for bumping base number
    if part == "major":
        maj, mi, pa = maj+1, 0, 0
    elif part == "minor":
        mi, pa = mi+1, 0
    elif part == "patch":
        pa = pa+1
    else:
        raise SystemExit("[ERR] part must be major|minor|patch")
    base = f"{maj}.{mi}.{pa}"
    if pre:
        return f"{base}-{pre}.{int(pre_num)}"
    return base

def bump_preonly(cur: str, pre: str) -> str:
    m = SEMVER_RE.match(cur)
    if not m:
        raise SystemExit(f"[ERR] Current version not SemVer: {cur}")
    maj, mi, pa = int(m.group('maj')), int(m.group('min')), int(m.group('pat'))
    cur_pre, cur_n = m.group('pre'), m.group('pren')
    base = f"{maj}.{mi}.{pa}"
    if cur_pre == pre and cur_n:
        return f"{base}-{pre}.{int(cur_n)+1}"
    return f"{base}-{pre}.1"

def write_version_files(new_v: str):
    # VERSION
    VERSION_FILE.write_text(new_v, encoding="utf-8")
    # __init__.py
    if PKG_INIT.exists():
        txt = PKG_INIT.read_text(encoding="utf-8")
    else:
        PKG_INIT.parent.mkdir(parents=True, exist_ok=True)
        txt = ""
    if re.search(r"__version__\s*=", txt):
        txt = re.sub(r"(__version__\s*=\s*['\"])([^'\"]+)(['\"])",
                     rf"\g<1>{new_v}\3", txt, count=1)
    else:
        if txt and not txt.endswith("\n"): txt += "\n"
        txt += f"__version__ = '{new_v}'\n"
    PKG_INIT.write_text(txt, encoding="utf-8")
    # pyproject.toml
    if PYPROJECT.exists():
        t = PYPROJECT.read_text(encoding="utf-8")
        if re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', t, re.M):
            t = re.sub(r'^(\s*version\s*=\s*["\'])([^"\']+)(["\'])',
                       rf"\g<1>{new_v}\3", t, flags=re.M, count=1)
            PYPROJECT.write_text(t, encoding="utf-8")

def run(cmd, check=True):
    print("[sh]", " ".join(cmd))
    return subprocess.run(cmd, check=check)

def ensure_git_repo(allow_dirty=False):
    try:
        run(["git","rev-parse","--is-inside-work-tree"])
    except Exception:
        raise SystemExit("[ERR] Not a git repository. Run `git init` first.")
    if not allow_dirty:
        r = subprocess.run(["git","status","--porcelain"], capture_output=True, text=True)
        if r.stdout.strip():
            raise SystemExit("[ERR] Working tree not clean. Commit or stash first, or use --allow-dirty.")

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--to", help="Set exact version (SemVer).")
    g.add_argument("--part", choices=["major","minor","patch"], help="Bump part.")
    ap.add_argument("--pre", choices=["alpha","beta","rc"], help="Set prerelease tag (with --part).")
    ap.add_argument("--pre-num", type=int, default=1, help="Prerelease number (default 1).")
    ap.add_argument("--preonly", choices=["alpha","beta","rc"], help="Only bump/attach pre-release without changing X.Y.Z.")
    ap.add_argument("--commit", action="store_true", help="Commit changes.")
    ap.add_argument("--tag", action="store_true", help="Create git tag 'v<version>'.")
    ap.add_argument("--tag-prefix", default="v")
    ap.add_argument("--message", default=None, help="Commit message.")
    ap.add_argument("--push", action="store_true", help="Push branch and tag to origin.")
    ap.add_argument("--allow-dirty", action="store_true", help="Allow dirty working tree.")
    args = ap.parse_args()

    cur = read_current_version()
    print(f"[info] current version: {cur}")

    if args.to:
        new_v = args.to.strip()
    elif args.preonly:
        new_v = bump_preonly(cur, args.preonly)
    else:
        new_v = bump_parts(cur, args.part, args.pre, args.pre_num)

    validate(new_v)
    print(f"[info] new version: {new_v}")

    write_version_files(new_v)
    print("[ok] wrote VERSION, __init__.py and pyproject.toml (if present).")

    if args.commit or args.tag or args.push:
        ensure_git_repo(allow_dirty=args.allow_dirty)

    if args.commit:
        msg = args.message or f"chore(release): bump version to {new_v}"
        run(["git","add",str(VERSION_FILE), str(PKG_INIT)] + ([str(PYPROJECT)] if PYPROJECT.exists() else []))
        run(["git","commit","-m", msg])

    if args.tag:
        tag = f"{args.tag_prefix}{new_v}"
        run(["git","tag","-a", tag, "-m", f"Release {new_v}"])

    if args.push:
        run(["git","push"])
        if args.tag:
            run(["git","push","origin", f"{args.tag_prefix}{new_v}"])

if __name__ == "__main__":
    main()
