"""locks.py - 鎖定編號 CRUD"""
import secrets
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

router = APIRouter(prefix="/api/locks", tags=["locks"])

class LockEntry(BaseModel):
    photo_id: int
    lock_number: int  # 1-9

class LockCreate(BaseModel):
    session_id: str
    photos: List[LockEntry]
    expires_days: int = 30

def _conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@router.post("")
def create_lock(body: LockCreate):
    if len(body.photos) > 9 or len(body.photos) < 1:
        raise HTTPException(status_code=400, detail="Photos count must be 1-9")
    numbers = [p.lock_number for p in body.photos]
    if len(set(numbers)) != len(numbers):
        raise HTTPException(status_code=400, detail="Duplicate lock_number")
    if any(n < 1 or n > 9 for n in numbers):
        raise HTTPException(status_code=400, detail="lock_number must be 1-9")

    token = secrets.token_urlsafe(16)
    expires_at = datetime.now() + timedelta(days=body.expires_days)

    conn = _conn()
    cur = conn.cursor()

    # 清掉這個 session 既有的 lock
    cur.execute("DELETE FROM locks WHERE session_id = ?", (body.session_id,))

    inserted_ids = []
    for entry in body.photos:
        cur.execute(
            """INSERT INTO locks (session_id, photo_id, lock_number, customer_share_token, expires_at)
               VALUES (?, ?, ?, ?, ?)""",
            (body.session_id, entry.photo_id, entry.lock_number, token, expires_at.isoformat())
        )
        inserted_ids.append(cur.lastrowid)
        cur.execute(
            "UPDATE photos SET lock_count = lock_count + 1 WHERE id = ?",
            (entry.photo_id,)
        )

    conn.commit()
    conn.close()

    return {
        "lock_ids": inserted_ids,
        "customer_share_token": token,
        "expires_at": expires_at.isoformat(),
        "customer_url": f"/share/{token}",  # Phase 4 才實作
    }

@router.delete("")
def delete_lock(session_id: str = Query(...)):
    conn = _conn()
    cur = conn.cursor()

    cur.execute("SELECT photo_id FROM locks WHERE session_id = ?", (session_id,))
    photo_ids = [r[0] for r in cur.fetchall()]

    cur.execute("DELETE FROM locks WHERE session_id = ?", (session_id,))
    deleted = cur.rowcount

    for pid in photo_ids:
        cur.execute(
            "UPDATE photos SET lock_count = MAX(0, lock_count - 1) WHERE id = ?",
            (pid,)
        )

    conn.commit()
    conn.close()
    return {"deleted_count": deleted}

@router.get("/current")
def get_current_lock(session_id: str = Query(...)):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT l.lock_number, l.customer_share_token, l.expires_at, p.*
        FROM locks l
        JOIN photos p ON p.id = l.photo_id
        WHERE l.session_id = ?
        ORDER BY l.lock_number ASC
        """,
        (session_id,)
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"locks": [], "customer_share_token": None}

    locks = [{
        "lock_number": r["lock_number"],
        "photo_id": r["id"],
        "filename": r["filename"],
        "micro_url": f"/static/micro/{r['filename']}",
        "thumb_url": f"/static/thumb/{r['filename']}",
        "full_url": f"/static/full/{r['filename']}",
        "color": r["color"],
        "category": r["category"],
        "gemstone": r["gemstone"],
        "price_band": r["price_band"],
    } for r in rows]

    return {
        "locks": locks,
        "customer_share_token": rows[0]["customer_share_token"],
        "expires_at": rows[0]["expires_at"],
    }
