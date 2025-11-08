
# MLS Optimizer v6.1.1

上下文感知 + 异步并行 + 术语守护 + QA + 配置内置 API Key 的本地化流水线。输出写入**第5列**，不覆盖第4列。

## 目录
```
mls_optimizer_v6_1_1/
├─ mls_optimizer/          # 核心模块
├─ scripts/                # 命令行脚本
├─ config/                 # 配置（含 punct 与 settings.local.template）
├─ artifacts/              # 产物（报告、缓存）
├─ data/                   # 数据文件（放 MLS Chinese.xlsx、name_map.json）
└─ requirements.txt
```

## 快速开始
```bash
# 1) 安装依赖（建议虚拟环境）
pip install -r requirements.txt

# 2) 填写 API Key（任一即可）
#   - 推荐复制 config/settings.local.example.yaml → config/settings.local.yaml 并填写
#   - SiliconFlow 网关注意 base_url 加 /v1

# 3) 放文件
#   - data/MLS Chinese.xlsx
#   - data/name_map.json

# 4) 场景切分
python scripts/05_segment_context.py --excel "data/MLS Chinese.xlsx"

# 5) 带上下文翻译（写入第5列）
python scripts/12_llm_translate.py --excel "data/MLS Chinese.xlsx" --target-lang zh-CN --context-mode scene --workers 6

# 6) 术语统一
python scripts/20_enforce_terms.py --excel "data/MLS Chinese.zh-CN.llm.xlsx" --name-map data/name_map.json --target-lang zh-CN --guard-by BOTH

# 7) 风格/标点（不把“你”改成“您”）
python scripts/30_style_adapt.py --excel "data/MLS Chinese.zh-CN.terms.xlsx" --target-lang zh-CN --punct-map config/punct.zh-CN.yaml

# 8) QA
python scripts/25_qa_check.py --excel "data/MLS Chinese.zh-CN.styled.xlsx" --out "data/report.zh-CN.qa.xlsx"
```

## 列约定
- 第1列 RU（俄语）
- 第2列 speaker
- 第3列 EN（英文）
- 第4列 现中文（不改）
- 第5列 OUT（脚本输出）

## 提示
- 429/限流：调低 `--workers` 或 `config/settings.yaml` 的 rpm
- Windows 避免 Excel 打开目标文件（会锁定）
- 最佳实践：先跑 0–50 行验证，再跑全表


## v6.1.3 新增
- ✅ **实时进度条**（tqdm）：行模式与场景模式都会显示完成进度
- ✅ **自适应并发/限流**：批量自调并发，遇到 429/超时自动退让并重试
- ✅ `--quiet` 静默模式；`--min-workers/--max-workers/--rpm` 可控
- 内部用 `asyncio.to_thread` 避免同步 SDK 阻塞事件循环

### 示例（带自适应）
```bash
python -m scripts.12_llm_translate --excel "data/MLS Chinese.xlsx" \
  --target-lang zh-CN --context-mode scene \
  --workers 8 --min-workers 2 --max-workers 12 --rpm 60
```
进度条会显示当前 workers、连续成功/失败统计。


## 推荐流水线（结合你提出的顺序）
**Prompt 预置术语 → 翻译 → 术语统一 → 风格微调 → 术语再统一 → QA**

命令示例：
```bash
# 1) 场景切分
python -m scripts.05_segment_context --excel "data/MLS Chinese.xlsx"

# 2) 翻译（在 System Prompt 中注入术语表，强制遵守）
python -m scripts.12_llm_translate --excel "data/MLS Chinese.xlsx" \
  --target-lang zh-CN --context-mode scene \
  --glossary data/name_map.json --glossary-max 300 \
  --workers 8 --min-workers 2 --max-workers 12 --rpm 60

# 3) 术语统一（保证100%替换到位）
python -m scripts.20_enforce_terms --excel "data/MLS Chinese.zh-CN.llm.xlsx" \
  --name-map data/name_map.json --target-lang zh-CN --guard-by BOTH

# 4) 风格/标点（不会触碰术语映射）
python -m scripts.30_style_adapt.py --excel "data/MLS Chinese.zh-CN.terms.xlsx" \
  --target-lang zh-CN --punct-map config/punct.zh-CN.yaml

# 5) 术语再统一（防止风格规则意外影响术语）
python -m scripts.21_enforce_terms_again --excel "data/MLS Chinese.zh-CN.styled.xlsx" \
  --name-map data/name_map.json --target-lang zh-CN --guard-by BOTH

# 6) QA 报告
python -m scripts.25_qa_check --excel "data/MLS Chinese.zh-CN.styled.zh-CN.terms.xlsx" \
  --out "data/report.zh-CN.qa.xlsx"
```
> 备注：第 5 步会在风格微调后再做一次术语替换，确保零回退。

### v6.2.1 更新
- ✅ `system_template` 支持：可在 `config/settings(.local).yaml` 覆盖默认 System Prompt
- ✅ I/O 更稳：自动选择首张工作表；写文件前自动建目录
- ✅ 一键脚本：`scripts/run_all.ps1` / `scripts/run_all.bat`
- ✅ 仍保留：术语前置到 Prompt + 翻译后两次术语统一 + 进度条 + 自适应并发

#### 一键运行（PowerShell）
```powershell
# 在项目根目录
powershell -ExecutionPolicy Bypass -File scripts/run_all.ps1 `
  -Excel "data/MLS Chinese.xlsx" -NameMap "data/name_map.json" `
  -Lang zh-CN -Workers 8 -MinWorkers 2 -MaxWorkers 12 -RPM 60
```

#### 自定义 System Prompt
把你的模板粘到 `config/settings.local.yaml` 的 `system_template` 字段即可。
模板里 `{brand_list}` 会自动替换为品牌白名单，末尾自动追加 `Target language: zh-CN`。
```


### v6.4 新增
- GUI 启动器：`scripts/00_launch_gui.py`（Windows 直接双击 `scripts/run_gui.bat`）
- TUI 版：`scripts/00_launch_tui.py`
- 教程：`docs/TUTORIAL.md`
