# Expert Auditor Pro 升级实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 升级 expert-auditor-pro 插件，增加上下文注入和 merge 决策逻辑

**Architecture:** 在现有 main.py 基础上重构，增加 3 个模块：上下文组装器、merge 决策器、日志增强器

**Tech Stack:** Python 3, httpx, loguru

---

### Task 1: 重构 main.py 输入解析模块

**Files:**
- Modify: `expert-auditor-pro/scripts/main.py:358-392`

**Step 1: 写一个测试用例验证当前输入解析**

```bash
# 测试 stdin JSON 解析
echo '{"plan": "test plan", "tool_name": "ExitPlanMode", "session_id": "123", "cwd": "/tmp"}' | python3 expert-auditor-pro/scripts/main.py
```

**Step 2: 重构输入解析逻辑，保持向后兼容**

保留现有的 3 种输入方式，但统一输出为包含以下字段的 dict：
```python
{
    "plan": "计划内容",
    "session_id": "xxx",
    "cwd": "/path",
    "transcript_path": "/path/to/transcript.jsonl"
}
```

**Step 3: 验证解析正确**

```bash
# 测试方式1: stdin JSON
echo '{"plan": "test", "session_id": "s1", "cwd": "/tmp"}' | python3 expert-auditor-pro/scripts/main.py

# 测试方式2: 命令行参数
python3 expert-auditor-pro/scripts/main.py "test plan"

# 测试方式3: stdin 原始文本
echo "raw plan text" | python3 expert-auditor-pro/scripts/main.py
```

---

### Task 2: 实现上下文注入模块

**Files:**
- Modify: `expert-auditor-pro/scripts/main.py:新增函数`

**Step 1: 添加上下文读取函数**

```python
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
```

**Step 2: 修改 audit_plan 函数签名**

```python
async def audit_plan(plan_content: str, context: dict) -> dict:
    # context 包含 session_id, cwd, transcript_path
```

**Step 3: 测试上下文加载**

```python
# 手动测试
from pathlib import Path
print(load_global_claude())
print(load_project_claude("/tmp"))
print(load_recent_messages("/tmp/transcript.jsonl"))
```

---

### Task 3: 实现 Merge 决策模块

**Files:**
- Modify: `expert-auditor-pro/scripts/main.py:新增函数`

**Step 1: 添加 merge_results 函数**

```python
def merge_results(qwen_result: dict, gemini_result: dict) -> dict:
    """
    共识模式 B 决策：
    - 任一 REJECT → REJECT
    - 两个 APPROVE → APPROVE
    - 一个 APPROVE + 一个 CONCERNS → 警告通过
    - 两个 CONCERNS → REJECT
    - 任一失败 → 视为 CONCERNS
    """
    # 提取决策
    qwen_decision = qwen_result.get("decision", "CONCERNS") if qwen_result.get("success") else "CONCERNS"
    gemini_decision = gemini_result.get("decision", "CONCERNS") if gemini_result.get("success") else "CONCERNS"

    # 任一 REJECT
    if qwen_decision == "REJECT" or gemini_decision == "REJECT":
        return {
            "decision": "REJECT",
            "reason": qwen_result.get("reason") or gemini_result.get("reason", "Model rejected"),
            "feedback": qwen_result.get("feedback") or gemini_result.get("feedback", ""),
            "model": "qwen" if qwen_decision == "REJECT" else "gemini"
        }

    # 两个 CONCERNS
    if qwen_decision == "CONCERNS" and gemini_decision == "CONCERNS":
        return {
            "decision": "REJECT",
            "reason": "Both models have concerns",
            "feedback": f"Qwen: {qwen_result.get('reason', '')}\nGemini: {gemini_result.get('reason', '')}",
            "model": "both"
        }

    # 一个 APPROVE + 一个 CONCERNS
    if (qwen_decision == "APPROVE" and gemini_decision == "CONCERNS") or \
       (qwen_decision == "CONCERNS" and gemini_decision == "APPROVE"):
        return {
            "decision": "APPROVE",
            "reason": "Approved with warnings",
            "feedback": f"Warning: {qwen_result.get('reason') or gemini_result.get('reason', 'One model has concerns')}",
            "model": "qwen" if gemini_decision == "CONCERNS" else "gemini"
        }

    # 两个 APPROVE
    return {
        "decision": "APPROVE",
        "reason": qwen_result.get("reason", "Both approved"),
        "model": "qwen"
    }
```

