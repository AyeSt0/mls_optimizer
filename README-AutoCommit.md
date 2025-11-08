# VS Code 一键自动写 Commit（独立集成包）

## 放置位置
将本压缩包解压到你的仓库根目录：
- `.vscode/`（VS Code 任务与轻量设置）
- `scripts/auto_commit.py`（自动生成 Conventional Commit 并提交）

## 使用方法
1. 先把改动加入暂存区：`git add -A`
2. VS Code → 命令面板（Ctrl/Cmd+Shift+P）→ **Run Task**：
   - **Auto Commit (Infer type/scope)**：自动推断类型与范围
   - **Auto Commit (Pick type/scope)**：手动选择类型与范围
   - **Auto Commit + Tag (Infer)**：自动提交并把 `VERSION` 的补丁位 +1、打 tag（若根目录不存在 `VERSION` 会自动创建）

> 提示：此脚本仅依赖 Git 与 Python，无需安装额外包。

## 可选：绑定快捷键
在用户级 `keybindings.json` 里加入：
```json
{
  "key": "ctrl+alt+c",
  "command": "workbench.action.tasks.runTask",
  "args": "Auto Commit (Infer type/scope)"
}
```
