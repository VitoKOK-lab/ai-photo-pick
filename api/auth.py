"""auth.py - 簡易 Bearer / query-param token 驗證"""
import sys
from pathlib import Path
from fastapi import Request
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import AUTH_TOKEN

# 無需驗證的路徑前綴
_PUBLIC_PREFIXES = (
    "/api/health",
    "/static/",       # 圖片靜態資源本身不擋（CDN 可快取）
)

# 無需驗證的完整路徑
_PUBLIC_EXACT = {"/"}


class TokenAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 未設定 token → 本機開發模式，全部放行
        if not AUTH_TOKEN:
            return await call_next(request)

        path = request.url.path

        # 公開路徑放行
        if path in _PUBLIC_EXACT:
            return await call_next(request)
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        # 取 token：先看 Authorization header，再看 query param
        token = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        if not token:
            token = request.query_params.get("token", "")

        if token != AUTH_TOKEN:
            if request.headers.get("accept", "").startswith("text/html"):
                # 瀏覽器 → 回可顯示的 HTML 登入提示頁
                return HTMLResponse(
                    status_code=401,
                    content=(
                        "<!doctype html><html><head>"
                        "<meta charset='utf-8'>"
                        "<title>需要驗證</title>"
                        "<style>body{font-family:sans-serif;display:flex;"
                        "justify-content:center;align-items:center;height:100vh;margin:0}"
                        ".box{text-align:center;padding:2rem;border:1px solid #ddd;border-radius:8px}"
                        "input{padding:.5rem;width:260px;margin:.5rem 0}"
                        "button{padding:.5rem 1.5rem;cursor:pointer}"
                        "</style></head><body><div class='box'>"
                        "<h2>🔒 需要驗證</h2>"
                        "<p>請輸入存取 Token</p>"
                        "<input id='t' type='password' placeholder='Token'/><br>"
                        "<button onclick=\"location.href=location.pathname+'?token='+document.getElementById('t').value\">"
                        "進入</button></div></body></html>"
                    ),
                )
            # API 客戶端 → 標準 401 + WWW-Authenticate
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)
