---
name: setup-skill
description: This skill should be used when the user asks to "configure API keys", "setup API keys", "configure Qwen", "configure Gemini", "设置 API Keys", "初始化环境", "安装依赖", or needs to set up Qwen/Gemini API keys or initialize the environment for expert-auditor-pro plugin.
---

# setup-skill

交互式录入并保存 API Keys 到 config.json，以及管理 Python 依赖环境。

## 工具验证状态

| 工具 | 状态 | 说明 |
|------|------|------|
| `uv` | ✅ 可用 | macOS: `/opt/homebrew/bin/uv` |
| `uv run python scripts/main.py --help` | ✅ 可用 | 验证通过 |
| `uv run python scripts/config_manager.py` | ✅ 可用 | 不带参数显示配置 |
| `uv run python scripts/config_manager.py --set-qwen-key` | ✅ 可用 | |
| `uv run python scripts/config_manager.py --set-gemini-key` | ✅ 可用 | |

## 使用场景

- 首次配置插件
- 更新 API Keys
- 初始化/更新 Python 依赖环境
- 查看当前配置状态

## 执行流程

1. 检查 uv 是否已安装 ✅ 已验证可用
2. 使用 uv sync 安装依赖（如需）
3. 提示用户输入 Qwen API Key（如未配置）
4. 提示用户输入 Gemini API Key（如未配置）
5. 调用 config_manager.py 保存配置

## 环境初始化

### 自动初始化（推荐）

首次使用前，运行以下命令初始化环境：

```bash
cd /path/to/expert-auditor-pro
uv sync
```

### 手动初始化

如果 uv 未安装，先安装 uv：

```bash
# macOS
brew install uv

# 或使用 pip
pip install uv
```

然后同步依赖：

```bash
uv sync
```

### 验证环境

```bash
# 使用 uv run 执行脚本（自动激活虚拟环境）
uv run python scripts/main.py --help
```

## 配置方式

### 方式1: 命令行参数

```bash
# 设置 Qwen API Key
uv run python scripts/config_manager.py --set-qwen-key "YOUR_QWEN_KEY"

# 设置 Gemini API Key
uv run python scripts/config_manager.py --set-gemini-key "YOUR_GEMINI_KEY"

# 同时设置两个
uv run python scripts/config_manager.py --set-qwen-key "YOUR_QWEN_KEY" --set-gemini-key "YOUR_GEMINI_KEY"
```

### 方式2: 交互式输入 / 查看当前配置

```bash
# 不带参数运行 - 无参数时显示当前配置（API Key 隐藏后4位）
uv run python scripts/config_manager.py
```

## 配置文件

API Keys 保存在 `~/.claude/plugin/expert-auditor-pro/config.json`：

```json
{
  "qwen_api_key": "your-qwen-key",
  "gemini_api_key": "your-gemini-key",
  "qwen_model": "qwen3.5-plus",
  "gemini_model": "gemini-3.1-pro-preview",
  "proxy": "http://127.0.0.1:7890"
}
```

## 依赖脚本

- **`scripts/config_manager.py`** - 配置管理脚本（支持 --set-qwen-key, --set-gemini-key）
- **`scripts/paths.py`** - 路径管理模块（配置存储在 ~/.claude/plugin/expert-auditor-pro/）
