#!/usr/bin/env python3
"""
Expert Auditor Pro - 双模型审计主程序
并行调用 Qwen 和 Gemini API，生成对比审计报告
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

import httpx
from loguru import logger

# 配置路径
PLUGIN_DIR = Path(__file__).parent.parent
CONFIG_FILE = PLUGIN_DIR / "config.json"
LOG_DIR = Path.home() / ".cache" / "expert-auditor-pro" / "logs"

# 确保日志目录存在
LOG_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_message(message: str) -> str:
    """脱敏函数：过滤敏感信息"""
    # 过滤 Bearer token
    message = re.sub(r'Bearer\s+[A-Za-z0-9\-_]+', 'Bearer ***', message)
    # 过滤 OpenAI API Key
    message = re.sub(r'sk-[A-Za-z0-9]+', 'sk-***', message)
    # 过滤 Google API Key
    message = re.sub(r'AIza[a-zA-Z0-9_-]{35}', 'AIza***', message)
    # 过滤 DashScope API Key
    message = re.sub(r'sk-[A-Za-z0-9]{32,}', 'sk-***', message)
    return message


# 配置 Loguru
logger.configure(
    patcher=lambda record: record.update(message=sanitize_message(str(record["message"])))
)

# stderr 彩色输出 (DEBUG 级别)
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    level="DEBUG",
    colorize=True
)

# JSONL 文件日志
logger.add(
    str(LOG_DIR / "audit.jsonl"),
    level="DEBUG",
    serialize=True,
    rotation="100 MB",
    retention="7 days"
)

logger.info("Expert Auditor Pro 启动")


def load_config() -> dict:
    """加载配置文件"""
    if not CONFIG_FILE.exists():
        logger.error("配置文件不存在")
        raise FileNotFoundError(f"配置文件不存在: {CONFIG_FILE}")

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    if not config.get("qwen_api_key"):
        logger.warning("Qwen API Key 未配置")
    if not config.get("gemini_api_key"):
        logger.warning("Gemini API Key 未配置")

    return config


async def call_qwen(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    plan_content: str,
    proxy: str
) -> dict:
    """调用 Qwen (DashScope) API"""
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    system_prompt = """你是一位资深的代码审查专家和架构师。审查计划时，请从以下6个维度评估：
1. 完整性 - 是否包含所有必要步骤？
2. 正确性 - 计划是否正确解决问题？
3. 安全性 - 是否有防止破坏性操作的保护措施？
4. 可逆性 - 更改是否可以回滚？
5. 安全性 - 是否引入安全漏洞？
6. 最佳实践 - 是否遵循项目约定？

