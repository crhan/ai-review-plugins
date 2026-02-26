# setup_skill

交互式录入 API Keys，直接写入 config.json。

## 操作步骤

1. 提示用户输入 Qwen API Key
2. 提示用户输入 Gemini API Key
3. 调用 config_manager.py 保存配置

## 调用命令

```bash
python3 scripts/config_manager.py --set-qwen-key "YOUR_QWEN_KEY"
python3 scripts/config_manager.py --set-gemini-key "YOUR_GEMINI_KEY"
```
