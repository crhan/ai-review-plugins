#!/usr/bin/env python3
"""
plan-gemini-review.py - Gemini review hook for ExitPlanMode

This script intercepts ExitPlanMode calls and performs Gemini-based review.
It returns APPROVE to pass through, or CONCERNS/REJECT with feedback.
"""

import os
import sys
import json
import subprocess
import logging
import time
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# Get plugin root directory - use explicit path
PLUGIN_DIR = Path.home() / ".cache" / "gemini_plan_review"
INFO_LOG = PLUGIN_DIR / "info.log"
DEBUG_LOG = PLUGIN_DIR / "debug.log"

# Ensure directories exist
PLUGIN_DIR.mkdir(parents=True, exist_ok=True)

# Setup logging
# Set root logger level to DEBUG (otherwise default is WARNING, which discards DEBUG/INFO messages)
logging.getLogger().setLevel(logging.DEBUG)

# Remove default handlers
logging.getLogger().handlers.clear()

# Info log handler - records INFO and above
info_handler = logging.FileHandler(INFO_LOG)
info_handler.setLevel(logging.INFO)
info_handler.setFormatter(logging.Formatter(
    "[%(asctime)s] [%(session)s] [%(request)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))

# Debug log handler - records DEBUG and above
debug_handler = logging.FileHandler(DEBUG_LOG)
debug_handler.setLevel(logging.DEBUG)
debug_handler.setFormatter(logging.Formatter(
    "[%(asctime)s] [%(session)s] [%(request)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))

# Console handler
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setFormatter(logging.Formatter(
    "[%(asctime)s] [%(session)s] [%(request)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))

# Add handlers to root logger
logging.getLogger().addHandler(info_handler)
logging.getLogger().addHandler(debug_handler)
logging.getLogger().addHandler(console_handler)

logger = logging.getLogger("plan-gemini-review")

_current_session = ""


def generate_request_id():
    """Generate a unique request ID (random only, no timestamp)"""
    return uuid.uuid4().hex[:8]


class SessionFilter(logging.Filter):
    def filter(self, record):
        record.session = _current_session[:8] if _current_session else "unknown"
        record.request = getattr(record, "_request_id", "-")
        return True


logger.addFilter(SessionFilter())


def log_with_request(request_id: str, logger_func, msg: str, *args, **kwargs):
    """Log with a specific request_id in the extra field."""
    kwargs.setdefault("extra", {})["_request_id"] = request_id
    logger_func(msg, *args, **kwargs)


def set_session(session_id):
    global _current_session
    _current_session = session_id


def call_reviewer(model_type: str, model_name: str, prompt: str, timeout: int, cwd: str = "") -> dict:
    """Call a reviewer model (Gemini or Qwen) and return the decision result."""
    # Generate a unique request_id for this specific call (random only, no timestamp)
    request_id = uuid.uuid4().hex[:8]

    env = os.environ.copy()
    env["http_proxy"] = "http://127.0.0.1:7890"
    env["https_proxy"] = "http://127.0.0.1:7890"

    start_time = time.time()
    log_with_request(request_id, logger.info, f"Calling {model_type}... (timeout: {timeout}s)")

    try:
        if model_type == "gemini":
            cmd = ["gemini", "-m", model_name, "-p", prompt]
        elif model_type == "qwen":
            cmd = ["qwen", "-m", model_name, "-p", prompt, "-o", "json"]
        else:
            return {"success": False, "error": f"Unknown model type: {model_type}"}

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=cwd
        )
        elapsed = time.time() - start_time
        log_with_request(request_id, logger.info, f"{model_type} call completed in {elapsed:.2f}s")

        if result.returncode != 0:
            # Extract key error message for logging
            error_output = result.stderr.strip()
            # Try to extract a short error message
            key_error = "Unknown error"
            if "error" in error_output.lower():
                # Find the error message
                import re
                match = re.search(r'"message":\s*"([^"]+)"', error_output)
                if match:
                    key_error = match.group(1)
                else:
                    # Take first line of error
                    key_error = error_output.split('\n')[0][:100]
            else:
                key_error = error_output[:100] if error_output else "Unknown error"

            log_with_request(request_id, logger.error, f"{model_type} failed (code {result.returncode}): {key_error}")
            log_with_request(request_id, logger.debug, f"{model_type} full stderr: {error_output}")
            return {"success": False, "error": f"Return code: {result.returncode}", "elapsed": elapsed}

        # Parse JSON response
        output = result.stdout.strip()

        if not output:
            log_with_request(request_id, logger.warning, f"{model_type} returned empty result")
            return {"success": False, "error": "Empty result", "elapsed": elapsed}

        # Log response in consistent format (markdown code block)
        result_text = None
        try:
            parsed = json.loads(output)
            if isinstance(parsed, list):
                # Qwen format: extract result from last element
                result_item = parsed[-1] if parsed else {}
                result_text = result_item.get("result", "")
                if result_text:
                    log_with_request(request_id, logger.debug, f"{model_type} response:\n```\n{result_text}\n```")
                else:
                    log_with_request(request_id, logger.debug, f"{model_type} response: {output}")
            else:
                # Gemini format: direct JSON object
                log_with_request(request_id, logger.debug, f"{model_type} response:\n{output}")
        except json.JSONDecodeError:
            log_with_request(request_id, logger.debug, f"{model_type} response: {output}")

        # Extract decision from response
        try:
            parsed = json.loads(output)
            if isinstance(parsed, list):
                # Qwen format: last element contains the result
                result_item = parsed[-1] if parsed else {}
                result_text = result_item.get("result", "")
            else:
                # Gemini format: direct JSON object (not in result field)
                # The entire parsed object IS the decision
                result_text = None  # Will handle directly below

            # Try to extract decision from result text
            if result_text:
                # Qwen format: result_text is a string
                # First, try to parse as JSON
                try:
                    decision_data = json.loads(result_text)
                    decision = decision_data.get("decision", "APPROVE")
                    reason = decision_data.get("reason", "")
                    feedback = decision_data.get("feedback", "")
                    return {
                        "success": True,
                        "decision": decision,
                        "reason": reason,
                        "feedback": feedback,
                        "elapsed": elapsed,
                        "raw": output
                    }
                except json.JSONDecodeError:
                    pass

                # Try to extract JSON from markdown code block
                import re
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', result_text, re.DOTALL)
                if json_match:
                    try:
                        decision_data = json.loads(json_match.group(1))
                        decision = decision_data.get("decision", "APPROVE")
                        reason = decision_data.get("reason", "")
                        feedback = decision_data.get("feedback", "")
                        return {
                            "success": True,
                            "decision": decision,
                            "reason": reason,
                            "feedback": feedback,
                            "elapsed": elapsed,
                            "raw": output
                        }
                    except json.JSONDecodeError:
                        pass

                # If not JSON, treat as plain text response
                # If we couldn't extract a decision, return CONCERNS (don't auto-approve)
                return {
                    "success": True,
                    "decision": "CONCERNS",
                    "reason": "Unable to parse model response as JSON decision",
                    "feedback": f"Raw response: {result_text[:200]}",
                    "elapsed": elapsed,
                    "raw": output
                }
            else:
                # Gemini format: try to extract JSON from output (may be wrapped in markdown)
                import re
                # Try to extract JSON from markdown code block
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', output, re.DOTALL)
                if json_match:
                    try:
                        decision_data = json.loads(json_match.group(1))
                        decision = decision_data.get("decision", "APPROVE")
                        reason = decision_data.get("reason", "")
                        feedback = decision_data.get("feedback", "")
                        return {
                            "success": True,
                            "decision": decision,
                            "reason": reason,
                            "feedback": feedback,
                            "elapsed": elapsed,
                            "raw": output
                        }
                    except json.JSONDecodeError:
                        pass

                # Also try direct JSON parse if output is a JSON object
                if isinstance(parsed, dict) and "decision" in parsed:
                    decision = parsed.get("decision", "APPROVE")
                    reason = parsed.get("reason", "")
                    feedback = parsed.get("feedback", "")
                    return {
                        "success": True,
                        "decision": decision,
                        "reason": reason,
                        "feedback": feedback,
                        "elapsed": elapsed,
                        "raw": output
                    }

                # Fallback: couldn't find decision
                return {
                    "success": True,
                    "decision": "CONCERNS",
                    "reason": "Unable to parse model response as JSON decision",
                    "feedback": f"Raw response: {output[:200]}",
                    "elapsed": elapsed,
                    "raw": output
                }
        except json.JSONDecodeError as e:
            log_with_request(request_id, logger.warning, f"Failed to parse {model_type} response as JSON")
            return {"success": False, "error": "JSON parse error", "elapsed": elapsed}

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        log_with_request(request_id, logger.error, f"{model_type} call timed out after {elapsed:.2f}s")
        return {"success": False, "error": "Timeout", "elapsed": elapsed}
    except FileNotFoundError as e:
        elapsed = time.time() - start_time
        log_with_request(request_id, logger.error, f"{model_type} command not found: {e}")
        return {"success": False, "error": f"Command not found: {e}", "elapsed": elapsed}
    except Exception as e:
        elapsed = time.time() - start_time
        log_with_request(request_id, logger.error, f"{model_type} error: {e}")
        return {"success": False, "error": str(e), "elapsed": elapsed}


def merge_results(gemini_result: dict, qwen_result: dict, main_request_id = None) -> dict:
    """Merge review results from both models.

    Gemini failure is ignored (graceful degradation).
    Only when both models APPROVE do we pass through.
    """
    # Check Qwen result (primary)
    if not qwen_result.get("success"):
        logger.warning(f"Qwen failed: {qwen_result.get('error')}, defaulting to approve")
        # Qwen 失败时放行
        return {"decision": "APPROVE", "reason": "Qwen failed, allowing", "model": "N/A"}

    qwen_decision = qwen_result.get("decision", "APPROVE")
    qwen_reason = qwen_result.get("reason", "")
    qwen_feedback = qwen_result.get("feedback", "")

    if main_request_id:
        log_with_request(main_request_id, logger.info, f"Qwen decision: {qwen_decision}, reason: {qwen_reason}")
    else:
        logger.info(f"Qwen decision: {qwen_decision}, reason: {qwen_reason}")

    # Log Gemini result if available
    if gemini_result.get("success"):
        gemini_decision = gemini_result.get("decision", "APPROVE")
        gemini_reason = gemini_result.get("reason", "")
        if main_request_id:
            log_with_request(main_request_id, logger.info, f"Gemini decision: {gemini_decision}, reason: {gemini_reason}")
        else:
            logger.info(f"Gemini decision: {gemini_decision}, reason: {gemini_reason}")
    else:
        if main_request_id:
            log_with_request(main_request_id, logger.info, f"Gemini failed: {gemini_result.get('error')}, ignoring its opinion")
        else:
            logger.info(f"Gemini failed: {gemini_result.get('error')}, ignoring its opinion")

    # Get Gemini decision (if successful) or default to APPROVE if failed
    gemini_decision = "APPROVE"
    gemini_reason = ""
    if gemini_result.get("success"):
        gemini_decision = gemini_result.get("decision", "APPROVE")
        gemini_reason = gemini_result.get("reason", "")

    # If either model says CONCERNS or REJECT, block
    if qwen_decision in ("CONCERNS", "REJECT"):
        return {
            "decision": qwen_decision,
            "reason": qwen_reason,
            "feedback": qwen_feedback,
            "model": "qwen"
        }

    if gemini_decision in ("CONCERNS", "REJECT"):
        return {
            "decision": gemini_decision,
            "reason": gemini_reason,
            "feedback": gemini_result.get("feedback", ""),
            "model": "gemini"
        }

    # Both approve, pass through
    return {"decision": "APPROVE", "reason": qwen_reason, "model": "qwen"}


def main():
    request_id = uuid.uuid4().hex[:8]
    logger.debug("Script started")
    # Read input JSON from stdin ONCE
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        logger.debug("JSON parse failed")
        return 0

    logger.debug(f"Input parsed, tool: {input_data.get('tool_name')}")

    # Stage 1: Guard Checks
    if os.environ.get("GEMINI_REVIEW_OFF") == "1":
        logger.debug("Review disabled by env")
        return 0

    tool_name = input_data.get("tool_name", "")
    if tool_name != "ExitPlanMode":
        return 0

    session_id = input_data.get("session_id", "")
    if not session_id:
        logger.debug("No session_id")
        return 0

    set_session(session_id)
    logger.info(f"Session ID: {session_id}")

    # Stage 2: Extract Plan Content
    # Get plan from tool_input
    tool_input = input_data.get("tool_input", {})
    plan_content = tool_input.get("plan", "")

    # Fallback: scan ~/.claude/plans/ for latest .md file
    if not plan_content:
        plans_dir = Path.home() / ".claude" / "plans"
        if plans_dir.exists():
            md_files = list(plans_dir.glob("*.md"))
            if md_files:
                latest = max(md_files, key=lambda p: p.stat().st_mtime)
                plan_content = latest.read_text()

    if not plan_content:
        logger.debug("No plan found")
        return 0

    logger.debug(f"Plan length: {len(plan_content)}")

    # Stage 4: Assemble Context - inject full CLAUDE.md content
    global_claude = ""
    claude_global_path = Path.home() / ".claude" / "CLAUDE.md"
    if claude_global_path.exists():
        global_claude = claude_global_path.read_text()

    project_claude = ""
    cwd = input_data.get("cwd", "")
    if cwd:
        project_claude_path = Path(cwd) / "CLAUDE.md"
        if project_claude_path.exists():
            project_claude = project_claude_path.read_text()

    # Get recent user messages from transcript_path
    recent_messages = ""
    transcript_path = input_data.get("transcript_path", "")
    if transcript_path and Path(transcript_path).exists():
        try:
            lines = Path(transcript_path).read_text().splitlines()
            user_msgs = []
            for line in lines[-30:]:
                try:
                    msg = json.loads(line)
                    if msg.get("type") == "user":
                        content = msg.get("message", {}).get("content", {})
                        text = content.get("text", "")
                        if text:
                            user_msgs.append(text)
                except json.JSONDecodeError:
                    continue
            recent_messages = "\n".join(user_msgs[-5:])
        except Exception:
            pass

    # Stage 5: Assemble Prompt
    prompt = f"""You are reviewing a Claude Code plan before it's executed. Your task is to evaluate the plan's quality and safety.

## Plan Content
{plan_content}

## Context

### Global CLAUDE.md
{global_claude}

### Project CLAUDE.md (full content)
{project_claude}

### Recent User Messages
{recent_messages}

## Review Criteria

Evaluate the plan against these 6 criteria:

1. **Completeness**: Are all necessary steps included? Are there clear acceptance criteria?
2. **Correctness**: Does the plan correctly solve the stated problem? Are the technical approaches sound?
3. **Safety**: Does the plan avoid destructive operations? Are there proper safeguards?
4. **Reversibility**: Can changes be easily reverted if issues arise?
5. **Security**: Does the plan avoid introducing security vulnerabilities?
6. **Best Practices**: Does the plan follow project conventions and coding standards?

## Output Format

Respond with ONLY a JSON object (no other text):
{{"decision": "APPROVE|CONCERNS|REJECT", "reason": "Brief explanation", "feedback": "Detailed feedback (only if CONCERNS or REJECT)"}}

- APPROVE: Plan is ready for execution
- CONCERNS: Plan needs minor improvements
- REJECT: Plan has critical issues"""

    logger.info(f"Prompt length: {len(prompt)} chars")
    logger.debug(f"Prompt ({len(prompt)} chars):\n{prompt}")

    # Stage 6: Parallel Review Calls (Gemini + Qwen)
    # Both use 60s timeout
    timeout_seconds = 60
    main_request_id = uuid.uuid4().hex[:8]
    log_with_request(main_request_id, logger.info, f"Calling reviewers (timeout: {timeout_seconds}s)...")

    gemini_result = None
    qwen_result = None

    with ThreadPoolExecutor(max_workers=2) as executor:
        gemini_future = executor.submit(call_reviewer, "gemini", "gemini-3-pro-preview", prompt, timeout_seconds, cwd)
        qwen_future = executor.submit(call_reviewer, "qwen", "coder-model", prompt, timeout_seconds, cwd)

        # Wait for both to complete
        try:
            gemini_result = gemini_future.result()
        except Exception as e:
            logger.error(f"Gemini future error: {e}")

        try:
            qwen_result = qwen_future.result()
        except Exception as e:
            logger.error(f"Qwen future error: {e}")

    # Stage 7: Merge Results
    # Handle None cases
    gemini_result = gemini_result or {"success": False, "error": "Not called"}
    qwen_result = qwen_result or {"success": False, "error": "Not called"}
    merged = merge_results(gemini_result, qwen_result, main_request_id)
    decision = merged.get("decision", "APPROVE")
    reason = merged.get("reason", "")
    feedback = merged.get("feedback", "")
    model = merged.get("model", "N/A")

    # Stage 8: Deny Handling
    log_with_request(main_request_id, logger.info, f"Decision: {decision} (model: {model}), Reason: {reason}")
    if decision == "APPROVE":
        # Log approval output for records
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": "Plan approved"
            }
        }
        log_with_request(main_request_id, logger.info, f"Output: {json.dumps(output, ensure_ascii=False)}")
        logger.info("Approved, allowing")
        return 0

    # Build error message
    error_msg = f"Plan review {decision}: {reason}"
    if feedback:
        error_msg += f"\n\nFeedback: {feedback}"

    # Output hook-specific JSON to stderr
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": error_msg
        }
    }
    # Log full JSON output for records
    log_with_request(main_request_id, logger.info, f"Output: {json.dumps(output, ensure_ascii=False)}")
    print(json.dumps(output), file=sys.stderr)

    return 2


if __name__ == "__main__":
    sys.exit(main())
