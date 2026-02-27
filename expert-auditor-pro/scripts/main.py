#!/usr/bin/env python3
"""
Expert Auditor Pro - 双模型审计主程序
并行调用 Qwen 和 Gemini API，生成对比审计报告
"""
import asyncio
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
from loguru import logger

from paths import get_config_path, LOG_DIR, ensure_dirs, CONFIG_FILE

# 启动时确保目录存在
ensure_dirs()


def generate_request_id() -> str:
    """生成请求 ID（8位十六进制）"""
    return uuid.uuid4().hex[:8]


# 全局 request_id
_request_id = ""


def _update_log_record(record):
    """更新日志记录，添加 request_id"""
    record["extra"].setdefault("request_id", _request_id)
    record["message"] = sanitize_message(str(record["message"]))


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


def info_filter(record):
    """仅接受 INFO 级别"""
    return record["level"].name == "INFO"


def debug_filter(record):
    """仅接受 DEBUG 级别"""
    return record["level"].name == "DEBUG"


# stderr 彩色输出 (INFO 级别，用户可见)
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    level="INFO",
    colorize=True
)

# JSONL 日志文件 - 仅 INFO 级别
logger.add(
    str(LOG_DIR / "info.jsonl"),
    level="INFO",
    filter=info_filter,
    serialize=True,
    rotation="50 MB",
    retention="7 days"
)

# JSONL 日志文件 - 仅 DEBUG 级别（完整信息）
logger.add(
    str(LOG_DIR / "debug.jsonl"),
    level="DEBUG",
    filter=debug_filter,
    serialize=True,
    rotation="100 MB",
    retention="7 days"
)

logger.info("Expert Auditor Pro 启动")


def load_config() -> dict:
    """加载配置文件"""
    config_path = get_config_path()
    if not config_path.exists():
        logger.error("配置文件不存在")
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
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

    # 从 context 中提取上下文（不限制长度）
    global_claude = context.get("global_claude", "") if context.get("global_claude") else ""
    review_notes = context.get("review_notes", "") if context.get("review_notes") else ""
    project_claude = context.get("project_claude", "") if context.get("project_claude") else ""
    recent_messages = context.get("recent_messages", "") if context.get("recent_messages") else ""

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

### 前期审查反馈
{review_notes if review_notes else "(本轮为首轮审查，无历史反馈)"}

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

    logger.debug(f"Calling Qwen, model: {model}, prompt length: {len(system_prompt) + len(plan_content)}")

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
        logger.info(f"Qwen done in {elapsed:.1f}s")

        # DEBUG 级别记录完整响应
        content = result["choices"][0]["message"]["content"]
        logger.debug(f"Qwen response ({len(content)} chars):\n{content[:800]}...")

        # 解析 decision
        decision_data = parse_decision_from_content(content)

        logger.info(f"Qwen: {decision_data['decision']}")

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

    # 从 context 中提取上下文（不限制长度）
    global_claude = context.get("global_claude", "") if context.get("global_claude") else ""
    review_notes = context.get("review_notes", "") if context.get("review_notes") else ""
    project_claude = context.get("project_claude", "") if context.get("project_claude") else ""
    recent_messages = context.get("recent_messages", "") if context.get("recent_messages") else ""

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

### 前期审查反馈
{review_notes if review_notes else "(本轮为首轮审查，无历史反馈)"}

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

    logger.debug(f"Calling Gemini, model: {model}, prompt length: {len(system_prompt) + len(plan_content)}")

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
        logger.info(f"Gemini done in {elapsed:.1f}s")

        # DEBUG 级别记录完整响应
        content = result["candidates"][0]["content"]["parts"][0]["text"]
        logger.debug(f"Gemini response ({len(content)} chars):\n{content[:800]}...")

        # 解析 decision
        decision_data = parse_decision_from_content(content)

        logger.info(f"Gemini: {decision_data['decision']}")

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
    project_path = Path(cwd)
    # 向上查找 CLAUDE.md，直到根目录
    while project_path != project_path.parent:
        claude_path = project_path / "CLAUDE.md"
        if claude_path.exists():
            return claude_path.read_text(encoding="utf-8")
        project_path = project_path.parent
    return ""


