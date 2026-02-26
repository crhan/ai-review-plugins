# audit_proposal

调用 main.py，并行调用双模型，返回 Markdown 报告。

## 操作步骤

1. 从 stdin 读取计划内容（JSON 格式）
2. 调用 scripts/main.py 执行审计
3. 输出 Markdown 格式的对比报告

## 调用命令

```bash
python3 scripts/main.py --plan-file - <<< '{"plan": "YOUR_PLAN_CONTENT"}'
```

## 输出格式

```markdown
# 双模型审计报告

## Qwen 审查结果
[Qwen 的审查意见]

## Gemini 审查结果
[Gemini 的审查意见]

## 综合结论
[最终建议]
```
