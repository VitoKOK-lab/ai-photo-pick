"""quotes.py - 報價管理 + 價格推估"""
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends, UploadFile, File
from pydantic import BaseModel
from api.auth import require_editor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, BASE_DIR

QUOTE_REFS_DIR = BASE_DIR / "data" / "quote_refs"
QUOTE_REFS_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


def _migrate():
    conn = sqlite3.connect(SQLITE_PATH)
    # Create table if it doesn't exist (safe if already exists)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_id INTEGER,
            description TEXT,
            final_price INTEGER NOT NULL DEFAULT 0,
            material TEXT,
            gemstone TEXT,
            gemstone_origin TEXT,
            quote_date DATE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for col, typ in [
        ('customer_name',   'TEXT'),
        ('original_data',   'TEXT'),
        ('adjusted_data',   'TEXT'),
        ('estimated_min',   'INTEGER'),
        ('estimated_max',   'INTEGER'),
        ('budget',          'INTEGER'),
        ('updated_at',      'TEXT'),
        ('stone_order_no',  'TEXT'),
        ('inquiry_time',    'TEXT'),
        ('source_channel',  'TEXT'),
        ('staff_name',      'TEXT'),
        ('ref_photo_url',   'TEXT'),
    ]:
        try:
            conn.execute(f"ALTER TABLE quotes ADD COLUMN {col} {typ}")
        except Exception:
            pass
    conn.commit()
    conn.close()

_migrate()

PRICE_BAND_RANGES = [
    (0,      10000,  "< 1萬"),
    (10000,  30000,  "1-3萬"),
    (30000,  60000,  "3-6萬"),
    (60000,  100000, "6-10萬"),
    (100000, 150000, "10-15萬"),
    (150000, None,   "> 15萬"),
]

def _price_to_band(price: int) -> str:
    for lo, hi, label in PRICE_BAND_RANGES:
        if hi is None or price < hi:
            return label
    return "> 15萬"

def _conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    idx = (len(s) - 1) * p
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return int(s[lo] + (s[hi] - s[lo]) * (idx - lo))


# ─── Models ────────────────────────────────────────────────
class QuoteCreate(BaseModel):
    description: Optional[str] = None
    final_price: Optional[int] = None
    material: Optional[str] = None
    gemstone: Optional[str] = None
    gemstone_origin: Optional[str] = None
    quote_date: Optional[str] = None
    notes: Optional[str] = None
    photo_id: Optional[int] = None
    customer_name: Optional[str] = None
    original_data: Optional[str] = None
    adjusted_data: Optional[str] = None
    estimated_min: Optional[int] = None
    estimated_max: Optional[int] = None
    budget: Optional[int] = None
    stone_order_no: Optional[str] = None
    inquiry_time: Optional[str] = None
    source_channel: Optional[str] = None
    staff_name: Optional[str] = None
    ref_photo_url: Optional[str] = None

class QuoteUpdate(BaseModel):
    description: Optional[str] = None
    final_price: Optional[int] = None
    material: Optional[str] = None
    gemstone: Optional[str] = None
    gemstone_origin: Optional[str] = None
    quote_date: Optional[str] = None
    notes: Optional[str] = None
    customer_name: Optional[str] = None
    lock: Optional[bool] = None  # set True to lock the quote


# ─── CRUD ──────────────────────────────────────────────────
@router.get("")
def list_quotes(
    material: Optional[str] = None,
    gemstone: Optional[str] = None,
    photo_id: Optional[int] = None,
    page: int = Query(1, ge=1),
):
    PAGE_SIZE = 30
    wheres, params = [], []
    if material:
        wheres.append("material = ?"); params.append(material)
    if gemstone:
        wheres.append("gemstone = ?"); params.append(gemstone)
    if photo_id is not None:
        wheres.append("photo_id = ?"); params.append(photo_id)

    where = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    offset = (page - 1) * PAGE_SIZE

    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM quotes {where}", params)
    total = cur.fetchone()[0]
    cur.execute(
        f"SELECT * FROM quotes {where} ORDER BY quote_date DESC, id DESC LIMIT ? OFFSET ?",
        params + [PAGE_SIZE, offset]
    )
    rows = cur.fetchall()
    conn.close()

    return {
        "quotes": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "has_more": offset + len(rows) < total,
    }


