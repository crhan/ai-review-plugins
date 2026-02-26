---
name: setup-skill
description: This skill should be used when the user asks to "configure API keys", "setup API keys", "configure Qwen", "configure Gemini", "设置 API Keys", or needs to set up Qwen/Gemini API keys for the expert-auditor-pro plugin.
version: 1.0.0
---

# setup-skill

交互式录入并保存 API Keys 到 config.json。

## 使用场景

- 首次配置插件
- 更新 API Keys
- 查看当前配置状态

## 执行流程

1. 提示用户输入 Qwen API Key
2. 提示用户输入 Gemini API Key
3. 调用 config_manager.py 保存配置

## 配置方式

### 方式1: 命令行参数

```bash
# 设置 Qwen API Key
python3 scripts/config_manager.py --set-qwen-key "YOUR_QWEN_KEY"

# 设置 Gemini API Key
python3 scripts/config_manager.py --set-gemini-key "YOUR_GEMINI_KEY"

# 同时设置两个
python3 scripts/config_manager.py --set-qwen-key "YOUR_QWEN_KEY" --set-gemini-key "YOUR_GEMINI_KEY"
```

### 方式2: 交互式输入

```bash
# 不带参数运行，提示交互输入
python3 scripts/config_manager.py
```

### 方式3: 查看当前配置

```bash
python3 scripts/config_manager.py --show
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
