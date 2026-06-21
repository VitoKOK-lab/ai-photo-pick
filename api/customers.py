"""customers.py - 客戶偏好庫 CRM"""
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from api.auth import require_editor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

router = APIRouter(prefix="/api/customers", tags=["customers"])


def _conn():
    c = sqlite3.connect(SQLITE_PATH)
    c.row_factory = sqlite3.Row
    return c


# ─── Models ──────────────────────────────────────────────────────────────────

class CustomerCreate(BaseModel):
    name: str
    line_id: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    line_id: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class DiscoverySession(BaseModel):
    staff_id: Optional[int] = None
    liked_photo_ids: List[int] = []
    tags: List[str] = []
    line_id: Optional[str] = None
    notes: Optional[str] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_customer(conn, customer_id: int):
    row = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Customer not found")
    c = dict(row)
    c["tags"] = [r["tag"] for r in conn.execute(
        "SELECT tag FROM customer_tags WHERE customer_id=? ORDER BY id", (customer_id,)
    ).fetchall()]
    favs = conn.execute(
        """SELECT cf.photo_id, cf.note, cf.created_at,
                  p.filename, p.category, p.color, p.material, p.gemstone
           FROM customer_favorites cf
           LEFT JOIN photos p ON p.id = cf.photo_id
           WHERE cf.customer_id = ?
           ORDER BY cf.created_at DESC""",
        (customer_id,)
    ).fetchall()
    c["favorites"] = [dict(f) for f in favs]
    return c


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("")
def list_customers(q: Optional[str] = Query(None)):
    conn = _conn()
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            """SELECT DISTINCT c.* FROM customers c
               LEFT JOIN customer_tags ct ON ct.customer_id = c.id
               WHERE c.name LIKE ? OR c.line_id LIKE ? OR ct.tag LIKE ?
               ORDER BY c.updated_at DESC""",
            (like, like, like)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM customers ORDER BY updated_at DESC"
        ).fetchall()

    result = []
    for row in rows:
        c = dict(row)
        c["tags"] = [r["tag"] for r in conn.execute(
            "SELECT tag FROM customer_tags WHERE customer_id=? ORDER BY id", (c["id"],)
        ).fetchall()]
        # last favorite photo for preview
        fav = conn.execute(
            """SELECT p.filename FROM customer_favorites cf
               JOIN photos p ON p.id = cf.photo_id
               WHERE cf.customer_id = ? ORDER BY cf.created_at DESC LIMIT 1""",
            (c["id"],)
        ).fetchone()
        c["last_fav_filename"] = fav["filename"] if fav else None
        c["fav_count"] = conn.execute(
            "SELECT COUNT(*) FROM customer_favorites WHERE customer_id=?", (c["id"],)
        ).fetchone()[0]
        result.append(c)
    conn.close()
    return result


@router.post("", status_code=201)
def create_customer(body: CustomerCreate, _user=Depends(require_editor)):
    if not body.name.strip():
        raise HTTPException(400, "name required")
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO customers(name, line_id, phone, notes) VALUES(?,?,?,?)",
        (body.name.strip(), body.line_id, body.phone, body.notes)
    )
    conn.commit()
    cid = cur.lastrowid
    c = dict(conn.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone())
    c["tags"] = []
    c["favorites"] = []
    conn.close()
    return c


@router.get("/{customer_id}")
def get_customer(customer_id: int):
    conn = _conn()
    c = _get_customer(conn, customer_id)
    conn.close()
    return c