def find_transcript_by_cwd(cwd: str) -> str:
    """根据 cwd 自动查找对应的 transcript 文件

    查找规则：
    1. 从 cwd 向上遍历，尝试匹配项目目录名
    2. 返回最近修改的 .jsonl 文件
    """
    logger.debug(f"find_transcript_by_cwd called: {cwd}")
    if not cwd:
        return ""

    try:
        cwd_path = Path(cwd).resolve()
        logger.debug(f"cwd_path={cwd_path}")

        # 查找项目目录
        claude_projects = Path.home() / ".claude" / "projects"
        logger.debug(f"claude_projects={claude_projects}, exists={claude_projects.exists()}")

        if not claude_projects.exists():
            return ""

        # 从 cwd 向上遍历，尝试匹配目录名
        current = cwd_path
        while True:
            # 尝试匹配项目目录
            parts = current.parts
            logger.debug(f"checking {current}")

            if len(parts) >= 3 and parts[1] == "Users":
                username = parts[2]
                # 构建目录名格式
                path_parts = parts[3:]
                if path_parts:
                    dir_name = "-".join(["Users"] + [username.replace(".", "-")] + list(path_parts))
                else:
                    dir_name = f"Users-{username.replace('.', '-')}"

                proj_dir = claude_projects / f"-{dir_name}"
                logger.debug(f"Checking proj_dir={proj_dir}, exists={proj_dir.exists()}")
                if proj_dir.exists():
                    jsonl_files = list(proj_dir.glob("*.jsonl"))
                    logger.debug(f"Found {len(jsonl_files)} jsonl files")
                    if jsonl_files:
                        latest = max(jsonl_files, key=lambda p: p.stat().st_mtime)
                        logger.debug(f"Auto-found transcript: {latest.name}")
                        return str(latest)

            # 向上遍历一层
            if current.parent == current:
                break  # 已经到根目录
            current = current.parent

        return ""

    except Exception as e:
        logger.debug(f"Failed to find transcript by cwd: {e}")
        return ""


def extract_message_content(msg: dict) -> str:
    """从消息中提取文本内容"""
    message = msg.get("message", {})
    if not isinstance(message, dict):
        return ""

    content = message.get("content", "")
    if isinstance(content, str) and content:
        # 过滤 IDE 元信息
        content = filter_ide_metadata(content)
        return content
    elif isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                item_type = item.get("type", "")
                # text 类型：直接提取
                if item_type == "text":
                    text = item.get("text", "")
                    if text:
                        # 过滤 IDE 元信息
                        text_parts.append(filter_ide_metadata(text))
                # thinking 类型：提取思考内容（用于 assistant）
                elif item_type == "thinking":
                    thinking = item.get("thinking", "")
                    if thinking:
                        text_parts.append(thinking)
                # tool_result 类型：提取工具输出（用于 user）
                elif item_type == "tool_result":
                    tool_content = item.get("content", "")
                    if tool_content:
                        text_parts.append(str(tool_content))
        return "\n".join(text_parts)
    return ""


def filter_ide_metadata(text: str) -> str:
    """过滤 IDE 元信息，如 <ide_opened_file>..."""
    import re
    if not text:
        return ""
    # 移除 <ide_opened_file>...</ide_opened_file> 标签
    text = re.sub(r"<ide_opened_file>[^<]*</ide_opened_file>\n?", "", text)
    # 移除 <command-message>...</command-message> 标签
    text = re.sub(r"<command-message>[^<]*</command-message>\n?", "", text)
    # 移除 <command-name>...</command-name> 标签
    text = re.sub(r"<command-name>[^<]*</command-name>\n?", "", text)
    # 移除 <command-args>...</command-args> 标签
    text = re.sub(r"<command-args>[^<]*</command-args>\n?", "", text)
    return text.strip()


