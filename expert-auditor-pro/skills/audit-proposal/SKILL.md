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
- **Peer Reviewer 角色**：你和外部模型（Qwen/Gemini）是对等的 peer reviewer
  - 当外部模型 APPROVE 时 → 直接放行
  - 当外部模型提出质疑时 → 你可以修正 plan 或在 plan 中辩护立场
  - 多轮磋商无法达成一致时 → 短路放行，交由用户做最终裁决

## 输入格式

### 最高优先级：自动发现 plan 文件

调用时自动在对话上下文或者以下位置查找最近修改的 plan 文件：

- `$CWD/docs/plans/`
- `$HOME/.claude/plan/`

找到后用 `--plan-file` 参数传入：

```bash
# 自动发现并审计
PLAN_FILE=$(find "$PWD/docs/plans" "$HOME/.claude/plan" -name "*.md" -type f -exec ls -t {} + 2>/dev/null | head -1)
uv run ${CLAUDE_PLUGIN_ROOT}/expert-auditor-pro/scripts/main.py --plan-file "$PLAN_FILE"
```

### 方式2：stdin JSON（Claude Code 调用时使用）

从 stdin 读取 JSON，字段说明：

| 字段              | 必填 | 说明                                    |
| ----------------- | ---- | --------------------------------------- |
| `plan`            | ✅   | 计划内容                                |
| `session_id`      | -    | 会话 ID（用于日志）                     |
| `cwd`             | -    | 当前工作目录（用于加载项目 CLAUDE.md）  |
| `transcript_path` | -    | transcript 文件路径（用于加载用户消息） |

**示例：**

```bash
echo '{"plan": "创建用户认证功能", "session_id": "abc123", "cwd": "/project"}' | uv run ${CLAUDE_PLUGIN_ROOT}/expert-auditor-pro/scripts/main.py
```

### 方式3：命令行参数

直接传入计划内容作为参数：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/expert-auditor-pro/scripts/main.py "创建用户认证功能"
```

### 方式4：stdin 原始文本

管道传入纯文本计划：

```bash
echo "创建用户认证功能" | uv run ${CLAUDE_PLUGIN_ROOT}/expert-auditor-pro/scripts/main.py
```

## 输出格式

直接输出 Markdown 格式报告：

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

## 决策规则（共识模式 B）

| 场景                         | 结果          |
| ---------------------------- | ------------- |
| 任一模型 REJECT              | REJECT        |
| 两个模型都 APPROVE           | APPROVE       |
| 一个 APPROVE + 一个 CONCERNS | 警告通过      |
| 两个模型都 CONCERNS          | REJECT        |
| 任一模型失败                 | 视为 CONCERNS |

## 依赖脚本

- **`${CLAUDE_PLUGIN_ROOT}/expert-auditor-pro/scripts/main.py`** - 主审计脚本
- **`${CLAUDE_PLUGIN_ROOT}/expert-auditor-pro/scripts/config_manager.py`** - 配置管理
- **`${CLAUDE_PLUGIN_ROOT}/expert-auditor-pro/config.json`** - 存储 API Keys 配置

## 调用示例

```bash
# 自动发现 plan 文件并审计（推荐）
PLAN_FILE=$(find "$PWD/docs/plans" "$HOME/.claude/plan" -name "*.md" -type f -exec ls -t {} + 2>/dev/null | head -1)
uv run ${CLAUDE_PLUGIN_ROOT}/expert-auditor-pro/scripts/main.py --plan-file "$PLAN_FILE"
```

脚本会自动从 `${CLAUDE_PLUGIN_ROOT}/expert-auditor-pro/config.json` 读取配置。

## 配置要求

使用 `/setup_skill` 命令配置：

- Qwen API Key
- Gemini API Key
- 代理设置（可选）
