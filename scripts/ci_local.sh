#!/bin/bash
# 本地 CI：与 .github/workflows/ci.yml 相同的三道门。
# GitHub Actions 因账户计费不可用期间，经 pre-push 钩子在每次推送前自动执行。
set -e
cd "$(dirname "$0")/.."
echo "== 1/3 core 门禁（verify 重算）=="
python3 scripts/validate_all_cores.py
echo "== 2/3 单元测试 =="
python3 -m unittest discover -s tests
echo "== 3/3 前端表达式守卫 =="
node tests/expr_guard.test.mjs
echo "== 本地 CI 全绿 ✓ =="
