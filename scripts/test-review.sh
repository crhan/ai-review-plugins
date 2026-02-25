#!/bin/bash
# Test script for plan-gemini-review.py

PLAN='{"tool_name": "ExitPlanMode", "session_id": "test-merge", "cwd": "/Users/ruohanc/Documents/GitHub/ai-review-plugins", "transcript_path": "/Users/ruohanc/.claude/transcripts/test-merge.jsonl", "tool_input": {"plan": "计划：修复用户登录问题\n\n目标：修复登录页面验证码错误时无法正确显示错误信息的问题\n\n步骤：\n1. 定位登录相关的前端代码\n2. 修改错误处理逻辑\n3. 添加单元测试\n4. 部署验证\n\n验收标准：\n- 验证码错误时显示具体信息\n- 单元测试通过"}}'

echo "$PLAN" | python3 /Users/ruohanc/Documents/GitHub/ai-review-plugins/scripts/plan-gemini-review.py 2>&1