**Step 2: 更新 API 响应解析**

修改 call_qwen 和 call_gemini 函数，从响应中提取 decision/reason/feedback：

```python
# 在 return 中添加 decision 字段
return {
    "success": True,
    "model": model,
    "content": result["choices"][0]["message"]["content"],
    "decision": "APPROVE",  # 默认值，后续从 content 解析
    "reason": "",
    "usage": result.get("usage", {})
}
```

**Step 3: 从模型响应中解析 decision**

```python
def parse_decision_from_content(content: str) -> dict:
    """从模型返回的文本中解析 decision/reason/feedback"""
    import re
    # 尝试从 JSON 块中提取
    json_match = re.search(r'\{.*?"decision".*?\}', content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return {
                "decision": data.get("decision", "CONCERNS"),
                "reason": data.get("reason", ""),
                "feedback": data.get("feedback", "")
            }
        except json.JSONDecodeError:
            pass

    # 尝试从文本开头提取
    content_upper = content.strip().upper()
    if content_upper.startswith("APPROVE"):
        return {"decision": "APPROVE", "reason": "Model approved", "feedback": ""}
    elif content_upper.startswith("CONCERNS"):
        return {"decision": "CONCERNS", "reason": "Model has concerns", "feedback": content}
    elif content_upper.startswith("REJECT"):
        return {"decision": "REJECT", "reason": "Model rejected", "feedback": content}

    # 默认
    return {"decision": "CONCERNS", "reason": "Unable to parse decision", "feedback": content}
```

---

### Task 4: 增强日志系统

**Files:**
- Modify: `expert-auditor-pro/scripts/main.py:38-58`

**Step 1: 添加 request_id 生成**

```python
import uuid

def generate_request_id() -> str:
    return uuid.uuid4().hex[:8]
```

**Step 2: 增强日志配置**

```python
# 添加 request_id 到日志上下文
request_id = generate_request_id()

logger.configure(
    patcher=lambda record: record.update(
        message=sanitize_message(str(record["message"])),
        extra={"request_id": request_id}
    )
)
```

**Step 3: 测试日志输出**

```bash
echo '{"plan": "test"}' | python3 expert-auditor-pro/scripts/main.py 2>&1 | head -20
```

---

### Task 5: 更新 audit-proposal Skill 文档

**Files:**
- Modify: `expert-auditor-pro/skills/audit-proposal/SKILL.md`

**Step 1: 更新 SKILL.md**

```markdown
---
name: audit-proposal
description: This skill should be used when the user asks to "audit proposal", "review plan", "双模型审计", "审查计划", or wants to review a plan using dual AI models (Qwen + Gemini).
---

# audit-proposal

使用双模型（Qwen + Gemini）并行审计计划，生成对比报告。

## 功能

- 上下文注入：全局 CLAUDE.md + 项目 CLAUDE.md + 用户消息
- 双模型并行审计
- 共识模式决策（任一 REJECT 拦截，两个 CONCERNS 拦截）
- 脱敏日志记录

## 输入格式

支持 3 种输入方式：
1. stdin JSON
2. 命令行参数
3. stdin 原始文本

## 输出

- stdout: Markdown 格式报告
- stderr: JSON hook 格式
```

---

### Task 6: 端到端测试

**Files:**
- Test: `expert-auditor-pro/scripts/main.py`

**Step 1: 准备测试环境**

确保 config.json 中配置了有效的 API key（测试时可跳过）

**Step 2: 运行测试**

```bash
# 测试完整流程（需要 API key）
echo '{"plan": "修复 bug", "session_id": "test", "cwd": "/tmp"}' | python3 expert-auditor-pro/scripts/main.py

# 验证输出包含
# - Qwen 审查结果
# - Gemini 审查结果
# - 综合结论（包含 decision）
```

---

### Task 7: 提交变更

**Files:**
- Commit: `expert-auditor-pro/scripts/main.py`, `expert-auditor-pro/skills/audit-proposal/SKILL.md`

```bash
git add expert-auditor-pro/scripts/main.py expert-auditor-pro/skills/audit-proposal/SKILL.md
git commit -m "feat(audit-proposal): add context injection and merge decision logic"
```
