# review-notes 传递给模型 - 设计

## 背景

当前 `audit-proposal` skill 的设计意图是：将历史审查对话（review-notes.md）与计划一起传递给外部模型，让模型能看到之前的讨论。

**实际问题**：main.py 中没有实现这个功能，导致每次调用都是独立的，无法利用历史上下文。

## 目标

实现自动发现并传递 review-notes.md 给外部模型。

## 方案

### 1. 文件发现逻辑

基于 plan 文件路径自动查找对应的 review-notes：

```
plan: docs/plans/2026-02-27-config-log-location-design.md
      ↓
review-notes: docs/plans/2026-02-27-config-log-location-design-review-notes.md
```

发现规则：
- 移除 `.md` 后缀，追加 `-review-notes.md`
- 在 plan 文件所在目录查找
- 文件不存在时 silent skip（首轮审计时没有 review-notes 是正常的）

### 2. 代码改动

| 文件 | 改动 |
|------|------|
| `main.py` | 添加 `load_review_notes()` 函数 |
| `main.py` | 修改 `call_qwen()` 和 `call_gemini()` 的 system_prompt |

### 3. 实现细节

#### load_review_notes() 函数

```python
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
```

#### 传递 context 给模型

在 `call_qwen()` 和 `call_gemini()` 的 system_prompt 中添加：

```
## 前期审查反馈

{review_notes_content if review_notes_content else "(本轮为首轮审查，无历史反馈)"}
```

### 4. SKILL.md 文档更新

更新 `输入格式` 部分，说明当前支持自动发现 review-notes。

## 风险

1. **路径遍历风险** - 已通过 resolve() + 目录锁定解决
2. **编码问题** - 使用 errors="replace" 防止崩溃

## 实施步骤

1. 在 `main.py` 中添加 `load_review_notes()` 函数
2. 修改 `audit_plan()` 接收 plan_path 并加载 review_notes
3. 将 review_notes 传递给 `call_qwen()` 和 `call_gemini()`
4. 在 system_prompt 中插入前期反馈
5. 更新 SKILL.md 文档
