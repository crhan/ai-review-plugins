# CLAUDE.md

此文件为 Claude Code (claude.ai/code) 在本项目中工作时提供指导。

## 项目概述

这是一个 **Claude Code 插件**，包含两个插件：
- `expert-auditor-pro`：双模型审计插件（Qwen + Gemini 并行审计）
- `gemini-plan-review`：单模型审查插件（Gemini）

## 架构

```
.claude-plugin/
├── plugin.json           → 插件声明
├── marketplace.json       → Marketplace 入口
expert-auditor-pro/       → 双模型审计插件
├── .claude-plugin/
│   └── plugin.json       → 插件清单
├── scripts/
│   ├── main.py           → 主审计脚本
│   └── config_manager.py → 配置管理
├── skills/
│   ├── audit-proposal/   → 审计 skill
│   └── setup-skill/      → 配置 skill
└── config.json           → API Keys 配置

gemini-plan-review/        → Gemini 审查插件
├── .claude-plugin/
│   └── plugin.json
├── hooks/
│   └── hooks.json
└── scripts/
    └── plan-gemini-review.py
```

## Marketplace Schema

本项目的 `.claude-plugin/marketplace.json` 定义了插件市场的 schema。

### 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | Marketplace 标识符（kebab-case），用户安装时可见，如 `expert-auditor-pro@ai-review-plugins` |
| `owner` | object | 维护者信息 |
| `plugins` | array | 可用插件列表 |

### Owner 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 维护者名称 |
| `email` | string | - | 联系方式 |

### Plugin Entry 字段

每个插件在 `plugins` 数组中定义：

**必填字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 插件标识符 |
| `source` | string\|object | 插件来源（见下文） |

**可选字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `description` | string | 插件描述 |
| `version` | string | 版本号 |
| `author` | object | 作者信息 |
| `category` | string | 分类 |
| `strict` | boolean | 是否严格模式（默认 true） |

### Plugin Sources

| 来源 | 类型 | 说明 |
|------|------|------|
| 相对路径 | string | 如 `"./expert-auditor-pro"` |
| GitHub | object | `{ "source": "github", "repo": "owner/repo", "ref": "v1.0", "sha": "..." }` |
| npm | object | `{ "source": "npm", "package": "@org/plugin", "version": "1.0.0" }` |
| pip | object | `{ "source": "pip", "package": "plugin-name" }` |

### 示例

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "ai-review-plugins",
  "owner": {
    "name": "ruohanc"
  },
  "plugins": [
    {
      "name": "expert-auditor-pro",
      "version": "1.2.0",
      "description": "双模型审计插件",
      "source": "./expert-auditor-pro",
      "category": "security"
    }
  ]
}
```

## 运行脚本

### expert-auditor-pro

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/expert-auditor-pro/scripts/main.py
```

脚本从 stdin 读取 JSON 输入：
```json
{
  "plan": "计划内容",
  "session_id": "session-id",
  "cwd": "/path/to/project"
}
```

### gemini-plan-review

```bash
python3 /Users/ruohan.chen/Documents/GitHub/ai-review-plugins/gemini-plan-review/scripts/plan-gemini-review.py
```

## 配置

### 配置文件位置

- API Keys: `~/.claude/plugin/expert-auditor-pro/config.json`
- 日志: `~/.claude/plugin/expert-auditor-pro/logs/`

### 日志查看

```bash
# INFO 级别
tail -f ~/.claude/plugin/expert-auditor-pro/logs/info.jsonl | jq -r '.text // .message'

# DEBUG 级别
tail -f ~/.claude/plugin/expert-auditor-pro/logs/debug.jsonl | jq -r '.text // .message'
```

### 配置 API Keys

```bash
cd expert-auditor-pro
uv run python scripts/config_manager.py --set-qwen-key "YOUR_KEY"
uv run python scripts/config_manager.py --set-gemini-key "YOUR_KEY"
```

## 审查标准

插件根据以下 6 个标准评估计划：
1. 完整性 - 是否包含所有必要步骤？
2. 正确性 - 计划是否正确解决问题？
3. 安全性 - 是否有防止破坏性操作的保护措施？
4. 可逆性 - 更改是否可以回滚？
5. 安全性 - 是否引入安全漏洞？
6. 最佳实践 - 是否遵循项目约定？
