# review-notes 传递给模型 - 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 main.py 中实现自动发现并传递 review-notes.md 给外部模型

**Architecture:** 基于 plan 文件路径自动查找对应的 review-notes，通过 system_prompt 传递给模型

**Tech Stack:** Python, httpx, loguru

---

## Task 1: 添加 load_review_notes() 函数

**Files:**
- Modify: `expert-auditor-pro/scripts/main.py:449-473` (在 load_recent_messages 函数后添加)

**Step 1: 添加 load_review_notes 函数**

```python
def load_review_notes(plan_path: str) -> str:
    """根据 plan 文件路径加载对应的 review-notes

    查找规则：plan.md -> plan-review-notes.md
    """
    if not plan_path:
        return ""

    plan_file = Path(plan_path)
    if not plan_file.exists():
        return ""

    # 构建 review-notes 路径
    review_notes_path = plan_file.with_name(plan_file.stem + "-review-notes.md")

    if review_notes_path.exists():
        content = review_notes_path.read_text(encoding="utf-8")
        # 防止文件过大，截断到 2000 字符
        return content[:2000]

    return ""
```

**Step 2: Commit**

```bash
git add expert-auditor-pro/scripts/main.py
git commit -m "feat(audit): add load_review_notes function"
```

---

## Task 2: 修改 audit_plan() 接收 plan_path

**Files:**
- Modify: `expert-auditor-pro/scripts/main.py:475-574` (audit_plan 函数)

**Step 1: 修改 audit_plan 函数签名和实现**

在函数开头获取 plan_path（需要先传递 plan_path 到 audit_plan），然后加载 review_notes：

```python
# 在 audit_plan 函数中，context 获取后添加：
plan_path = context.get("plan_path", "")
review_notes = load_review_notes(plan_path)

# DEBUG
logger.debug(f"Review notes loaded: {len(review_notes)} chars")
```

**Step 2: 修改 context 字典构建位置**

在构建传递给模型的 context 字典时添加 review_notes：

```python
context = {
    "global_claude": global_claude,
    "project_claude": project_claude,
    "recent_messages": recent_messages,
    "review_notes": review_notes  # 新增
}
```

**Step 3: Commit**

```bash
git add expert-auditor-pro/scripts/main.py
git commit -m "feat(audit): pass review_notes to context"
```

---

## Task 3: 修改 call_qwen() 接收 review_notes

**Files:**
- Modify: `expert-auditor-pro/scripts/main.py:219-319` (call_qwen 函数)

**Step 1: 修改函数签名**

```python
async def call_qwen(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    plan_content: str,
    proxy: str,
    context: dict
) -> dict:
```

**Step 2: 在函数内提取 review_notes**

在提取 global_claude 之后添加：

```python
review_notes = context.get("review_notes", "")[:1500] if context.get("review_notes") else ""
```

**Step 3: 修改 system_prompt**

在 system_prompt 末尾添加：

```python
## 前期审查反馈

{review_notes if review_notes else "(本轮为首轮审查，无历史反馈)"}
```

完整 system_prompt 变成：

```python
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
```

**Step 4: Commit**

```bash
git add expert-auditor-pro/scripts/main.py
git commit -m "feat(audit): pass review_notes to Qwen prompt"
```

---

## Task 4: 修改 call_gemini() 接收 review_notes

**Files:**
- Modify: `expert-auditor-pro/scripts/main.py:322-429` (call_gemini 函数)

**Step 1: 同样的修改**

重复 Task 3 的步骤 2-3，修改 call_gemini 函数。

**Step 2: Commit**

```bash
git add expert-auditor-pro/scripts/main.py
git commit -m "feat(audit): pass review_notes to Gemini prompt"
```

---

## Task 5: 修改 main() 传递 plan_path

**Files:**
- Modify: `expert-auditor-pro/scripts/main.py:665-740` (main 函数)

**Step 1: 在读取 plan_file 后设置 plan_path**

```python
if args.plan_file:
    plan_path = str(plan_path)  # 添加这行
    context["plan_path"] = plan_path  # 添加这行
```

**Step 2: Commit**

```bash
git add expert-auditor-pro/scripts/main.py
git commit -m "feat(audit): pass plan_path to audit_plan"
```

---

## Task 6: 添加 --review-notes 命令行参数

**Files:**
- Modify: `expert-auditor-pro/scripts/main.py:680-686` (argparse 部分)

**Step 1: 添加命令行参数**

```python
parser.add_argument("--plan-file", type=str, help="Plan 文件路径")
parser.add_argument("--review-notes", type=str, help="Review notes 文件路径（可选）")
parser.add_argument("plan", nargs="*", default="")
```

**Step 2: 在 main() 中处理参数**

```python
if args.review_notes:
    review_notes_path = Path(args.review_notes)
    if review_notes_path.exists():
        context["review_notes"] = review_notes_path.read_text(encoding="utf-8")[:2000]
        logger.info(f"Using review notes: {review_notes_path}")
```

**Step 3: Commit**

```bash
git add expert-auditor-pro/scripts/main.py
git commit -m "feat(audit): add --review-notes CLI argument"
```

---

## Task 7: 更新 SKILL.md 文档

**Files:**
- Modify: `expert-auditor-pro/skills/audit-proposal/SKILL.md`

**Step 1: 更新输入格式部分**

在 "自动发现 plan 文件" 部分添加说明：

```markdown
> 注意：自动发现 review-notes.md，与 plan 文件同目录，命名为 `{plan-name}-review-notes.md`
```

**Step 2: Commit**

```bash
git add expert-auditor-pro/skills/audit-proposal/SKILL.md
git commit -m "docs(audit-proposal): document review-notes auto-discovery"
```

---

## Task 8: 测试验证

**Step 1: 运行现有审计测试**

```bash
cd expert-auditor-pro
echo '{"plan": "test plan", "cwd": "/tmp"}' | uv run python scripts/main.py
```

**Step 2: 验证 review-notes 被加载**

查看 debug 日志：
```bash
tail -f ~/.cache/expert-auditor-pro/logs/debug.jsonl | jq -r '.message'
```

预期看到：`Review notes loaded: XXX chars`

**Step 3: Commit**

```bash
git add -A
git commit -m "test: verify review-notes passing works"
```
