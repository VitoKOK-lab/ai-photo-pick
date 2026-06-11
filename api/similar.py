"""similar.py - 找相似（同品項 → 鑽石款式 → 價格帶）"""
import sqlite3
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

router = APIRouter(prefix="/api/photos", tags=["similar"])

def _conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _photo_url(d: dict) -> str:
    full_path = d.get("full_path") or "" if isinstance(d, dict) else (d["full_path"] or "")
    if "02_classified" in str(full_path):
        from config.settings import BASE_DIR
        classified_dir = str(BASE_DIR / "data" / "02_classified")
        rel = str(full_path).replace(classified_dir, "").lstrip("/\\")
        if rel and not rel.endswith(('.jpg','.jpeg','.png','.webp')):
            rel += ".jpg"
        if rel:
            return f"/static/classified/{rel}"
    return f"/static/full/{d['filename']}"

def _to_dict(row) -> dict:
    d = dict(row)
    url = _photo_url(d)
    return {
        "id":         d["id"],
        "filename":   d["filename"],
        "micro_url":  url,
        "thumb_url":  url,
        "full_url":   url,
        "category":   d.get("category"),
        "style":      d.get("style"),
        "material":   d.get("material"),
        "gemstone":   d.get("gemstone"),
        "color":      d.get("color"),
        "price_band": d.get("price_band"),
    }

@router.get("/{photo_id}/similar")
def find_similar(
    photo_id: int,
    limit: int = Query(12, ge=1, le=50),
):
    conn = _conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM photos WHERE id = ?", (photo_id,))
    anchor_row = cur.fetchone()
    if not anchor_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Photo not found")
    anchor = dict(anchor_row)

    # 同品項，依相似度分組後各組內隨機排列
    # 相似分：style 符合 +2，price_band 符合 +1，其餘 0
    cur.execute(
        """
        SELECT *,
          (CASE WHEN style = ? AND style IS NOT NULL AND style != '' THEN 2 ELSE 0 END
         + CASE WHEN price_band = ? AND price_band IS NOT NULL AND price_band != '' THEN 1 ELSE 0 END
          ) AS sim_score
        FROM photos
        WHERE category = ? AND id != ?
        ORDER BY sim_score DESC, RANDOM()
        """,
        (
            anchor.get("style") or "",
            anchor.get("price_band") or "",
            anchor.get("category"),
            photo_id,
        ),
    )
    rows = cur.fetchall()
    conn.close()

    similar = [_to_dict(r) for r in rows[:limit]]
    return {
        "anchor": _to_dict(anchor_row),
        "similar": similar,
    }