def load_recent_messages(transcript_path: str, cwd: str = "", limit: int = 5) -> str:
    """从 transcript JSONL 读取最近 N 轮对话

    每轮包含：用户消息 + AI 回应
    如果未提供 transcript_path，会尝试根据 cwd 自动查找
    """
    logger.debug(f"load_recent_messages called: transcript_path={transcript_path[:50] if transcript_path else 'None'}..., cwd={cwd[:30] if cwd else 'None'}...")

    # 如果没有提供 path，尝试自动查找
    logger.debug(f"Looking for transcript, initial transcript_path={transcript_path[:30] if transcript_path else 'None'}")
    if not transcript_path and cwd:
        transcript_path = find_transcript_by_cwd(cwd)
        logger.debug(f"After find_transcript_by_cwd: transcript_path={transcript_path[:30] if transcript_path else 'None'}")
        if transcript_path:
            logger.debug(f"Auto-found transcript: {transcript_path}")

    if not transcript_path:
        logger.debug("No transcript_path found, returning empty")
        return ""

    transcript = Path(transcript_path)
    logger.debug(f"Transcript path: {transcript}, exists={transcript.exists()}")
    if not transcript.exists():
        return ""

    try:
        lines = transcript.read_text().splitlines()
        logger.debug(f"Transcript has {len(lines)} lines, starting to parse...")

        # 按轮次组织对话
        rounds = []
        current_user_msg = None
        current_assistant_msg = None
        processed = 0

        for line in lines:
            processed += 1
            if processed % 500 == 0:
                logger.debug(f"Processed {processed} lines...")

            try:
                msg = json.loads(line)
                msg_type = msg.get("type")

                if msg_type == "user":
                    # 如果已有 user 消息，说明遇到了新的轮次，保存上一轮
                    if current_user_msg is not None:
                        rounds.append((current_user_msg, current_assistant_msg))
                    # 开始新轮
                    current_user_msg = extract_message_content(msg)
                    current_assistant_msg = None

                elif msg_type == "assistant":
                    # 记录 AI 回应
                    content = extract_message_content(msg)
                    if content:  # 只有当有实际内容时才更新
                        current_assistant_msg = content

            except json.JSONDecodeError:
                continue

        # 保存最后一轮
        logger.debug(f"Saving last round: current_user_msg={current_user_msg is not None}, current_assistant_msg={current_assistant_msg is not None}")
        if current_user_msg is not None:
            rounds.append((current_user_msg, current_assistant_msg))

        logger.info(f"Found {len(rounds)} rounds")

        # 取最近 N 轮
        recent_rounds = rounds[-limit:] if rounds else []
        logger.debug(f"Taking last {limit} rounds, got {len(recent_rounds)}")

        # 组装结果
        result_parts = []
        for i, (user_msg, assistant_msg) in enumerate(recent_rounds):
            if user_msg:
                result_parts.append(f"## 轮次 {i + 1}\n\n### 用户\n{user_msg}\n\n### AI\n{assistant_msg or '(无回应)'}")

        result = "\n\n".join(result_parts)
        logger.debug(f"Assembled result: {len(result)} chars, {len(result_parts)} rounds")
        return result

    except Exception as e:
        logger.info(f"Failed to load messages: {e}")
        return ""


