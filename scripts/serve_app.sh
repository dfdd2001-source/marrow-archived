#!/bin/bash
# 启动 Marrow 本地预览：http://127.0.0.1:8765/
# 静态模式运行（无需后端与数据库），18 个 core / 393 道习题全可用
# 用 no-cache 头的迷你服务器替代 python -m http.server：
# 后者不发缓存头，浏览器启发式缓存会让"改了代码看不到更新"。
cd "$(dirname "$0")/../app" && exec python3 - <<'PYEOF'
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        super().end_headers()

ThreadingHTTPServer(("127.0.0.1", 8765), NoCacheHandler).serve_forever()
PYEOF
