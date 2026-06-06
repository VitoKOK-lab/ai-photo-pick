"""quotes.py - 報價管理 + 價格推估"""
import sqlite3
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

router = APIRouter(prefix="/api/quotes", tags=["quotes"])

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
    description: str
    final_price: int
    material: Optional[str] = None
    gemstone: Optional[str] = None
    gemstone_origin: Optional[str] = None
    quote_date: Optional[str] = None
    notes: Optional[str] = None
    photo_id: Optional[int] = None

class QuoteUpdate(BaseModel):
    description: Optional[str] = None
    final_price: Optional[int] = None
    material: Optional[str] = None
    gemstone: Optional[str] = None
    gemstone_origin: Optional[str] = None
    quote_date: Optional[str] = None
    notes: Optional[str] = None


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
def create_quote(body: QuoteCreate):
    if body.final_price <= 0:
        raise HTTPException(status_code=400, detail="final_price 需為正整數")
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO quotes (description, final_price, material, gemstone,
                               gemstone_origin, quote_date, notes, photo_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (body.description, body.final_price, body.material, body.gemstone,
         body.gemstone_origin, body.quote_date, body.notes, body.photo_id)
    )
    qid = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": qid}


@router.delete("/{quote_id}")
def delete_quote(quote_id: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Quote not found")
    return {"deleted": True}


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
    material: Optional[str] = None,
    gemstone: Optional[str] = None,
):
    """根據 material/gemstone 推估價格（不更新資料庫）"""
    result = _estimate(material, gemstone)
    if not result:
        return {"estimated": False, "message": "報價資料不足，無法推估"}
    return {"estimated": True, **result}


@router.post("/batch-estimate")
def batch_estimate(min_samples: int = Query(3, ge=1)):
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