@router.put("/{customer_id}")
def update_customer(customer_id: int, body: CustomerUpdate, _user=Depends(require_editor)):
    conn = _conn()
    row = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Customer not found")
    name    = body.name.strip()    if body.name    is not None else row["name"]
    line_id = body.line_id         if body.line_id is not None else row["line_id"]
    phone   = body.phone           if body.phone   is not None else row["phone"]
    notes   = body.notes           if body.notes   is not None else row["notes"]
    conn.execute(
        """UPDATE customers SET name=?, line_id=?, phone=?, notes=?,
           updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (name, line_id, phone, notes, customer_id)
    )
    conn.commit()
    c = _get_customer(conn, customer_id)
    conn.close()
    return c


@router.post("/{customer_id}/sessions")
def save_discovery_session(customer_id: int, body: DiscoverySession, _user=Depends(require_editor)):
    """儲存一次偏好探索結果：喜愛照片 + 偏好標籤"""
    conn = _conn()
    row = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Customer not found")

    # update line_id if provided
    if body.line_id and not row["line_id"]:
        conn.execute("UPDATE customers SET line_id=? WHERE id=?", (body.line_id, customer_id))

    # create session record
    cur = conn.execute(
        "INSERT INTO customer_sessions(customer_id, staff_id, notes) VALUES(?,?,?)",
        (customer_id, body.staff_id, body.notes)
    )
    session_id = cur.lastrowid

    # save liked photos
    for pid in body.liked_photo_ids:
        conn.execute(
            """INSERT OR IGNORE INTO customer_favorites(customer_id, photo_id, session_id)
               VALUES(?,?,?)""",
            (customer_id, pid, session_id)
        )

    # merge tags (deduplicate)
    for tag in body.tags:
        tag = tag.strip()
        if tag:
            conn.execute(
                "INSERT OR IGNORE INTO customer_tags(customer_id, tag) VALUES(?,?)",
                (customer_id, tag)
            )

    # increment session count
    conn.execute(
        """UPDATE customers SET session_count=session_count+1,
           updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (customer_id,)
    )
    conn.commit()
    c = _get_customer(conn, customer_id)
    conn.close()
    return {"session_id": session_id, "customer": c}


@router.get("/{customer_id}/sessions")
def list_sessions(customer_id: int):
    conn = _conn()
    rows = conn.execute(
        """SELECT cs.*, s.name as staff_name FROM customer_sessions cs
           LEFT JOIN staff s ON s.id = cs.staff_id
           WHERE cs.customer_id = ? ORDER BY cs.created_at DESC""",
        (customer_id,)
    ).fetchall()
    sessions = []
    for row in rows:
        s = dict(row)
        s["favorites"] = [dict(f) for f in conn.execute(
            """SELECT cf.photo_id, cf.note, p.filename, p.category, p.color, p.material
               FROM customer_favorites cf
               LEFT JOIN photos p ON p.id = cf.photo_id
               WHERE cf.session_id = ?""",
            (s["id"],)
        ).fetchall()]
        sessions.append(s)
    conn.close()
    return sessions


@router.delete("/{customer_id}/tags/{tag}")
def remove_tag(customer_id: int, tag: str, _user=Depends(require_editor)):
    conn = _conn()
    conn.execute(
        "DELETE FROM customer_tags WHERE customer_id=? AND tag=?", (customer_id, tag)
    )
    conn.commit()
    conn.close()
    return {"deleted": True}


@router.delete("/{customer_id}")
def delete_customer(customer_id: int, _user=Depends(require_editor)):
    conn = _conn()
    cur = conn.execute("DELETE FROM customers WHERE id=?", (customer_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Customer not found")
    return {"deleted": True}


# ─── Insights for Stats page ──────────────────────────────────────────────────

@router.get("/insights/preferences")
def preference_insights():
    """全部客戶偏好彙整 — 用於統計頁"""
    conn = _conn()
    rows = conn.execute(
        """SELECT p.category, p.gemstone, p.material, p.color,
                  COUNT(DISTINCT cf.customer_id) as customer_count,
                  COUNT(*) as fav_count
           FROM customer_favorites cf
           JOIN photos p ON p.id = cf.photo_id
           GROUP BY p.category, p.gemstone, p.material, p.color
           ORDER BY fav_count DESC LIMIT 50"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
