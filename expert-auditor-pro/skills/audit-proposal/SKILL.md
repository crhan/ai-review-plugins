---
name: audit-proposal
description: This skill should be used when the user asks to "audit proposal", "review plan", "双模型审计", "审查计划", or wants to have an external model review a plan.
---

# audit-proposal

邀请外部模型（Qwen + Gemini）对设计方案进行评审，并根据反馈改进计划。

## 核心流程

1. **调用外部模型**：通过 main.py 脚本并行调用 Qwen 和 Gemini 进行评审
2. **获取反馈**：接收模型的审查意见（APPROVE / CONCERNS / REJECT）
3. **处理反馈**：
   - APPROVE → 直接放行，执行计划
   - CONCERNS/REJECT → 根据反馈修正计划，或在计划中辩护你的立场
   - 无法达成共识 → 交由用户做最终裁决

## 你的角色

你是**对等的 peer reviewer**。外部模型的意见是参考，不是圣旨。你需要：
- 尊重模型的专业建议
- 但也有权质疑模型的判断
- 最终目标是产出更好的设计方案，而不是盲目服从模型

## 输入格式

### 最高优先级：自动发现 plan 文件

调用时自动在以下位置查找最近修改的 plan 文件：
- `$CWD/docs/plans/`
- `$HOME/.claude/plan/`

找到后用 `--plan-file` 参数传入：

```bash
PLAN_FILE=$(find "$PWD/docs/plans" "$HOME/.claude/plan" -name "*.md" -type f -exec ls -t {} + 2>/dev/null | head -1)
uv run ${CLAUDE_PLUGIN_ROOT}/expert-auditor-pro/scripts/main.py --plan-file "$PLAN_FILE"
```

### 方式2：stdin JSON

```bash
echo '{"plan": "计划内容", "cwd": "/project"}' | uv run ${CLAUDE_PLUGIN_ROOT}/expert-auditor-pro/scripts/main.py
```

### 方式3：命令行参数

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/expert-auditor-pro/scripts/main.py "计划内容"
```

## 输出格式

外部模型会返回 Markdown 格式的审查报告：

```markdown
# 双模型审计报告

## Qwen 审查结果
[审查意见，包含 decision: APPROVE/CONCERNS/REJECT]

## Gemini 审查结果
[审查意见]

## 综合结论
✅/⚠️/❌ 最终决定 + 原因 + 反馈
```

## 决策规则

| 场景 | 结果 |
|------|------|
| 任一模型 REJECT | 需处理反馈后才能继续 |
| 两个模型都 APPROVE | 可以继续执行 |
| 一个 APPROVE + 一个 CONCERNS | 警告通过 |
| 两个模型都 CONCERNS | 需处理反馈后才能继续 |

## 配置

```bash
# 配置 API Keys
cd ${CLAUDE_PLUGIN_ROOT}/expert-auditor-pro
uv run python scripts/config_manager.py --set-qwen-key "YOUR_KEY"
uv run python scripts/config_manager.py --set-gemini-key "YOUR_KEY"
```