请直接给出审查结论，使用 APPROVE / CONCERNS / REJECT 之一作为开头。"""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请审查以下计划：\n\n{plan_content}"}
        ],
        "temperature": 0.7,
        "max_tokens": 4096
    }

    logger.debug(f"调用 Qwen API, model: {model}")

    try:
        response = await client.post(
            url,
            headers=headers,
            json=payload,
            timeout=60.0,
            proxies={"http://": proxy, "https://": proxy}
        )
        response.raise_for_status()
        result = response.json()

        logger.info("Qwen API 调用成功")
        return {
            "success": True,
            "model": model,
            "content": result["choices"][0]["message"]["content"],
            "usage": result.get("usage", {})
        }
    except httpx.HTTPStatusError as e:
        logger.error(f"Qwen API HTTP 错误: {e.response.status_code}")
        return {
            "success": False,
            "model": model,
            "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        }
    except Exception as e:
        logger.error(f"Qwen API 调用失败: {str(e)}")
        return {
            "success": False,
            "model": model,
            "error": str(e)
        }


async def call_gemini(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    plan_content: str,
    proxy: str
) -> dict:
    """调用 Gemini API"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {
        "Content-Type": "application/json"
    }

    system_prompt = """你是一位资深的代码审查专家和架构师。审查计划时，请从以下6个维度评估：
1. 完整性 - 是否包含所有必要步骤？
2. 正确性 - 计划是否正确解决问题？
3. 安全性 - 是否有防止破坏性操作的保护措施？
4. 可逆性 - 更改是否可以回滚？
5. 安全性 - 是否引入安全漏洞？
6. 最佳实践 - 是否遵循项目约定？

请直接给出审查结论，使用 APPROVE / CONCERNS / REJECT 之一作为开头。"""

    payload = {
        "systemInstruction": {
            "role": "user",
            "parts": [{"text": system_prompt}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"请审查以下计划：\n\n{plan_content}"}]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 4096
        }
    }

    logger.debug(f"调用 Gemini API, model: {model}")

    try:
        response = await client.post(
            url,
            headers=headers,
            json=payload,
            timeout=60.0,
            proxies={"http://": proxy, "https://": proxy}
        )
        response.raise_for_status()
        result = response.json()

        logger.info("Gemini API 调用成功")
        return {
            "success": True,
            "model": model,
            "content": result["candidates"][0]["content"]["parts"][0]["text"],
            "usage": result.get("usageMetadata", {})
        }
    except httpx.HTTPStatusError as e:
        logger.error(f"Gemini API HTTP 错误: {e.response.status_code}")
        return {
            "success": False,
            "model": model,
            "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        }
    except Exception as e:
        logger.error(f"Gemini API 调用失败: {str(e)}")
        return {
            "success": False,
            "model": model,
            "error": str(e)
        }


async def audit_plan(plan_content: str) -> dict:
    """
    并行调用双模型审计计划
    """
    config = load_config()

    proxy = config.get("proxy", "")
    qwen_api_key = config.get("qwen_api_key", "")
    gemini_api_key = config.get("gemini_api_key", "")
    qwen_model = config.get("qwen_model", "qwen3.5-plus")
    gemini_model = config.get("gemini_model", "gemini-3.1-pro-preview")

    # 检查是否有可用的 API
    if not qwen_api_key and not gemini_api_key:
        logger.error("无可用的 API")
        return {
            "error": "请先配置 API Key，使用 /setup_skill 命令"
        }

    # 创建异步客户端
        # 并行调用双模型
        tasks = []

        if qwen_api_key:
            tasks.append(call_qwen(client, qwen_api_key, qwen_model, plan_content, proxy))
        else:
            logger.warning("跳过 Qwen API 调用（未配置 API Key）")

        if gemini_api_key:
            tasks.append(call_gemini(client, gemini_api_key, gemini_model, plan_content, proxy))
        else:
            logger.warning("跳过 Gemini API 调用（未配置 API Key）")

        if not tasks:
            logger.error("无可用的 API")
            return {
                "error": "请先配置 API Key，使用 /setup_skill 命令"
            }

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 收集结果
        qwen_result = None
        gemini_result = None

        for result in results:
            if isinstance(result, dict):
                if result.get("model", "").startswith("qwen"):
                    qwen_result = result
                elif result.get("model", "").startswith("gemini"):
                    gemini_result = result
            elif isinstance(result, Exception):
                logger.error(f"并行调用异常: {result}")

        return {
            "qwen": qwen_result,
            "gemini": gemini_result
        }


def generate_markdown_report(results: dict) -> str:
    """生成 Markdown 格式的审计报告"""
    report_lines = [
        "# 双模型审计报告",
        "",
        "---",
        ""
    ]

    # Qwen 结果
    qwen = results.get("qwen")
    if qwen:
        report_lines.extend([
            "## Qwen 审查结果",
            "",
            f"**模型**: {qwen.get('model', 'N/A')}",
            ""
        ])
        if qwen.get("success"):
            report_lines.append(qwen.get("content", ""))
        else:
            report_lines.append(f"❌ 错误: {qwen.get('error', '未知错误')}")
        report_lines.extend(["", "---", ""])

    # Gemini 结果
    gemini = results.get("gemini")
    if gemini:
        report_lines.extend([
            "## Gemini 审查结果",
            "",
            f"**模型**: {gemini.get('model', 'N/A')}",
            ""
        ])
        if gemini.get("success"):
            report_lines.append(gemini.get("content", ""))
        else:
            report_lines.append(f"❌ 错误: {gemini.get('error', '未知错误')}")
        report_lines.extend(["", "---", ""])

    # 综合结论
    report_lines.extend([
        "## 综合结论",
        ""
    ])

    # 简单汇总
    conclusions = []
    if qwen and qwen.get("success"):
        content = qwen.get("content", "")
        if content.upper().startswith("APPROVE"):
            conclusions.append("✅ Qwen: APPROVE")
        elif content.upper().startswith("CONCERNS"):
            conclusions.append("⚠️ Qwen: CONCERNS")
        elif content.upper().startswith("REJECT"):
            conclusions.append("❌ Qwen: REJECT")

    if gemini and gemini.get("success"):
        content = gemini.get("content", "")
        if content.upper().startswith("APPROVE"):
            conclusions.append("✅ Gemini: APPROVE")
        elif content.upper().startswith("CONCERNS"):
            conclusions.append("⚠️ Gemini: CONCERNS")
        elif content.upper().startswith("REJECT"):
            conclusions.append("❌ Gemini: REJECT")

    if conclusions:
        report_lines.extend(conclusions)
    else:
        report_lines.append("⚠️ 至少一个模型调用失败，请检查配置")

    return "\n".join(report_lines)


async def main():
    """主入口"""
    # 从 stdin 读取 JSON 输入
    try:
        input_data = json.load(sys.stdin)
        plan_content = input_data.get("plan", "")
    except json.JSONDecodeError:
        # 尝试从参数读取
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--plan-file", action="store_true", help="从 stdin 读取计划")
        parser.add_argument("plan", nargs="*", default="")
        args = parser.parse_args()

        if args.plan:
            plan_content = " ".join(args.plan)
        else:
            # 尝试从 stdin 读取原始内容
            plan_content = sys.stdin.read()

    if not plan_content:
        logger.error("未提供计划内容")
        print("错误: 请提供计划内容", file=sys.stderr)
        sys.exit(1)

    logger.info("开始审计计划")
    results = await audit_plan(plan_content)

    # 生成报告
    report = generate_markdown_report(results)
    print("\n" + report)

    # 返回 JSON 结果（用于程序化处理）
    return results


if __name__ == "__main__":
    asyncio.run(main())
