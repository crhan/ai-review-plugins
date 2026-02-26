---
name: audit-proposal
description: This skill should be used when the user asks to "audit proposal", "review plan", "双模型审计", "审查计划", or wants to review a plan using dual AI models (Qwen + Gemini).
version: 1.0.0
---

# audit-proposal

使用双模型（Qwen + Gemini）并行审计计划，生成对比报告。

## 使用场景

- 用户要求审查/审计计划
- 需要双模型视角对比分析
- 生成结构化审计报告

## 执行流程

1. 从 stdin 读取计划内容（JSON 格式）
2. 调用 `scripts/main.py` 执行双模型审计
3. 输出 Markdown 格式的对比报告

## 调用方式

### 读取计划内容

计划内容通过 stdin 传入，格式为 JSON：
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

### 执行审计

使用以下命令调用审计脚本：

```bash
# 方式1: 从文件读取
python3 scripts/main.py --plan-file /path/to/plan.json

# 方式2: 从 stdin 读取
python3 scripts/main.py --plan-file - <<< '{"plan": "YOUR_PLAN_CONTENT"}'
```

## 输出格式

审计完成后，输出 Markdown 格式报告：

```markdown
# 双模型审计报告

## Qwen 审查结果
[Qwen 的审查意见]

## Gemini 审查结果
[Gemini 的审查意见]

## 综合结论
[最终建议]
```

## 依赖脚本

- **`scripts/main.py`** - 主审计脚本，负责并行调用双模型并汇总结果
- **`scripts/config_manager.py`** - 配置管理，读取 API Keys
- **`config.json`** - 存储 API Keys 配置

## 配置要求

首次使用前，确保已配置 API Keys：
- Qwen API Key
- Gemini API Key

使用 `/setup_skill` 命令或 `setup-skill` skill 配置。
