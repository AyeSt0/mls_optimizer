
param(
  [switch]$NoAliases
)

function Write-Info($msg){ Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Ok($msg){ Write-Host "[OK]   $msg" -ForegroundColor Green }
function Write-Warn($msg){ Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg){ Write-Host "[ERR]  $msg" -ForegroundColor Red }

$root = Get-Location
Write-Info "Working in: $root"

# -- Ensure directories
$scriptDir = Join-Path $root "scripts"
$vscodeDir = Join-Path $root ".vscode"
if (!(Test-Path $scriptDir)) { New-Item -ItemType Directory -Path $scriptDir | Out-Null }
if (!(Test-Path $vscodeDir)) { New-Item -ItemType Directory -Path $vscodeDir | Out-Null }

# -- Write robust auto_commit.py (UTF-8)
$autoCommitPath = Join-Path $scriptDir "auto_commit.py"
$autoCommitPy = @'
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

    # 如果没有暂存改动，直接提示并退出
    if sh("git diff --cached --quiet", check=False).returncode == 0:
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
'@

Set-Content -Path $autoCommitPath -Value $autoCommitPy -Encoding UTF8 -NoNewline
Write-Ok "scripts/auto_commit.py written."

# -- JSON helpers
function Load-Json($path){
  if(Test-Path $path){
    try { return Get-Content -Raw -Path $path | ConvertFrom-Json } catch { return $null }
  }
  return $null
}
function Save-Json($path, $obj){
  $json = $obj | ConvertTo-Json -Depth 20
  Set-Content -Path $path -Value $json -Encoding UTF8
}
function Has-Prop($obj, $name){
  if($null -eq $obj){ return $false }
  return $obj.PSObject.Properties.Name -contains $name
}
function Ensure-ArrayProp($obj, $name){
  if(-not (Has-Prop $obj $name)){
    $obj | Add-Member -NotePropertyName $name -NotePropertyValue @()
  }
}

# -- tasks.json merge
$tasksPath = Join-Path $vscodeDir "tasks.json"
$existing = Load-Json $tasksPath
if(-not $existing){
  $existing = [pscustomobject]@{ version = "2.0.0"; tasks = @(); inputs = @() }
}else{
  if(-not (Has-Prop $existing "version")){ $existing | Add-Member -NotePropertyName version -NotePropertyValue "2.0.0" }
  Ensure-ArrayProp $existing "tasks"
  Ensure-ArrayProp $existing "inputs"
}

function Add-TaskIfMissing([object]$obj, [hashtable]$task){
  $label = $task.label
  $exists = $false
  foreach($t in $obj.tasks){
    if($t.label -eq $label){ $exists = $true; break }
  }
  if(-not $exists){ $obj.tasks += ([pscustomobject]$task) }
}

function Add-InputIfMissing([object]$obj, [hashtable]$inp){
  $id = $inp.id
  $exists = $false
  foreach($i in $obj.inputs){
    if($i.id -eq $id){ $exists = $true; break }
  }
  if(-not $exists){ $obj.inputs += ([pscustomobject]$inp) }
}

$envBlock = @{ PYTHONIOENCODING = "utf-8"; GIT_PAGER = "cat" }

$taskAllInfer = @{
  label = "Auto Commit (Add All + Infer)"
  type = "shell"
  command = "python"
  args = @("scripts/auto_commit.py","--all")
  options = @{ cwd = "${workspaceFolder}"; env = $envBlock }
  problemMatcher = @()
}
$taskAllTag = @{
  label = "Auto Commit + Tag (Add All + Infer)"
  type = "shell"
  command = "python"
  args = @("scripts/auto_commit.py","--all","--tag")
  options = @{ cwd = "${workspaceFolder}"; env = $envBlock }
  problemMatcher = @()
}
$taskPick = @{
  label = "Auto Commit (Pick type/scope)"
  type = "shell"
  command = "python"
  args = @(
    "scripts/auto_commit.py",
    "--all",
    "--type","${input:commitType}",
    "--scope","${input:commitScope}"
  )
  options = @{ cwd = "${workspaceFolder}"; env = $envBlock }
  problemMatcher = @()
}

$inpType = @{
  id = "commitType"
  type = "pickString"
  description = "Conventional Commit type"
  options = @("feat","fix","docs","style","refactor","perf","test","build","ci","chore","revert")
  default = "chore"
}
$inpScope = @{
  id = "commitScope"
  type = "promptString"
  description = "Scope (e.g. src,docs,tests). Leave empty to auto-infer"
  default = ""
}

# Backup existing tasks.json
if(Test-Path $tasksPath){
  $stamp = Get-Date -Format "yyyyMMddHHmmss"
  Copy-Item $tasksPath "$tasksPath.bak.$stamp" -Force
  Write-Info "Backed up existing tasks.json to tasks.json.bak.$stamp"
}

# Merge and save
Add-TaskIfMissing -obj $existing -task $taskAllInfer
Add-TaskIfMissing -obj $existing -task $taskAllTag
Add-TaskIfMissing -obj $existing -task $taskPick
Add-InputIfMissing -obj $existing -inp $inpType
Add-InputIfMissing -obj $existing -inp $inpScope

Save-Json $tasksPath $existing
Write-Ok ".vscode/tasks.json updated."

# -- settings.json (PSCUSTOMOBJECT-safe)
$settingsPath = Join-Path $vscodeDir "settings.json"
$settingsObj = Load-Json $settingsPath
if($null -eq $settingsObj){ $settingsObj = New-Object psobject }

if(-not (Has-Prop $settingsObj "git.enableSmartCommit")){
  $settingsObj | Add-Member -NotePropertyName "git.enableSmartCommit" -NotePropertyValue $true
}
if(-not (Has-Prop $settingsObj "git.postCommitCommand")){
  $settingsObj | Add-Member -NotePropertyName "git.postCommitCommand" -NotePropertyValue "none"
}
if(-not (Has-Prop $settingsObj "files.insertFinalNewline")){
  $settingsObj | Add-Member -NotePropertyName "files.insertFinalNewline" -NotePropertyValue $true
}
if(-not (Has-Prop $settingsObj "files.trimTrailingWhitespace")){
  $settingsObj | Add-Member -NotePropertyName "files.trimTrailingWhitespace" -NotePropertyValue $true
}

Save-Json $settingsPath $settingsObj
Write-Ok ".vscode/settings.json updated."

# Optional git aliases
if(-not $NoAliases){
  Write-Info "Setting git aliases: ac, bump (idempotent)"
  git config alias.ac   '!python scripts/auto_commit.py --all'
  git config alias.bump '!python scripts/auto_commit.py --all --tag'
}

Write-Ok "Done. In VS Code: Run Task -> 'Auto Commit (Add All + Infer)'. Or run: git ac"
