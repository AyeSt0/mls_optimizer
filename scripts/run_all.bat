
@echo off
set EXCEL=data\MLS Chinese.xlsx
set NAMEMAP=data\name_map.json
set LANG=zh-CN
set WORKERS=8
set MINWORKERS=2
set MAXWORKERS=12
set RPM=60

echo == MLS Optimizer Full Pipeline ==

if not exist artifacts mkdir artifacts
if not exist data mkdir data

python -m scripts.05_segment_context --excel "%EXCEL%"
python -m scripts.12_llm_translate --excel "%EXCEL%" --target-lang %LANG% --context-mode scene --glossary "%NAMEMAP%" --glossary-max 300 --resume --autosave-every 200 --checkpoint-file artifacts\ckpt.translate.jsonl --workers %WORKERS% --min-workers %MINWORKERS% --max-workers %MAXWORKERS% --rpm %RPM%

set XL1=%EXCEL:.xlsx=.%LANG%.llm.xlsx%
python -m scripts.20_enforce_terms --excel "%XL1%" --name-map "%NAMEMAP%" --target-lang %LANG% --guard-by BOTH --resume --autosave-every 500 --checkpoint-file artifacts\ckpt.enforce.jsonl

set XL2=%XL1:.llm.xlsx=.terms.xlsx%
python -m scripts.30_style_adapt --excel "%XL2%" --target-lang %LANG% --punct-map config/punct.zh-CN.yaml --resume --autosave-every 800 --checkpoint-file artifacts\ckpt.style.jsonl

set XL3=%XL2:.terms.xlsx=.styled.xlsx%
python -m scripts.21_enforce_terms_again --excel "%XL3%" --name-map "%NAMEMAP%" --target-lang %LANG% --guard-by BOTH --resume --autosave-every 500 --checkpoint-file artifacts\ckpt.enforce.jsonl

set XL4=%XL3:.styled.xlsx=.styled.%LANG%.terms.xlsx%
python -m scripts.25_qa_check --excel "%XL4%" --out "data\report.%LANG%.qa.xlsx"

echo == DONE ==
pause
