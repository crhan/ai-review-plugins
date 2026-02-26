#!/usr/bin/env python3
"""
Expert Auditor Pro - 双模型审计主程序
并行调用 Qwen 和 Gemini API，生成对比审计报告
"""
import asyncio
import json
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
from loguru import logger


def generate_request_id() -> str:
    """生成请求 ID（8位十六进制）"""
    return uuid.uuid4().hex[:8]


# 全局 request_id
_request_id = ""


def _update_log_record(record):
    """更新日志记录，添加 request_id"""
    record["extra"].setdefault("request_id", _request_id)
    record["message"] = sanitize_message(str(record["message"]))

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


# 配置 Loguru - 移除默认 handler，使用自定义格式
logger.configure(
    patcher=_update_log_record,
    handlers=[]
)

# stderr 彩色输出 (DEBUG 级别)
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <cyan>{extra[request_id]: <8}</cyan> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
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


def parse_decision_from_content(content: str) -> dict:
    """从模型返回的文本中解析 decision/reason/feedback"""
    import re

    # 尝试 1: 直接解析整个 content 为 JSON
    try:
        data = json.loads(content.strip())
        if isinstance(data, dict) and "decision" in data:
            return {
                "decision": data.get("decision", "CONCERNS"),
                "reason": data.get("reason", ""),
                "feedback": data.get("feedback", "")
            }
    except (json.JSONDecodeError, AttributeError):
        pass

    # 尝试 2: 从 JSON 块中提取
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            if "decision" in data:
                return {
                    "decision": data.get("decision", "CONCERNS"),
                    "reason": data.get("reason", ""),
                    "feedback": data.get("feedback", "")
                }
        except json.JSONDecodeError:
            pass

    # 尝试 3: 从文本开头提取关键词
    content_upper = content.strip().upper()
    if content_upper.startswith("APPROVE"):
        return {"decision": "APPROVE", "reason": "Model approved", "feedback": ""}
    elif content_upper.startswith("CONCERNS"):
        return {"decision": "CONCERNS", "reason": "Model has concerns", "feedback": content}
    elif content_upper.startswith("REJECT"):
        return {"decision": "REJECT", "reason": "Model rejected", "feedback": content}

    # 默认
    return {"decision": "CONCERNS", "reason": "Unable to parse decision", "feedback": content}


def merge_results(qwen_result: dict, gemini_result: dict) -> dict:
    """
    共识模式 B 决策：
    - 任一 REJECT → REJECT
    - 两个 APPROVE → APPROVE
    - 一个 APPROVE + 一个 CONCERNS → 警告通过
    - 两个 CONCERNS → REJECT
    - 任一失败 → 视为 CONCERNS
    """
    # 处理 None 情况
    qwen_result = qwen_result or {}
    gemini_result = gemini_result or {}

    # 提取决策
    qwen_decision = qwen_result.get("decision", "CONCERNS") if qwen_result.get("success") else "CONCERNS"
    gemini_decision = gemini_result.get("decision", "CONCERNS") if gemini_result.get("success") else "CONCERNS"

    qwen_reason = qwen_result.get("reason", "")
    gemini_reason = gemini_result.get("reason", "")

    # 任一 REJECT
    if qwen_decision == "REJECT" or gemini_decision == "REJECT":
        return {
            "decision": "REJECT",
            "reason": qwen_reason or gemini_reason or "Model rejected",
            "feedback": qwen_result.get("feedback", "") or gemini_result.get("feedback", ""),
            "model": "qwen" if qwen_decision == "REJECT" else "gemini"
        }

    # 两个 CONCERNS
    if qwen_decision == "CONCERNS" and gemini_decision == "CONCERNS":
        return {
            "decision": "REJECT",
            "reason": "Both models have concerns",
            "feedback": f"Qwen: {qwen_reason}\nGemini: {gemini_reason}",
            "model": "both"
        }

    # 一个 APPROVE + 一个 CONCERNS
    if (qwen_decision == "APPROVE" and gemini_decision == "CONCERNS") or \
       (qwen_decision == "CONCERNS" and gemini_decision == "APPROVE"):
        return {
            "decision": "APPROVE",
            "reason": "Approved with warnings",
            "feedback": f"Warning: {qwen_reason or gemini_reason or 'One model has concerns'}",
            "model": "qwen" if gemini_decision == "CONCERNS" else "gemini"
        }

    # 两个 APPROVE
    return {
        "decision": "APPROVE",
        "reason": qwen_reason or "Both approved",
        "model": "both"
    }


