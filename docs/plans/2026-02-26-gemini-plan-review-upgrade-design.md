# gemini-plan-review 升级设计

## 目标

将 gemini-plan-review 从调用 CLI 改为直接 import expert-auditor-pro 的模块，统一配置和日志管理到 `~/.claude/plugins/` 目录下。

## 架构

```
~/.claude/plugins/gemini-plan-review/
├── config.json           # 权限 600
├── logs/
│   └── audit.jsonl
├── scripts/
│   └── plan-review.py   # 直接 import expert-auditor-pro 的模块
└── hooks/
    └── hooks.json
```

## 实现方案

将 expert-auditor-pro 的以下模块复制/软链到 gemini-plan-review：
- `scripts/main.py` → 改为 `plan-review.py`
- `scripts/config_manager.py` → 保留
- 移除 CLI 调用（subprocess），改为直接 import

## 迁移方案（可逆）

### 步骤 1：备份旧数据
```bash
cp -r ~/.cache/gemini_plan_review ~/.cache/gemini_plan_review.bak
```

### 步骤 2：双写日志（过渡期）
新脚本同时写入：
- 新路径：`~/.claude/plugins/gemini-plan-review/logs/audit.jsonl`
- 旧路径：`~/.cache/gemini_plan_review/info.log`（保持兼容）

### 步骤 3：更新 hook 配置
修改 `hooks/hooks.json` 中的脚本路径

### 步骤 4：验证后删除旧日志

## 改动清单

| # | 改动 | 说明 |
|---|------|------|
| 1 | 复制 expert-auditor-pro 模块到 gemini-plan-review | API 调用、配置加载等 |
| 2 | 修改 plan-review.py | 移除 subprocess，改为 import |
| 3 | 创建 `~/.claude/plugins/gemini-plan-review/config.json` | 权限 600 |
| 4 | 创建日志目录 | `~/.claude/plugins/gemini-plan-review/logs/` |
| 5 | 实现双写日志 | 新旧路径同时写入 |
| 6 | 更新 hook 配置 | 指向新脚本路径 |
| 7 | 迁移备份 | 保留旧数据备份 |

## 配置字段

`config.json`（权限必须为 600）:

```json
{
  "disabled": false,
  "qwen_api_key": "",
  "gemini_api_key": "",
  "qwen_model": "qwen3.5-plus",
  "gemini_model": "gemini-3.1-pro-preview",
  "proxy": "http://127.0.0.1:7890"
}
```

> ⚠️ 创建后必须执行：`chmod 600 ~/.claude/plugins/gemini-plan-review/config.json`

## 日志格式

JSONL 格式：

```json
{"level": "INFO", "message": "Plan review started", "timestamp": "...", "request_id": "..."}
```

## 结果合并逻辑

保持双模型并行审查：
- 任一模型 REJECT → REJECT
- 两个模型都 CONCERNS → REJECT
- 一个 APPROVE + 一个 CONCERNS → 警告通过
- 两个模型都 APPROVE → APPROVE
