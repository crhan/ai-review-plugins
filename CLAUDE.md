# CLAUDE.md

此文件为 Claude Code (claude.ai/code) 在本项目中工作时提供指导。

## 项目概述

这是一个 **Claude Code 插件**，使用 Google 的 Gemini AI 实现 AI 驱动的计划审查系统。它拦截 `ExitPlanMode` 调用，在执行计划前进行验证。

## 架构

```
.claude-plugin/plugin.json  → 插件声明
hooks/hooks.json             → 钩子触发定义（ExitPlanMode 的 PreToolUse）
scripts/plan-gemini-review.py → 主逻辑（Python 脚本）
```

钩子在 `ExitPlanMode` 工具调用时触发，提取计划内容，组装上下文（全局 CLAUDE.md、项目 CLAUDE.md、近期用户消息），发送到 Gemini 审查，并返回 APPROVE/CONCERNS/REJECT。

## 运行脚本

```bash
python3 /home/ruohanc/project/review_hooks/scripts/plan-gemini-review.py
```

脚本从 stdin 读取 JSON 输入（由 Claude Code 钩子系统提供）。

## 配置

- **禁用审查**：设置环境变量 `GEMINI_REVIEW_OFF=1`
- **代理**：API 调用使用 `http://127.0.0.1:7890`（脚本中硬编码）
- **API**：使用 Gemini CLI，模型为 `gemini-3-pro-preview`
- **标记清理**：清理 `~/.claude/hooks/.markers/` 中超过 30 分钟的过期标记

## 审查标准

插件根据以下 6 个标准评估计划：
1. 完整性 - 是否包含所有必要步骤？
2. 正确性 - 计划是否正确解决问题？
3. 安全性 - 是否有防止破坏性操作的保护措施？
4. 可逆性 - 更改是否可以回滚？
5. 安全性 - 是否引入安全漏洞？
6. 最佳实践 - 是否遵循项目约定？

## 日志输出

日志同时写入 `review_hooks.log` 和 stderr。日志格式包含会话 ID（前 8 位）。