def load_review_notes(plan_path: str) -> str:
    """根据 plan 文件路径加载对应的 review-notes

    查找规则：plan.md -> plan-review-notes.md
    """
    if not plan_path:
        logger.debug("No plan_path provided, skipping review_notes")
        return ""

    plan_file = Path(plan_path).resolve()  # 解析绝对路径防止路径遍历

    # 锁定在项目 docs/plans 目录内
    if not str(plan_file).startswith(str(Path.cwd() / "docs" / "plans")):
        logger.debug(f"plan_path outside allowed directory: {plan_path}")
        return ""

    if not plan_file.exists():
        logger.debug(f"Plan file not found: {plan_path}")
        return ""

    # 构建 review-notes 路径
    review_notes_path = plan_file.with_name(plan_file.stem + "-review-notes.md")

    if review_notes_path.exists():
        try:
            content = review_notes_path.read_text(encoding="utf-8", errors="replace")
            logger.debug(f"Loaded review notes: {len(content)} chars from {review_notes_path.name}")
            return content
        except Exception as e:
            logger.debug(f"Failed to read review notes: {e}")
            return ""

    logger.debug("No review-notes file found")
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

    # 会话信息放 INFO，细节放 DEBUG
    logger.info(f"Audit session: {session_id[:8] if session_id else 'N/A'}, cwd: {cwd[:20] if cwd else 'N/A'}")

    # 记录 plan_path
    plan_path = context.get("plan_path", "")
    logger.info(f"Plan path: {plan_path if plan_path else '(none)'}")

    # 组装上下文
    global_claude = load_global_claude()
    project_claude = load_project_claude(cwd)
    recent_messages = ""  # 已禁用：用户要求不加载 messages

    # 获取 plan_path 并加载 review_notes
    review_notes = load_review_notes(plan_path)

    # INFO 级别记录 review_notes 状态
    if review_notes:
        logger.info(f"Review notes loaded: {len(review_notes)} chars")
    else:
        logger.info("No review notes found (first round or file not exists)")

    # DEBUG: 完整的上下文信息
    logger.debug(f"Context loaded: global={len(global_claude)} chars, project={len(project_claude)} chars, messages={len(recent_messages)} chars, review_notes={len(review_notes)} chars")

    # 构建传递给 API 的 context
    context = {
        "global_claude": global_claude,
        "project_claude": project_claude,
        "recent_messages": recent_messages,
        "review_notes": review_notes
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

        # 统一记录 prompt 统计
        ctx = context  # context 已在前面定义
        logger.info(f"Prompt stats: plan={len(plan_content)} chars, global={len(ctx.get('global_claude', ''))} chars, project={len(ctx.get('project_claude', ''))} chars, review_notes={len(ctx.get('review_notes', ''))} chars")

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
        reason = merged.get("reason", "")

        logger.info(f"Final: {decision} ({merged.get('model', 'N/A')})")

        # DEBUG: 详细原因
        logger.debug(f"Merge details: qwen={qwen_result.get('decision', 'N/A') if qwen_result else 'fail'}, gemini={gemini_result.get('decision', 'N/A') if gemini_result else 'fail'}, reason={reason[:100]}")

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
    parser.add_argument("--plan-file", type=str, help="Plan 文件路径")
    parser.add_argument("plan", nargs="*", default="")
    args = parser.parse_args()

    # 1. 如果指定了 --plan-file，读取文件内容
    if args.plan_file:
        plan_path = Path(args.plan_file)
        if plan_path.exists():
            context["plan"] = plan_path.read_text(encoding="utf-8")
            context["plan_path"] = str(plan_path)
            # 自动设置 cwd 为 plan 文件所在目录
            context["cwd"] = str(plan_path.resolve().parent)
            # 自动设置 transcript_path 从环境变量
            context["transcript_path"] = os.environ.get("CLAUDE_TRANSCRIPT", "")
            logger.info(f"Using plan file: {plan_path}")
        else:
            logger.error(f"Plan file not found: {plan_path}")
            print(f"错误: 文件不存在: {plan_path}", file=sys.stderr)
            sys.exit(1)
    # 2. 如果有命令行参数，使用参数内容
    elif args.plan:
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
                # DEBUG: 完整输入信息
                logger.debug(f"Input: tool={input_data.get('tool_name', 'N/A')}, session={context['session_id'][:8] if context['session_id'] else 'N/A'}, cwd={context['cwd'][:30] if context['cwd'] else 'N/A'}")
        except json.JSONDecodeError:
            # 不是 JSON，使用原始内容
            context["plan"] = stdin_content
            logger.debug("Input: raw text")

    # DEBUG: 计划长度
    logger.debug(f"Plan: {len(context['plan'])} chars")

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
