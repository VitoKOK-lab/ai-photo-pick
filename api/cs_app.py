"""cs_app.py - 只跑「客服訂單追蹤」的輕量入口。

正式部署在雲端時用這個，而不是 api.main：
它只載入客服模組，不需要 torch / chromadb 等影像辨識套件，
小主機也能很快裝好、很省資源。

啟動：
    uvicorn api.cs_app:app --host 0.0.0.0 --port 8000
"""
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import BASE_DIR, ALLOWED_ORIGINS
from api.auth import TokenAuthMiddleware
from api.cs import router as cs_router

app = FastAPI(title="客服訂單追蹤")

# 通行碼驗證（設定 JEWELRY_AUTH_TOKEN 才生效）
app.add_middleware(TokenAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(cs_router)

# 前端網頁（放最後，作為 fallback）— 進入點：/cs.html
app.mount("/", StaticFiles(directory=str(BASE_DIR / "web"), html=True), name="web")
