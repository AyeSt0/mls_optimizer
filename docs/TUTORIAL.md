
# MLS Optimizer — 使用教程（v6.4）

## 快速开始
1. 安装依赖：`pip install pandas openpyxl openai tqdm pyyaml`
2. 填写密钥：复制 `config/settings.local.example.yaml` 到 `config/settings.local.yaml`，填上 `providers.deepseek.api_key`（或 OpenAI）。
3. 把 `MLS Chinese.xlsx` 和 `name_map.json` 放到 `data/` 目录。
4. 运行 GUI：双击 `scripts/run_gui.bat`（Windows），或命令 `python scripts/00_launch_gui.py`。

## GUI 指南
- Excel：指向 `data/MLS Chinese.xlsx`
- name_map.json：指向 `data/name_map.json`
- Target Lang：默认 `zh-CN`
- Provider/Model：默认 DeepSeek；也可选 OpenAI
- Workers/Min/Max/RPM：并发与限流参数（内部自适应，遇 429 会自动退让）
- Context mode：`scene`（推荐）或 `window`
- Resume：勾选则断点续跑（默认勾选）
- Include system lines：如需把系统/提示类文案合到场景翻译可勾选

### 运行
- **Run FULL Pipeline**：执行 6 步：场景切分 → 翻译（术语前置）→ 术语统一 → 风格 → 再统一 → QA
- **Run TRANSLATE only**：仅执行翻译（含术语前置、断点续跑、自动保存）
- 日志：实时输出到 GUI；文件写入 `artifacts/`

## 结果产物
- 第5列写入：`data/MLS Chinese.zh-CN.llm.xlsx`（不覆盖第4列）
- 术语统一：`...terms.xlsx`
- 风格：`...styled.xlsx`
- 再统一后供 QA：`...styled.zh-CN.terms.xlsx`
- QA 报告：`data/report.zh-CN.qa.xlsx`
- 检查点：`artifacts/ckpt.translate.jsonl` / `ckpt.enforce.jsonl` / `ckpt.style.jsonl`

## 常见问题
- **报 429**：系统会自动降并发并退避；可在 GUI 调低 `Workers` 或增加 `RPM`。
- **中断重跑**：保持 `Resume` 勾选，直接再点运行即可续跑。
- **替换模型**：在 `config/settings.local.yaml` 设置或在 GUI 直接改 Provider/Model。
- **自定义 Prompt**：在 `config/settings(.local).yaml` 中覆盖 `system_template` 字段。

## 命令行一键
```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_all.ps1 `
  -Excel "data/MLS Chinese.xlsx" -NameMap "data/name_map.json" `
  -Lang zh-CN -Workers 8 -MinWorkers 2 -MaxWorkers 12 -RPM 60
```


## v6.4.1 GUI 改进
- 统一栅格布局，控件对齐更整齐；
- 目标语言提供大列表（含代码），也可直接手填自定义 BCP-47 代码；
