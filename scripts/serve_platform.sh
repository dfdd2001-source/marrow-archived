#!/bin/bash
# 启动 Marrow 平台（PWA + 导入/流水线 API）：http://127.0.0.1:8765/
# 解释器优先级：$MARROW_PY > /opt/anaconda3/bin/python3（fastapi 所在环境）> python3
# 需要 fastapi/uvicorn 与 .env 中的 AGNES_API_KEY
pkill -f "http.server 8765" 2>/dev/null
pkill -f "uvicorn.*8765" 2>/dev/null
sleep 0.5
if [ -n "$MARROW_PY" ]; then PY="$MARROW_PY"
elif [ -x /opt/anaconda3/bin/python3 ]; then PY=/opt/anaconda3/bin/python3
else PY=python3; fi
cd "$(dirname "$0")/.." && exec "$PY" -m uvicorn backend.platform:app --host 127.0.0.1 --port 8765
