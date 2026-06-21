"""main.py - FastAPI 入口"""
import io
import sqlite3
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import BASE_DIR, PROCESSED_DIR, ALLOWED_ORIGINS, SQLITE_PATH, PRICING_DB_PATH


def _run_migrations():
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

    # 確保新表存在（首次升級時建立）
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            username      TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'editor' CHECK(role IN ('admin','editor','viewer')),
            is_active     INTEGER NOT NULL DEFAULT 1,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS blocked_ips (
            ip         TEXT PRIMARY KEY,
            reason     TEXT,
            blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS guest_links (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            token         TEXT NOT NULL UNIQUE,
            customer_id   INTEGER NOT NULL,
            customer_name TEXT NOT NULL,
            created_by    TEXT,
            expires_at    TIMESTAMP NOT NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active     INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS staff (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS customers (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            line_id       TEXT,
            phone         TEXT,
            notes         TEXT,
            session_count INTEGER DEFAULT 0,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_customers_line_id ON customers(line_id);
        CREATE TABLE IF NOT EXISTS customer_tags (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            tag         TEXT NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            UNIQUE(customer_id, tag)
        );
        CREATE INDEX IF NOT EXISTS idx_customer_tags_cid ON customer_tags(customer_id);
        CREATE TABLE IF NOT EXISTS customer_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            staff_id    INTEGER,
            notes       TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY (staff_id) REFERENCES staff(id)
        );
        CREATE TABLE IF NOT EXISTS customer_favorites (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            photo_id    INTEGER NOT NULL,
            session_id  INTEGER,
            note        TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY (photo_id)    REFERENCES photos(id),
            FOREIGN KEY (session_id)  REFERENCES customer_sessions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_cf_customer ON customer_favorites(customer_id);
        CREATE INDEX IF NOT EXISTS idx_cf_photo    ON customer_favorites(photo_id);
        CREATE TABLE IF NOT EXISTS transactions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name    TEXT NOT NULL,
            category     TEXT,
            material     TEXT,
            gemstone     TEXT,
            stone_spec   TEXT,
            metal_weight REAL,
            price        INTEGER NOT NULL,
            sale_date    DATE,
            notes        TEXT,
            client_name  TEXT,
            photo_id     INTEGER,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (photo_id) REFERENCES photos(id)
        );
        CREATE INDEX IF NOT EXISTS idx_tx_material ON transactions(material);
        CREATE INDEX IF NOT EXISTS idx_tx_gemstone ON transactions(gemstone);
        CREATE INDEX IF NOT EXISTS idx_tx_date     ON transactions(sale_date);
    """)
    conn.commit()


    # 簡化寶石顏色標籤
    color_renames = [
        ('紅色', '紅'), ('粉紅色', '粉'), ('橙色', '黃'), ('黃色', '黃'),
        ('綠色', '綠'), ('藍綠色', '藍'), ('藍色', '藍'),
        ('紫色', '紫'), ('白色', '白'), ('無色透明', '白'),
        ('黑色', '彩'), ('灰色', '彩'), ('棕色', '彩'), ('多色', '彩'),
    ]
    for old, new in color_renames:
        conn.execute("UPDATE photos SET color=? WHERE color=?", (new, old))

    # 縮短鑽石等級標籤，豪鑲改奢華
    style_renames = [
        ('簡約(5顆鑽內)',  '簡約'),
        ('輕奢(20顆鑽內)', '輕奢'),
        ('豪鑲滿鑲鑽',     '奢華'),
        ('豪鑲',           '奢華'),
    ]
    for old, new in style_renames:
        conn.execute("UPDATE photos SET style=? WHERE style=?", (new, old))

    # 從 material 自動推導 metal_color
    conn.execute("UPDATE photos SET metal_color='金' WHERE metal_color IS NULL AND material IN ('18K黃金','18K玫瑰金')")
    conn.execute("UPDATE photos SET metal_color='銀' WHERE metal_color IS NULL AND material IN ('18K白金','925銀','鴣金')")

    # 墜子合併至項鍊
    conn.execute("UPDATE photos SET category='項鍊' WHERE category='墜子'")

    conn.commit()
    conn.close()

    import json
    labels_path = BASE_DIR / "data" / "training_labels_style.json"
    if labels_path.exists():
        try:
            labels = json.loads(labels_path.read_text(encoding="utf-8"))
            remap = {'簡約(5顆鑽內)': '簡約', '輕奢(20顆鑽內)': '輕奢', '豪鑲滿鑲鑽': '奢華', '豪鑲': '奢華'}
            updated = {k: remap.get(v, v) for k, v in labels.items()}
            if updated != labels:
                labels_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
                print("[DB migration] training_labels_style.json 標籤已縮短")
        except Exception:
            pass


_run_migrations()

app = FastAPI(title="Jewelry DB API")


class NoCacheHTMLMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.endswith(".html") or path == "/" or not "." in path.split("/")[-1]:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.headers["Surrogate-Control"] = "no-store"  # Cloudflare CDN skip cache
            response.headers["CDN-Cache-Control"] = "no-store"  # Cloudflare specific
        return response


app.add_middleware(NoCacheHTMLMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

_full_dir  = PROCESSED_DIR / "full"
_thumb_dir = PROCESSED_DIR / "thumb"
_micro_dir = PROCESSED_DIR / "micro"
_classified_dir = BASE_DIR / "data" / "02_classified"
_quote_refs_dir = BASE_DIR / "data" / "quote_refs"

_full_dir.mkdir(parents=True, exist_ok=True)
_thumb_dir.mkdir(parents=True, exist_ok=True)
_micro_dir.mkdir(parents=True, exist_ok=True)
_quote_refs_dir.mkdir(parents=True, exist_ok=True)
_classified_dir.mkdir(parents=True, exist_ok=True)

app.mount("/static/full",        StaticFiles(directory=str(_full_dir)),        name="full")
app.mount("/static/thumb",       StaticFiles(directory=str(_thumb_dir)),       name="thumb")
app.mount("/static/micro",       StaticFiles(directory=str(_micro_dir)),       name="micro")
app.mount("/static/classified",  StaticFiles(directory=str(_classified_dir)),  name="classified")
app.mount("/static/quote-refs",  StaticFiles(directory=str(_quote_refs_dir)),  name="quote-refs")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/thumb/{photo_id}")
def get_thumb(photo_id: int, size: int = 320):
    """動態生成縮圖並快取到 thumb 目錄。"""
    cache_path = _thumb_dir / f"{photo_id}_{size}.jpg"
    if cache_path.exists():
        return Response(content=cache_path.read_bytes(), media_type="image/jpeg")

    conn = sqlite3.connect(SQLITE_PATH)
    row = conn.execute("SELECT full_path, filename FROM photos WHERE id=?", (photo_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404)

    full_path = Path(row[0]) if row[0] else None
    if full_path is None or not full_path.exists():
        # fallback: try classified dir
        full_path = _classified_dir / row[1] if row[1] else None
    if full_path is None or not full_path.exists():
        raise HTTPException(status_code=404)

    try:
        from PIL import Image
        img = Image.open(full_path).convert("RGB")
        img.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82, optimize=True)
        data = buf.getvalue()
        cache_path.write_bytes(data)
        return Response(content=data, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
from api.upload       import router as upload_router
from api.auth         import router as auth_router
from api.pricing      import router as pricing_router
from api.agents       import router as agents_router
from api.staging      import router as staging_router
from api.admin        import router as admin_router
from api.guest_links  import router as guest_links_router

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
app.include_router(upload_router)
app.include_router(auth_router)
app.include_router(pricing_router)

@app.on_event("startup")
def _post_startup_cleanup():
    """在所有 router 初始化（含建表）後執行的清理。"""
    conn = sqlite3.connect(PRICING_DB_PATH)
    try:
        conn.execute("DELETE FROM pricing_metals WHERE material='9K金'")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
app.include_router(agents_router)
app.include_router(staging_router)
app.include_router(admin_router)
app.include_router(guest_links_router)

app.mount("/", StaticFiles(directory=str(BASE_DIR / "web"), html=True), name="web")
