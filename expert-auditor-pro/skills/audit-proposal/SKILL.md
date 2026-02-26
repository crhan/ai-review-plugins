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
1. stdin JSON（推荐）
2. 命令行参数
3. stdin 原始文本

### 推荐的 stdin JSON 格式

```json
{
  "tool_name": "ExitPlanMode",
  "session_id": "session-id",
  "cwd": "/path/to/project",
  "transcript_path": "/path/to/transcript.jsonl",
  "tool_input": {
    "plan": "计划内容..."
  }
}
```

## 输出格式

### stdout: Markdown 格式报告

```markdown
# 双模型审计报告

## Qwen 审查结果

[模型审查意见，包含 decision]

## Gemini 审查结果

[模型审查意见]

## 综合结论

✅ 最终决定: APPROVE - 原因
或
⚠️ 最终决定: CONCERNS - 原因
或
❌ 最终决定: REJECT - 原因

**反馈**: [详细反馈内容]
```

### stderr: JSON hook 格式（用于 skill 返回）

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow|deny",
    "permissionDecisionReason": "原因"
  }
}
```

## 决策规则（共识模式 B）

| 场景 | 结果 |
|------|------|
| 任一模型 REJECT | REJECT |
| 两个模型都 APPROVE | APPROVE |
| 一个 APPROVE + 一个 CONCERNS | 警告通过 |
| 两个模型都 CONCERNS | REJECT |
| 任一模型失败 | 视为 CONCERNS |

## 依赖脚本

- **`scripts/main.py`** - 主审计脚本
- **`scripts/config_manager.py`** - 配置管理
- **`config.json`** - 存储 API Keys 配置

## 配置要求

使用 `/setup_skill` 命令配置：
- Qwen API Key
- Gemini API Key
- 代理设置（可选）
