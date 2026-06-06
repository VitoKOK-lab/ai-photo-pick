"""auth.py - 簡易 Bearer / query-param token 驗證"""
import sys
from pathlib import Path
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
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
            # HTML 請求 → 導到登入提示頁；API 請求 → 回 401
            if request.headers.get("accept", "").startswith("text/html"):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "未授權。請在 URL 加上 ?token=YOUR_TOKEN"},
                )
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)
