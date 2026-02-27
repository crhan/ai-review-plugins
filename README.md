# Expert Auditor Pro

Claude Code 插件 - 使用 Qwen + Gemini 双模型并行审计计划

## 简介

Expert Auditor Pro 是一个 Claude Code 插件，在计划模式（Plan Mode）下使用双模型（Qwen + Gemini）并行审查计划，提供更全面、多角度的安全评估。

## 功能

- **双模型并行审计**: 同时调用 Qwen 和 Gemini，从不同模型视角审查计划
- **对比分析**: 生成两份独立审计报告，便于交叉验证
- **上下文感知**: 结合全局和项目级别的 CLAUDE.md 进行审查
- **配置灵活**: 支持自定义模型、代理设置

## 审查标准

插件根据以下 6 个标准评估计划：

1. **完整性**: 是否包含所有必要步骤？是否有明确的验收标准？
2. **正确性**: 计划是否正确解决问题？技术方案是否合理？
3. **安全性**: 是否避免破坏性操作？是否有适当的保护措施？
4. **可逆性**: 如果出现问题，更改是否可以轻松回滚？
5. **安全性**: 是否避免引入安全漏洞？
6. **最佳实践**: 是否遵循项目约定和编码规范？

## 安装

```bash
/plugin marketplace add crhan/ai-review-plugins
/plugin install expert-auditor-pro@ai-review-plugins
```

## 初始化配置

安装插件后，运行以下命令初始化环境并配置 API Keys：

```
/setup-skill
```

这将自动：
1. 检查并安装依赖（使用 uv）
2. 验证环境配置
3. 提示输入 Qwen 和 Gemini API Keys

## 配置说明

配置文件位于 `~/.claude/plugin/expert-auditor-pro/config.json`：

```json
{
  "qwen_api_key": "your-qwen-key",
  "gemini_api_key": "your-gemini-key",
  "qwen_model": "qwen3.5-plus",
  "gemini_model": "gemini-3.1-pro-preview",
  "proxy": "http://127.0.0.1:7890"
}
```

### 配置项说明

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `qwen_api_key` | - | Qwen API Key（必需） |
| `gemini_api_key` | - | Gemini API Key（必需） |
| `qwen_model` | qwen3.5-plus | Qwen 模型名称 |
| `gemini_model` | gemini-3.1-pro-preview | Gemini 模型名称 |
| `proxy` | http://127.0.0.1:7890 | HTTP 代理地址 |

## 使用方法

在 Plan Mode 下完成计划编写后，使用 `/audit-proposal` 触发双模型审计：

```
/audit-proposal
```

插件将：
1. 提取计划内容
2. 并行调用 Qwen 和 Gemini 审查
3. 生成对比审计报告

## 日志

日志位于 `~/.claude/plugin/expert-auditor-pro/logs/`：

```bash
# 查看 INFO 日志
tail -f ~/.claude/plugin/expert-auditor-pro/logs/info.jsonl | jq -r '.text // .message'

# 查看 DEBUG 日志
tail -f ~/.claude/plugin/expert-auditor-pro/logs/debug.jsonl | jq -r '.text // .message'
```

## 许可证

MIT
