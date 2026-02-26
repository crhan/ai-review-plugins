---
name: setup-skill
description: This skill should be used when the user asks to "configure API keys", "setup API keys", "configure Qwen", "configure Gemini", "设置 API Keys", "初始化环境", "安装依赖", or needs to set up Qwen/Gemini API keys or initialize the environment for expert-auditor-pro plugin.
---

# setup-skill

交互式录入并保存 API Keys 到 config.json，以及管理 Python 依赖环境。

## 使用场景

- 首次配置插件
- 更新 API Keys
- 初始化/更新 Python 依赖环境
- 查看当前配置状态

## 执行流程

1. 检查 uv 是否已安装
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

### 方式2: 交互式输入

```bash
# 不带参数运行，提示交互输入
uv run python scripts/config_manager.py
```

### 方式3: 查看当前配置

```bash
uv run python scripts/config_manager.py --show
```

## 配置文件

API Keys 保存在 `config.json` 文件中：

```json
{
  "qwen_api_key": "your-qwen-key",
  "gemini_api_key": "your-gemini-key"
}
```

## 依赖脚本

- **`scripts/config_manager.py`** - 配置管理脚本
- **`config.json`** - 配置文件存储位置