@router.post("")
def create_quote(body: QuoteCreate, _user=Depends(require_editor)):
    fp = body.final_price if body.final_price is not None else 0
    if fp < 0:
        raise HTTPException(status_code=400, detail="final_price 不可為負數")
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO quotes (description, final_price, material, gemstone,
                               gemstone_origin, quote_date, notes, photo_id,
                               customer_name, original_data, adjusted_data,
                               estimated_min, estimated_max, budget,
                               stone_order_no, inquiry_time, source_channel, staff_name,
                               ref_photo_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (body.description, fp, body.material, body.gemstone,
         body.gemstone_origin, body.quote_date, body.notes, body.photo_id,
         body.customer_name, body.original_data, body.adjusted_data,
         body.estimated_min, body.estimated_max, body.budget,
         body.stone_order_no, body.inquiry_time, body.source_channel, body.staff_name,
         body.ref_photo_url)
    )
    qid = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": qid}


@router.patch("/{quote_id}")
def update_quote(quote_id: int, body: QuoteUpdate, _user=Depends(require_editor)):
    conn = _conn()
    row = conn.execute("SELECT * FROM quotes WHERE id=?", (quote_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Quote not found")
    r = dict(row)
    # reject edits if already locked
    if r.get("locked_at") and body.lock is not True:
        conn.close()
        raise HTTPException(403, "此報價已鎖定，無法修改")
    fields: dict = {}
    if body.final_price is not None:
        if body.final_price < 0:
            raise HTTPException(400, "final_price 不可為負數")
        fields["final_price"] = body.final_price
    for attr in ("description","material","gemstone","gemstone_origin","quote_date","notes","customer_name"):
        val = getattr(body, attr)
        if val is not None:
            fields[attr] = val
    if body.lock is True and not r.get("locked_at"):
        from datetime import datetime
        fields["locked_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    if not fields:
        conn.close()
        return dict(r)
    set_clause = ", ".join(f"{k}=?" for k in fields)
    conn.execute(
        f"UPDATE quotes SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        list(fields.values()) + [quote_id]
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM quotes WHERE id=?", (quote_id,)).fetchone()
    conn.close()
    return dict(updated)


@router.post("/upload-ref-photo")
async def upload_ref_photo(file: UploadFile = File(...), _user=Depends(require_editor)):
    """上傳客人參考照片，儲存後回傳可存取的 URL。"""
    ext = Path(file.filename or "photo.jpg").suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}:
        raise HTTPException(400, "不支援的格式")
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = QUOTE_REFS_DIR / filename
    content = await file.read()
    # 壓縮至合理尺寸以節省空間
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(content)).convert("RGB")
        img.thumbnail((1200, 1200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        dest.with_suffix(".jpg").write_bytes(buf.getvalue())
        filename = dest.stem + ".jpg"
    except Exception:
        dest.write_bytes(content)
    return {"url": f"/static/quote-refs/{filename}"}


@router.delete("/all")
def delete_all_quotes(_user=Depends(require_editor)):
    conn = _conn()
    conn.execute("DELETE FROM quotes")
    conn.commit()
    conn.close()
    return {"deleted": True}


@router.delete("/{quote_id}")
def delete_quote(quote_id: int, _user=Depends(require_editor)):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Quote not found")
    return {"deleted": True}


# ─── 待確認報價（final_price = 0 或 NULL）─────────────────
@router.get("/pending")
def pending_quotes():
    """回傳所有尚未填入成交價的報價，含經過小時數。"""
    conn = _conn()
    try:
        rows = conn.execute(
            """SELECT id, description, gemstone, material, customer_name,
                      estimated_min, estimated_max, budget, photo_id,
                      created_at,
                      CAST((julianday('now') - julianday(COALESCE(created_at,'now'))) * 24 AS INTEGER) AS hours_elapsed
               FROM quotes
               WHERE final_price IS NULL OR final_price = 0
               ORDER BY created_at ASC"""
        ).fetchall()
    except Exception:
        rows = []
    conn.close()
    return [dict(r) for r in rows]


# ─── 統計 ──────────────────────────────────────────────────
@router.get("/stats")
def quote_stats():
    """各 material/gemstone 組合的價格統計"""
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT material, gemstone,
                  COUNT(*) as count,
                  MIN(final_price) as min_price,
                  MAX(final_price) as max_price,
                  CAST(AVG(final_price) AS INTEGER) as avg_price
           FROM quotes
           WHERE material IS NOT NULL OR gemstone IS NOT NULL
           GROUP BY material, gemstone
           ORDER BY count DESC"""
    )
    rows = cur.fetchall()

    cur.execute("SELECT COUNT(*), MIN(final_price), MAX(final_price), CAST(AVG(final_price) AS INTEGER) FROM quotes")
    total_row = cur.fetchone()
    conn.close()

    return {
        "total_quotes": total_row[0],
        "overall_min": total_row[1],
        "overall_max": total_row[2],
        "overall_avg": total_row[3],
        "by_combination": [dict(r) for r in rows],
    }


# ─── 價格推估 ──────────────────────────────────────────────
def _estimate(material: Optional[str], gemstone: Optional[str]) -> Optional[dict]:
    """
    從 quotes 表推估價格區間（25th ~ 75th percentile）
    優先用 material+gemstone 完整比對；樣本不足時降級到單維度
    """
    conn = _conn()
    cur = conn.cursor()

    def _fetch(where, params) -> list[int]:
        cur.execute(f"SELECT final_price FROM quotes WHERE {where}", params)
        return [r[0] for r in cur.fetchall()]

    prices = []
    source = None

    # 1. material + gemstone 完整比對
    if material and gemstone:
        prices = _fetch("material = ? AND gemstone = ?", [material, gemstone])
        if prices:
            source = f"material={material} + gemstone={gemstone}"

    # 2. gemstone 單獨（寶石決定大半價值）
    if not prices and gemstone:
        prices = _fetch("gemstone = ?", [gemstone])
        if prices:
            source = f"gemstone={gemstone}"

    # 3. material 單獨
    if not prices and material:
        prices = _fetch("material = ?", [material])
        if prices:
            source = f"material={material}"

    conn.close()

    if not prices:
        return None

    low  = _percentile(prices, 0.25)
    high = _percentile(prices, 0.75)
    mid  = (low + high) // 2

    return {
        "price_estimate_low":  low,
        "price_estimate_high": high,
        "price_band": _price_to_band(mid),
        "price_source": source,
        "sample_count": len(prices),
    }


@router.post("/estimate")
def estimate_price(
    material: Optional[str] = Query(None),
    gemstone: Optional[str] = Query(None),
):
    """根據 material/gemstone 推估價格（不更新資料庫）。參數從 query string 傳入。"""
    result = _estimate(material, gemstone)
    if not result:
        return {"estimated": False, "message": "報價資料不足，無法推估"}
    return {"estimated": True, **result}


@router.get("/estimate-by-attrs")
def estimate_by_attrs(
    category:    Optional[str] = None,
    stone_size:  Optional[str] = None,
    stone_shape: Optional[str] = None,
    style:       Optional[str] = None,
    gemstone:    Optional[str] = None,
    color:       Optional[str] = None,
):
    """
    根據 5 個估價條件從 transactions + quotes 表推估價格區間。
    同時回傳符合條件的參考照片。
    """
    conn = _conn()
    cur = conn.cursor()

    def _fetch_tx(where_clause, params) -> list[int]:
        try:
            cur.execute(f"SELECT price FROM transactions WHERE {where_clause}", params)
            return [r[0] for r in cur.fetchall()]
        except Exception:
            return []

    prices: list[int] = []
    source: Optional[str] = None

    # 由精到粗逐步嘗試
    if not prices and category and gemstone and style:
        prices = _fetch_tx("category=? AND gemstone=? AND style=?", [category, gemstone, style])
        if prices: source = f"{category}+{gemstone}+{style}"

    if not prices and category and gemstone:
        prices = _fetch_tx("category=? AND gemstone=?", [category, gemstone])
        if prices: source = f"{category}+{gemstone}"

    if not prices and gemstone:
        prices = _fetch_tx("gemstone=?", [gemstone])
        if prices: source = f"gemstone={gemstone}"

    if not prices and category:
        prices = _fetch_tx("category=?", [category])
        if prices: source = f"category={category}"

    # 若 transactions 無資料，從 quotes 表嘗試
    if not prices and gemstone:
        try:
            cur.execute("SELECT final_price FROM quotes WHERE gemstone=?", [gemstone])
            prices = [r[0] for r in cur.fetchall()]
            if prices: source = f"quotes:gemstone={gemstone}"
        except Exception:
            pass

    # 查詢符合條件的參考照片
    photo_wheres: list[str] = []
    photo_params: list = []
    for field, val in [
        ("category",    category),
        ("gemstone",    gemstone),
        ("stone_shape", stone_shape),
        ("style",       style),
        ("color",       color),
    ]:
        if val:
            photo_wheres.append(f"{field}=?")
            photo_params.append(val)

    photo_sql = ("WHERE " + " AND ".join(photo_wheres)) if photo_wheres else ""
    try:
        cur.execute(
            f"SELECT id, filename, category, gemstone, color, style, stone_shape, stone_size "
            f"FROM photos {photo_sql} ORDER BY RANDOM() LIMIT 12",
            photo_params,
        )
        matching_photos = [dict(r) for r in cur.fetchall()]
    except Exception:
        matching_photos = []

    conn.close()

    if not prices:
        return {
            "estimated":      False,
            "message":        "成交紀錄不足，無法推估",
            "sample_count":   0,
            "matching_photos": matching_photos,
        }

    low  = _percentile(prices, 0.25)
    high = _percentile(prices, 0.75)
    return {
        "estimated":       True,
        "price_low":       low,
        "price_high":      high,
        "sample_count":    len(prices),
        "source":          source,
        "matching_photos": matching_photos,
    }


@router.post("/batch-estimate")
def batch_estimate(min_samples: int = Query(3, ge=1, description="最少需要幾筆報價才推估")):
    """
    批次更新所有尚未定價照片的 price_estimate_* 欄位
    只在 price_source IS NULL（從未推估過）時更新
    """
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, material, gemstone FROM photos WHERE price_source IS NULL"
    )
    photos = cur.fetchall()

    updated = 0
    skipped = 0

    for photo in photos:
        result = _estimate(photo["material"], photo["gemstone"])
        if not result or result["sample_count"] < min_samples:
            skipped += 1
            # material + gemstone 都是 NULL → 永遠無法推估，寫 sentinel 避免重複掃描
            if not photo["material"] and not photo["gemstone"]:
                cur.execute(
                    "UPDATE photos SET price_source = 'no_data' WHERE id = ?",
                    (photo["id"],)
                )
            continue
        cur.execute(
            """UPDATE photos
               SET price_estimate_low  = ?,
                   price_estimate_high = ?,
                   price_band          = ?,
                   price_source        = ?
               WHERE id = ?""",
            (result["price_estimate_low"], result["price_estimate_high"],
             result["price_band"], result["price_source"], photo["id"])
        )
        updated += 1

    conn.commit()
    conn.close()
    return {
        "updated": updated,
        "skipped": skipped,
        "total": len(photos),
    }
