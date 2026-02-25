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
from pathlib import Path
from datetime import datetime, timedelta

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
    "[%(asctime)s] [%(session)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))

# Debug log handler - records DEBUG and above
debug_handler = logging.FileHandler(DEBUG_LOG)
debug_handler.setLevel(logging.DEBUG)
debug_handler.setFormatter(logging.Formatter(
    "[%(asctime)s] [%(session)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))

# Console handler
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setFormatter(logging.Formatter(
    "[%(asctime)s] [%(session)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))

# Add handlers to root logger
logging.getLogger().addHandler(info_handler)
logging.getLogger().addHandler(debug_handler)
logging.getLogger().addHandler(console_handler)

logger = logging.getLogger("plan-gemini-review")

_current_session = ""


class SessionFilter(logging.Filter):
    def filter(self, record):
        record.session = _current_session[:8] if _current_session else "unknown"
        return True


logger.addFilter(SessionFilter())


def set_session(session_id):
    global _current_session
    _current_session = session_id


def main():
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

    logger.info(f"Session ID: {session_id}")
    set_session(session_id)

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

    logger.debug(f"Prompt to Gemini:\n{prompt}")

    # Stage 6: Gemini Call
    start_time = time.time()
    logger.info("Calling Gemini...")

    env = os.environ.copy()
    env["http_proxy"] = "http://127.0.0.1:7890"
    env["https_proxy"] = "http://127.0.0.1:7890"

    try:
        result = subprocess.run(
            ["gemini", "-m", "gemini-3-pro-preview", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=180,
            env=env
        )
        gemini_result = result.stdout.strip()
        elapsed = time.time() - start_time
        logger.info(f"Gemini call completed in {elapsed:.2f}s")
        logger.debug(f"Gemini raw result: {gemini_result}")
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        logger.error(f"Gemini call timed out after {elapsed:.2f}s")
        return 0
    except (FileNotFoundError, Exception) as e:
        elapsed = time.time() - start_time
        logger.debug(f"Gemini error: {e} (took {elapsed:.2f}s)")
        return 0

    if not gemini_result:
        logger.debug("Empty Gemini result")
        return 0

    # Parse Gemini response
    try:
        parsed = json.loads(gemini_result)
        decision = parsed.get("decision", "APPROVE")
        reason = parsed.get("reason", "")
        feedback = parsed.get("feedback", "")
    except json.JSONDecodeError:
        return 0

    if not decision:
        return 0

    # Stage 7: Deny Handling
    logger.info(f"Decision: {decision}, Reason: {reason}")
    if decision == "APPROVE":
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
    print(json.dumps(output), file=sys.stderr)

    return 2


if __name__ == "__main__":
    sys.exit(main())
