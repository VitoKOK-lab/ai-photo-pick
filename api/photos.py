"""photos.py - /api/photos 列表 + 單張詳細"""
import sqlite3
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

router = APIRouter(prefix="/api/photos", tags=["photos"])

PAGE_SIZE = 9

def _conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _safe(row, key, default=None):
    try:
        return row[key]
    except (IndexError, KeyError):
        return default

def _photo_url(row) -> str:
    try:
        full_path = row["full_path"] or ""
    except (IndexError, KeyError):
        full_path = ""
    if "02_classified" in str(full_path):
        from config.settings import BASE_DIR
        classified_dir = str(BASE_DIR / "data" / "02_classified")
        rel = str(full_path).replace(classified_dir, "").lstrip("/\\")
        if rel:
            return f"/static/classified/{rel}"
    return f"/static/full/{row['filename']}"

def _row_to_dict(row) -> dict:
    url = _photo_url(row)
    return {
        "id":                  row["id"],
        "filename":            row["filename"],
        "micro_url":           url,
        "thumb_url":           url,
        "full_url":            url,
        "color":               row["color"],
        "category":            row["category"],
        "material":            row["material"],
        "gemstone":            row["gemstone"],
        "style":               _safe(row, "style"),
        "stone_shape":         _safe(row, "stone_shape"),
        "stone_size":          _safe(row, "stone_size"),
        "diamond_status":      _safe(row, "diamond_status"),
        "price_band":          row["price_band"],
        "price_estimate_low":  row["price_estimate_low"],
        "price_estimate_high": row["price_estimate_high"],
        "price_source":        row["price_source"],
        "view_count":          row["view_count"],
        "favorite_count":      row["favorite_count"],
    }

@router.get("")
def list_photos(
    color:        Optional[str] = None,
    category:     Optional[str] = None,
    material:     Optional[str] = None,
    diamond_status: Optional[str] = None,
    gemstone:     Optional[str] = None,
    price_band:   Optional[str] = None,
    style:        Optional[str] = None,
    stone_shape:  Optional[str] = None,
    stone_size:   Optional[str] = None,
    page:         int = Query(1, ge=1),
    sort:         str = Query("random", pattern="^(random|newest|popular)$"),
    exclude_seen: bool = False,
    session_id:   Optional[str] = None,
):
    wheres = []
    params = []

    def add_in(field: str, value: Optional[str]):
        if value:
            items = [v.strip() for v in value.split(",") if v.strip()]
            if items:
                placeholders = ",".join("?" * len(items))
                wheres.append(f"{field} IN ({placeholders})")
                params.extend(items)

    add_in("color",          color)
    add_in("category",       category)
    add_in("material",       material)
    add_in("diamond_status", diamond_status)
    add_in("gemstone",       gemstone)
    add_in("price_band",     price_band)
    add_in("style",          style)
    add_in("stone_shape",    stone_shape)
    add_in("stone_size",     stone_size)

    if exclude_seen and session_id:
        wheres.append(
            "id NOT IN (SELECT DISTINCT photo_id FROM events WHERE session_id = ? AND event_type IN ('view', 'click'))"
        )
        params.append(session_id)

    where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    if sort == "random":
        order_clause = "ORDER BY RANDOM()"
    elif sort == "newest":
        order_clause = "ORDER BY created_at DESC"
    elif sort == "popular":
        order_clause = "ORDER BY (view_count + favorite_count * 3 + lock_count * 5) DESC"
    else:
        order_clause = "ORDER BY id"

    offset = (page - 1) * PAGE_SIZE

    conn = _conn()
    cur = conn.cursor()

    cur.execute(f"SELECT COUNT(*) FROM photos {where_clause}", params)
    total = cur.fetchone()[0]

    cur.execute(
        f"SELECT * FROM photos {where_clause} {order_clause} LIMIT ? OFFSET ?",
        params + [PAGE_SIZE, offset]
    )
    rows = cur.fetchall()
    conn.close()

    photos = [_row_to_dict(r) for r in rows]
    return {
        "photos":   photos,
        "total":    total,
        "page":     page,
        "has_more": offset + len(photos) < total,
    }

@router.get("/category-counts")
def category_counts():
    """回傳各 category 的照片數量"""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT category, COUNT(*) as cnt FROM photos WHERE category IS NOT NULL AND category != '' GROUP BY category")
    rows = cur.fetchall()
    conn.close()
    return {r["category"]: r["cnt"] for r in rows}

@router.get("/{photo_id}")
def get_photo(photo_id: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM photos WHERE id = ?", (photo_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")
    return _row_to_dict(row)

@router.patch("/{photo_id}")
def update_photo(photo_id: int, body: dict):
    allowed = {"category", "style", "color", "gemstone", "material", "price_band"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields")
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [photo_id]
    conn = _conn()
    conn.execute(f"UPDATE photos SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id=?", values)
    conn.commit()
    cur = conn.cursor()
    cur.execute("SELECT * FROM photos WHERE id = ?", (photo_id,))
    row = cur.fetchone()
    conn.close()
    return _row_to_dict(row)

@router.delete("/{photo_id}")
def delete_photo(photo_id: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT full_path FROM photos WHERE id = ?", (photo_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Photo not found")
    conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    conn.commit()
    conn.close()
    return {"deleted": photo_id}
