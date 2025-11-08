
param(
  [string]$Excel="data/MLS Chinese.xlsx",
  [string]$NameMap="data/name_map.json",
  [string]$Lang="zh-CN",
  [int]$Workers=8,
  [int]$MinWorkers=2,
  [int]$MaxWorkers=12,
  [int]$RPM=60
)

$ErrorActionPreference = "Stop"
Write-Host "== MLS Optimizer Full Pipeline =="
Write-Host "Excel: $Excel"

# 0) ensure dirs
New-Item -ItemType Directory -Force -Path artifacts | Out-Null
New-Item -ItemType Directory -Force -Path data | Out-Null

# 1) segment
python -m scripts.05_segment_context --excel "$Excel"

# 2) translate with glossary
python -m scripts.12_llm_translate --excel "$Excel" --target-lang $Lang --context-mode scene `
  --glossary "$NameMap" --glossary-max 300 --resume --autosave-every 200 --checkpoint-file artifacts/ckpt.translate.jsonl `
  --workers $Workers --min-workers $MinWorkers --max-workers $MaxWorkers --rpm $RPM

$xl1 = $Excel.Replace(".xlsx", ".$Lang.llm.xlsx")
# 3) enforce
python -m scripts.20_enforce_terms --excel "$xl1" --name-map "$NameMap" --target-lang $Lang --guard-by BOTH --resume --autosave-every 500 --checkpoint-file artifacts/ckpt.enforce.jsonl

$xl2 = $xl1.Replace(".llm.xlsx", ".terms.xlsx")
# 4) style
python -m scripts.30_style_adapt --excel "$xl2" --target-lang $Lang --punct-map config/punct.zh-CN.yaml --resume --autosave-every 800 --checkpoint-file artifacts/ckpt.style.jsonl

$xl3 = $xl2.Replace(".terms.xlsx", ".styled.xlsx")
# 5) re-enforce
python -m scripts.21_enforce_terms_again --excel "$xl3" --name-map "$NameMap" --target-lang $Lang --guard-by BOTH --resume --autosave-every 500 --checkpoint-file artifacts/ckpt.enforce.jsonl

$xl4 = $xl3.Replace(".styled.xlsx", ".styled.$Lang.terms.xlsx")
# 6) QA
python -m scripts.25_qa_check --excel "$xl4" --out "data/report.$Lang.qa.xlsx"

Write-Host "== DONE =="
