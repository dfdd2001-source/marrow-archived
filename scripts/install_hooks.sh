#!/bin/bash
# 把仓库内的钩子安装到 .git/hooks（幂等）
cd "$(dirname "$0")/.."
cp scripts/git-hooks/pre-push .git/hooks/pre-push
chmod +x .git/hooks/pre-push scripts/ci_local.sh
echo "pre-push 钩子已安装：每次 git push 前自动运行本地 CI"