async def call_qwen(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    plan_content: str,
    proxy: str,
    context: dict
) -> dict:
    """调用 Qwen (DashScope) API"""
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 从 context 中提取上下文（限制长度以避免超时）
    global_claude = context.get("global_claude", "")[:3000] if context.get("global_claude") else ""
    project_claude = context.get("project_claude", "")[:2000] if context.get("project_claude") else ""
    recent_messages = context.get("recent_messages", "")[:1500] if context.get("recent_messages") else ""

    system_prompt = f"""你是一位资深的代码审查专家和架构师。审查计划时，请从以下6个维度评估：
1. 完整性 - 是否包含所有必要步骤？
2. 正确性 - 计划是否正确解决问题？
3. 安全性 - 是否有防止破坏性操作的保护措施？
4. 可逆性 - 更改是否可以回滚？
5. 安全性 - 是否引入安全漏洞？
6. 最佳实践 - 是否遵循项目约定？

## 上下文

### 全局 CLAUDE.md
{global_claude if global_claude else "(无)"}

### 项目 CLAUDE.md
{project_claude if project_claude else "(无)"}

### 近期用户消息
{recent_messages if recent_messages else "(无)"}

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

    start_time = time.time()
    try:
        response = await client.post(
            url,
            headers=headers,
            json=payload,
            timeout=120.0
        )
        response.raise_for_status()
        result = response.json()

        elapsed = time.time() - start_time
        logger.info(f"Qwen API call completed in {elapsed:.2f}s")

        # DEBUG 级别记录响应
        content = result["choices"][0]["message"]["content"]
        logger.debug(f"Qwen response:\n{content[:500]}...")

        # 解析 decision
        decision_data = parse_decision_from_content(content)

        logger.info(f"Qwen decision: {decision_data['decision']}, reason: {decision_data['reason'][:50]}")

        return {
            "success": True,
            "model": model,
            "content": content,
            "decision": decision_data["decision"],
            "reason": decision_data["reason"],
            "feedback": decision_data["feedback"],
            "usage": result.get("usage", {})
        }
    except httpx.HTTPStatusError as e:
        elapsed = time.time() - start_time
        logger.error(f"Qwen API HTTP 错误: {e.response.status_code} (after {elapsed:.2f}s)")
        return {
            "success": False,
            "model": model,
            "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        }
    except Exception as e:
        import traceback
        logger.error(f"Qwen API 调用失败: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}")
        return {
            "success": False,
            "model": model,
            "error": f"{type(e).__name__}: {str(e)}"
        }


async def call_gemini(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    plan_content: str,
    proxy: str,
    context: dict
) -> dict:
    """调用 Gemini API"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {
        "Content-Type": "application/json"
    }

    # 从 context 中提取上下文（限制长度以避免超时）
    global_claude = context.get("global_claude", "")[:3000] if context.get("global_claude") else ""
    project_claude = context.get("project_claude", "")[:2000] if context.get("project_claude") else ""
    recent_messages = context.get("recent_messages", "")[:1500] if context.get("recent_messages") else ""

    system_prompt = f"""你是一位资深的代码审查专家和架构师。审查计划时，请从以下6个维度评估：
1. 完整性 - 是否包含所有必要步骤？
2. 正确性 - 计划是否正确解决问题？
3. 安全性 - 是否有防止破坏性操作的保护措施？
4. 可逆性 - 更改是否可以回滚？
5. 安全性 - 是否引入安全漏洞？
6. 最佳实践 - 是否遵循项目约定？

## 上下文

### 全局 CLAUDE.md
{global_claude if global_claude else "(无)"}

### 项目 CLAUDE.md
{project_claude if project_claude else "(无)"}

### 近期用户消息
{recent_messages if recent_messages else "(无)"}

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

    start_time = time.time()
    try:
        response = await client.post(
            url,
            headers=headers,
            json=payload,
            timeout=120.0
        )
        response.raise_for_status()
        result = response.json()

        elapsed = time.time() - start_time
        logger.info(f"Gemini API call completed in {elapsed:.2f}s")

        # DEBUG 级别记录响应
        content = result["candidates"][0]["content"]["parts"][0]["text"]
        logger.debug(f"Gemini response:\n{content[:500]}...")

        # 解析 decision
        decision_data = parse_decision_from_content(content)

        logger.info(f"Gemini decision: {decision_data['decision']}, reason: {decision_data['reason'][:50]}")

        return {
            "success": True,
            "model": model,
            "content": content,
            "decision": decision_data["decision"],
            "reason": decision_data["reason"],
            "feedback": decision_data["feedback"],
            "usage": result.get("usageMetadata", {})
        }
    except httpx.HTTPStatusError as e:
        elapsed = time.time() - start_time
        logger.error(f"Gemini API HTTP 错误: {e.response.status_code} (after {elapsed:.2f}s)")
        return {
            "success": False,
            "model": model,
            "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        }
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Gemini API 调用失败: {str(e)} (after {elapsed:.2f}s)")
        return {
            "success": False,
            "model": model,
            "error": str(e)
        }


def load_global_claude() -> str:
    """读取全局 CLAUDE.md"""
    global_path = Path.home() / ".claude" / "CLAUDE.md"
    if global_path.exists():
        return global_path.read_text(encoding="utf-8")
    return ""


def load_project_claude(cwd: str) -> str:
    """读取项目 CLAUDE.md"""
    if not cwd:
        return ""
    project_path = Path(cwd) / "CLAUDE.md"
    if project_path.exists():
        return project_path.read_text(encoding="utf-8")
    return ""


def load_recent_messages(transcript_path: str, limit: int = 5) -> str:
    """从 transcript JSONL 读取最近 N 条用户消息"""
    if not transcript_path:
        return ""
    transcript = Path(transcript_path)
    if not transcript.exists():
        return ""

    try:
        lines = transcript.read_text().splitlines()
        user_msgs = []
        for line in lines[-50:]:  # 扫描最近50条
            try:
                msg = json.loads(line)
                if msg.get("type") == "user":
                    content = msg.get("message", {}).get("content", {})
                    text = content.get("text", "")
                    if text:
                        user_msgs.append(text)
            except json.JSONDecodeError:
                continue
        return "\n".join(user_msgs[-limit:])
    except Exception:
        return ""


async def audit_plan(context: dict) -> dict:
    """
    并行调用双模型审计计划
    context: 包含 plan, session_id, cwd, transcript_path 的字典
    """
    plan_content = context.get("plan", "")
    session_id = context.get("session_id", "")
    cwd = context.get("cwd", "")
    transcript_path = context.get("transcript_path", "")

    logger.info(f"开始审计计划, session_id: {session_id}, cwd: {cwd}")

    # 组装上下文
    global_claude = load_global_claude()
    project_claude = load_project_claude(cwd)
    recent_messages = load_recent_messages(transcript_path)

    logger.debug(f"Loaded context: global_claude={len(global_claude)} chars, project_claude={len(project_claude)} chars, recent_messages={len(recent_messages)} chars")

    # 构建传递给 API 的 context
    context = {
        "global_claude": global_claude,
        "project_claude": project_claude,
        "recent_messages": recent_messages
    }

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
    async with httpx.AsyncClient(proxy=proxy if proxy else None) as client:
        # 并行调用双模型
        tasks = []
        call_count = 0

        logger.info(f"Calling reviewers (timeout: 120s)...")

        if qwen_api_key:
            tasks.append(call_qwen(client, qwen_api_key, qwen_model, plan_content, proxy, context))
            call_count += 1
        else:
            logger.warning("跳过 Qwen API 调用（未配置 API Key）")

        if gemini_api_key:
            tasks.append(call_gemini(client, gemini_api_key, gemini_model, plan_content, proxy, context))
            call_count += 1
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

        # 合并结果
        merged = merge_results(qwen_result or {}, gemini_result or {})
        decision = merged.get("decision", "APPROVE")

        logger.info(f"Merge decision: {decision}")

        return {
            "qwen": qwen_result,
            "gemini": gemini_result,
            "merged": merged
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

    # 添加最终决定（使用 merged 结果）
    merged = results.get("merged", {})
    if merged:
        decision = merged.get("decision", "APPROVE")
        reason = merged.get("reason", "")
        feedback = merged.get("feedback", "")
        if decision == "APPROVE":
            report_lines.append(f"✅ 最终决定: APPROVE - {reason}")
        elif decision == "CONCERNS":
            report_lines.append(f"⚠️ 最终决定: CONCERNS - {reason}")
        else:
            report_lines.append(f"❌ 最终决定: REJECT - {reason}")

        if feedback:
            report_lines.extend(["", f"**反馈**: {feedback}"])
    else:
        report_lines.append("⚠️ 至少一个模型调用失败，请检查配置")

    return "\n".join(report_lines)


async def main():
    """主入口"""
    global _request_id
    _request_id = generate_request_id()

    logger.info("Script started")

    # 默认 context
    context = {
        "plan": "",
        "session_id": "",
        "cwd": "",
        "transcript_path": ""
    }

    # 先解析命令行参数（因为 stdin 只能读一次）
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-file", action="store_true", help="从 stdin 读取计划")
    parser.add_argument("plan", nargs="*", default="")
    args = parser.parse_args()

    # 如果有命令行参数，优先使用
    if args.plan:
        context["plan"] = " ".join(args.plan)
        logger.debug("Using command line arguments")
    else:
        # 从 stdin 读取内容
        stdin_content = sys.stdin.read()

        # 尝试解析 JSON
        try:
            if stdin_content.strip():
                input_data = json.loads(stdin_content)
                context["plan"] = input_data.get("plan", "")
                context["session_id"] = input_data.get("session_id", "")
                context["cwd"] = input_data.get("cwd", "")
                context["transcript_path"] = input_data.get("transcript_path", "")
                logger.debug(f"Input parsed, tool: {input_data.get('tool_name', 'N/A')}")
        except json.JSONDecodeError:
            # 不是 JSON，使用原始内容
            context["plan"] = stdin_content
            logger.debug("Input parsed as raw text")

    logger.debug(f"Plan length: {len(context['plan'])} chars")

    if not context["plan"]:
        logger.error("未提供计划内容")
        print("错误: 请提供计划内容", file=sys.stderr)
        sys.exit(1)

    results = await audit_plan(context)

    # 生成报告
    report = generate_markdown_report(results)
    print("\n" + report)

    # 返回 JSON 结果（用于程序化处理）
    return results


if __name__ == "__main__":
    asyncio.run(main())
