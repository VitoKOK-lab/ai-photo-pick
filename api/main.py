"""main.py - FastAPI 入口"""
import sqlite3
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import BASE_DIR, PROCESSED_DIR, ALLOWED_ORIGINS, SQLITE_PATH


def _run_migrations():
    """啟動時確保所有新欄位存在"""
    new_cols = [
        ("setting_amount", "TEXT"),
    ]
    conn = sqlite3.connect(SQLITE_PATH)
    existing = {r[1] for r in conn.execute("PRAGMA table_info(photos)")}
    for col, typ in new_cols:
        if col not in existing:
            conn.execute(f"ALTER TABLE photos ADD COLUMN {col} {typ}")
            print(f"[DB migration] 新增欄位：{col}")
    conn.commit()
    conn.close()


_run_migrations()

app = FastAPI(title="Jewelry DB API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 靜態圖片：優先用 03_processed，沒有則 fallback 到 02_classified
_full_dir  = PROCESSED_DIR / "full"
_thumb_dir = PROCESSED_DIR / "thumb"
_micro_dir = PROCESSED_DIR / "micro"
_classified_dir = BASE_DIR / "data" / "02_classified"

_full_dir.mkdir(parents=True, exist_ok=True)
_thumb_dir.mkdir(parents=True, exist_ok=True)
_micro_dir.mkdir(parents=True, exist_ok=True)
_classified_dir.mkdir(parents=True, exist_ok=True)

app.mount("/static/full",       StaticFiles(directory=str(_full_dir)),       name="full")
app.mount("/static/thumb",      StaticFiles(directory=str(_thumb_dir)),      name="thumb")
app.mount("/static/micro",      StaticFiles(directory=str(_micro_dir)),      name="micro")
app.mount("/static/classified", StaticFiles(directory=str(_classified_dir)), name="classified")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Routers
from api.photos       import router as photos_router
from api.similar      import router as similar_router
from api.favorites    import router as favorites_router
from api.locks        import router as locks_router
from api.events       import router as events_router
from api.stats        import router as stats_router
from api.quotes       import router as quotes_router
from api.backup       import router as backup_router
from api.staff        import router as staff_router
from api.customers    import router as customers_router
from api.transactions import router as transactions_router

app.include_router(photos_router)
app.include_router(similar_router)
app.include_router(favorites_router)
app.include_router(locks_router)
app.include_router(events_router)
app.include_router(stats_router)
app.include_router(quotes_router)
app.include_router(backup_router)
app.include_router(staff_router)
app.include_router(customers_router)
app.include_router(transactions_router)


# 前端 HTML（放最後，作為 fallback）
app.mount("/", StaticFiles(directory=str(BASE_DIR / "web"), html=True), name="web")
