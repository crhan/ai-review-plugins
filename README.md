# review-hooks

Claude Code 插件 - 使用 Gemini AI 进行计划审查

## 简介

这是一个 Claude Code 插件，在用户尝试退出计划模式（ExitPlanMode）时自动拦截并使用 Google Gemini AI 对计划进行安全审查。

## 功能

- **自动审查**: 在执行计划前自动调用 Gemini 进行审查
- **多维度评估**: 从 6 个维度评估计划质量
- **上下文感知**: 结合全局和项目级别的 CLAUDE.md 进行审查
- **可配置**: 支持通过环境变量禁用审查

## 审查标准

插件根据以下 6 个标准评估计划：

1. **完整性 (Completeness)**: 是否包含所有必要步骤？是否有明确的验收标准？
2. **正确性 (Correctness)**: 计划是否正确解决问题？技术方案是否合理？
3. **安全性 (Safety)**: 是否避免破坏性操作？是否有适当的保护措施？
4. **可逆性 (Reversibility)**: 如果出现问题，更改是否可以轻松回滚？
5. **安全性 (Security)**: 是否避免引入安全漏洞？
6. **最佳实践 (Best Practices)**: 是否遵循项目约定和编码规范？

## 安装

1. 克隆仓库到本地：

```bash
git clone https://github.com/crhan/review-hooks.git ~/.claude/plugins/review-hooks
```

2. 在 Claude Code 设置中启用插件

## 配置

### 禁用审查

设置环境变量 `GEMINI_REVIEW_OFF=1` 可以禁用计划审查：

```bash
export GEMINI_REVIEW_OFF=1
```

### 代理设置

脚本默认使用 `http://127.0.0.1:7890` 作为代理。如需修改，编辑 `scripts/plan-gemini-review.py`：

```python
env["http_proxy"] = "http://127.0.0.1:7890"
env["https_proxy"] = "http://127.0.0.1:7890"
```

### API 模型

默认使用 `gemini-3-pro-preview` 模型。如需修改，编辑脚本中的模型名称：

```python
["gemini", "-m", "gemini-3-pro-preview", "-p", prompt]
```

## 工作原理

1. 用户调用 `ExitPlanMode` 时，钩子触发
2. 脚本提取计划内容（从工具输入或 `~/.claude/plans/` 目录）
3. 组装上下文：
   - 全局 CLAUDE.md (`~/config/CLAUDE.md`)
   - 项目 CLAUDE.md（前 150 行）
   - 近期用户消息（最近 5 条）
4. 发送至 Gemini 进行审查
5. 返回结果：
   - `APPROVE`: 计划通过审查，允许执行
   - `CONCERNS`: 计划需要小幅改进
   - `REJECT`: 计划存在关键问题

## 日志

日志同时写入 `review_hooks.log` 和 stderr，便于调试和问题排查。

## 许可证

MIT
