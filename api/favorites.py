"""favorites.py - 喜愛清單 CRUD"""
import sqlite3
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

router = APIRouter(prefix="/api/favorites", tags=["favorites"])

class FavoriteAdd(BaseModel):
    photo_id: int
    session_id: str
    note: Optional[str] = None

def _conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@router.post("")
def add_favorite(body: FavoriteAdd):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM photos WHERE id = ?", (body.photo_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Photo not found")

    try:
        cur.execute(
            "INSERT INTO favorites (photo_id, session_id, note) VALUES (?, ?, ?)",
            (body.photo_id, body.session_id, body.note)
        )
        fav_id = cur.lastrowid
        cur.execute(
            "UPDATE photos SET favorite_count = favorite_count + 1 WHERE id = ?",
            (body.photo_id,)
        )
        conn.commit()
        conn.close()
        return {"id": fav_id, "photo_id": body.photo_id}
    except sqlite3.IntegrityError:
        conn.close()
        return {"already_exists": True, "photo_id": body.photo_id}

@router.delete("/{photo_id}")
def remove_favorite(photo_id: int, session_id: str = Query(...)):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM favorites WHERE photo_id = ? AND session_id = ?",
        (photo_id, session_id)
    )
    if cur.rowcount > 0:
        cur.execute(
            "UPDATE photos SET favorite_count = MAX(0, favorite_count - 1) WHERE id = ?",
            (photo_id,)
        )
        conn.commit()
    conn.close()
    return {"deleted": cur.rowcount > 0}

@router.get("")
def list_favorites(session_id: str = Query(...), page: int = 1):
    PAGE_SIZE = 9
    offset = (page - 1) * PAGE_SIZE
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT f.id as fav_id, f.created_at as fav_created_at, p.*
        FROM favorites f
        JOIN photos p ON p.id = f.photo_id
        WHERE f.session_id = ?
        ORDER BY f.created_at DESC
        LIMIT ? OFFSET ?
        """,
        (session_id, PAGE_SIZE, offset)
    )
    rows = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM favorites WHERE session_id = ?", (session_id,))
    total = cur.fetchone()[0]
    conn.close()

    favorites = [{
        "fav_id": r["fav_id"],
        "photo_id": r["id"],
        "filename": r["filename"],
        "micro_url": f"/static/micro/{r['filename']}",
        "thumb_url": f"/static/thumb/{r['filename']}",
        "full_url": f"/static/full/{r['filename']}",
        "color": r["color"],
        "category": r["category"],
        "gemstone": r["gemstone"],
        "price_band": r["price_band"],
        "favorited_at": r["fav_created_at"],
    } for r in rows]

    return {
        "favorites": favorites,
        "total": total,
        "page": page,
        "has_more": offset + len(favorites) < total,
    }
