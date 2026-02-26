# Expert Auditor Pro 升级设计

## 目标

升级 `expert-auditor-pro` 插件的 skill 逻辑，参照 `gemini-plan-review/scripts/plan-gemini-review.py` 的业务逻辑，实现更强大的双模型审计能力。

## 约束

- 保持 skill 调用形式（不改造为 hook）
- 使用 httpx 直连 API（不改为 CLI 调用）
- 仅修改 `expert-auditor-pro` 插件目录内的文件

## 架构

```
expert-auditor-pro/
├── .claude-plugin/
│   └── plugin.json           # 插件声明
├── skills/
│   └── audit-proposal/
│       └── SKILL.md          # 审计 skill（更新）
└── scripts/
    ├── main.py               # 主逻辑（重构）
    └── config_manager.py     # 配置管理（保留）
```

**数据流**：
```
Skill 调用 → stdin JSON → scripts/main.py → Qwen/Gemini API → merge → stdout/stderr
```

## 详细设计

### 输入格式

保持兼容 Claude Code hook JSON 格式：

```json
{
  "tool_name": "ExitPlanMode",
  "session_id": "xxx",
  "cwd": "/path/to/project",
  "transcript_path": "/path/to/transcript.jsonl",
  "tool_input": {
    "plan": "计划内容..."
  }
}
```

### 上下文注入

**全局 CLAUDE.md**
- 路径：`~/.claude/CLAUDE.md`
- 读取全部内容

**项目 CLAUDE.md**
- 路径：`{cwd}/CLAUDE.md`
- 仅当 cwd 存在时读取

**近期用户消息**
- 来源：`transcript_path`（JSONL 格式）
- 提取最近 5 条 user 消息
- 格式：纯文本拼接

### 审计 Prompt

```
## Plan Content
{plan}

## Context

### Global CLAUDE.md
{global_claude}

### Project CLAUDE.md
{project_claude}

### Recent User Messages
{recent_messages}

## Review Criteria

1. Completeness: 步骤完整？有验收标准？
2. Correctness: 技术方案正确？
3. Safety: 破坏性操作有保护？
4. Reversibility: 可回滚？
5. Security: 安全漏洞？
6. Best Practices: 符合项目约定？

## Output Format

{"decision": "APPROVE|CONCERNS|REJECT", "reason": "简要说明", "feedback": "详细反馈（仅CONCERNS/REJECT）"}
```

### Merge 策略（共识模式 B）

```
决策矩阵：

Qwen \ Gemini | APPROVE      | CONCERNS      | REJECT
-------------|---------------|---------------|--------------
APPROVE      | APPROVE       | 用户确认*     | REJECT
CONCERNS     | 用户确认*     | REJECT        | REJECT
REJECT       | REJECT        | REJECT        | REJECT

* 用户确认：当只有一个模型返回 CONCERNS 时，
  输出警告但标记为 APPROVE，同时在 feedback 中说明需要关注
```

**实现逻辑**：
1. 任一模型 REJECT → 直接 REJECT
2. 两个模型都 APPROVE → APPROVE
3. 一个 APPROVE + 一个 CONCERNS → 警告通过（APPROVE + feedback 提醒）
4. 两个模型都 CONCERNS → REJECT
5. 任一模型失败（网络错误等）→ 视为 CONCERNS（安全优先）

### 日志系统

使用 Loguru（已有），增强为：
- 脱敏处理（API Key 过滤）
- 分级输出：DEBUG → stderr，INFO+ → 文件
- 追加 request_id 追踪
- JSONL 格式记录审计历史

### 输出格式

**stdout**: Markdown 报告

**stderr**: JSON hook 格式（用于 skill 返回）

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow|deny",
    "permissionDecisionReason": "原因"
  }
}
```

## 差异表

| 特性 | 当前实现 | 升级后 |
|------|----------|--------|
| 上下文 | 无 | CLAUDE.md x2 + 用户消息 |
| merge 逻辑 | 简单 markdown 拼接 | 共识模式决策 |
| 日志 | 基础 | 脱敏 + request_id |
| 输入 | 多格式 | 统一 JSON |

## 文件变更（仅 expert-auditor-pro 目录）

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/main.py` | 重构 | 增加上下文注入 + merge 逻辑 |
| `skills/audit-proposal/SKILL.md` | 更新 | 同步新功能说明 |
| `config.json` | 保留 | 配置格式不变 |

## 待定

- 是否保留多格式输入兼容（当前支持 argparse + stdin + JSON）？
- 日志是否拆分为独立模块？
