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
        ("setting_amount",   "TEXT"),
        ("craft_complexity", "TEXT"),
        ("metal_color",      "TEXT"),
    ]
    conn = sqlite3.connect(SQLITE_PATH)
    existing = {r[1] for r in conn.execute("PRAGMA table_info(photos)")}
    for col, typ in new_cols:
        if col not in existing:
            conn.execute(f"ALTER TABLE photos ADD COLUMN {col} {typ}")
            print(f"[DB migration] 新增欄位：{col}")

    # 縮短鑽石等級標籤
    style_renames = [
        ('簡約(5顆鑽內)',  '簡約'),
        ('輕奢(20顆鑽內)', '輕奢'),
        ('豪鑲滿鑲鑽',     '豪鑲'),
    ]
    for old, new in style_renames:
        conn.execute("UPDATE photos SET style=? WHERE style=?", (new, old))

    # 從 material 自動推導 metal_color
    conn.execute("UPDATE photos SET metal_color='金' WHERE metal_color IS NULL AND material IN ('18K黃金','18K玫瑰金')")
    conn.execute("UPDATE photos SET metal_color='銀' WHERE metal_color IS NULL AND material IN ('18K白金','925銀','鉑金')")

    conn.commit()
    conn.close()

    # 同步更新 training_labels_style.json 裡的舊標籤
    import json
    labels_path = BASE_DIR / "data" / "training_labels_style.json"
    if labels_path.exists():
        try:
            labels = json.loads(labels_path.read_text(encoding="utf-8"))
            remap = {'簡約(5顆鑽內)': '簡約', '輕奢(20顆鑽內)': '輕奢', '豪鑲滿鑲鑽': '豪鑲'}
            updated = {k: remap.get(v, v) for k, v in labels.items()}
            if updated != labels:
                labels_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
                print("[DB migration] training_labels_style.json 標籤已縮短")
        except Exception:
            pass


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
