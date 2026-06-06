"""main.py - FastAPI 入口"""
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import BASE_DIR, PROCESSED_DIR

app = FastAPI(title="Jewelry DB API")

# CORS（MVP 階段全開，Phase 4 上線時收緊）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 靜態圖片
app.mount("/static/full", StaticFiles(directory=str(PROCESSED_DIR / "full")), name="full")
app.mount("/static/thumb", StaticFiles(directory=str(PROCESSED_DIR / "thumb")), name="thumb")
app.mount("/static/micro", StaticFiles(directory=str(PROCESSED_DIR / "micro")), name="micro")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Routers
from api.photos import router as photos_router
from api.similar import router as similar_router
from api.favorites import router as favorites_router
from api.locks import router as locks_router
from api.events import router as events_router

app.include_router(photos_router)
app.include_router(similar_router)
app.include_router(favorites_router)
app.include_router(locks_router)
app.include_router(events_router)


# 前端 HTML（放最後，作為 fallback）
app.mount("/", StaticFiles(directory=str(BASE_DIR / "web"), html=True), name="web")
