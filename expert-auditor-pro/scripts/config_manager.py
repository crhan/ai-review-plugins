#!/usr/bin/env python3
"""
配置管理模块
读写 config.json
"""
import json
import argparse
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent / "config.json"

def load_config() -> dict:
    """加载配置文件"""
    if not CONFIG_FILE.exists():
        return {
            "qwen_api_key": "",
            "gemini_api_key": "",
            "qwen_model": "qwen3.5-plus",
            "gemini_model": "gemini-3.1-pro-preview",
            "proxy": "http://127.0.0.1:7890"
        }
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config: dict) -> None:
    """保存配置文件"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def set_qwen_key(key: str) -> None:
    """设置 Qwen API Key"""
    config = load_config()
    config["qwen_api_key"] = key
    save_config(config)
    print("Qwen API Key 已保存")

def set_gemini_key(key: str) -> None:
    """设置 Gemini API Key"""
    config = load_config()
    config["gemini_api_key"] = key
    save_config(config)
    print("Gemini API Key 已保存")

def main():
    parser = argparse.ArgumentParser(description="配置管理工具")
    parser.add_argument("--set-qwen-key", type=str, help="设置 Qwen API Key")
    parser.add_argument("--set-gemini-key", type=str, help="设置 Gemini API Key")

    args = parser.parse_args()

    if args.set_qwen_key:
        set_qwen_key(args.set_qwen_key)
    elif args.set_gemini_key:
        set_gemini_key(args.set_gemini_key)
    else:
        config = load_config()
        # 打印配置（隐藏 API Key）
        config_display = config.copy()
        if config_display.get("qwen_api_key"):
            config_display["qwen_api_key"] = "***" + config_display["qwen_api_key"][-4:]
        if config_display.get("gemini_api_key"):
            config_display["gemini_api_key"] = "***" + config_display["gemini_api_key"][-4:]
        print(json.dumps(config_display, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
