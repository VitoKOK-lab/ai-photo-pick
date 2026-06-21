"""guest_links.py - 臨時客人連結（4 小時有效）"""
import secrets
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH
from api.auth import require_editor

LINK_HOURS = 4
router = APIRouter(prefix="/api/guest-links", tags=["guest-links"])


def _conn():
    c = sqlite3.connect(SQLITE_PATH)
    c.row_factory = sqlite3.Row
    return c


class CreateLinkBody(BaseModel):
    customer_name: str
    staff_name: str = ""


# ── 員工：建立連結 ──────────────────────────────────────
@router.post("", status_code=201)
def create_link(body: CreateLinkBody, user=Depends(require_editor)):
    name = body.customer_name.strip()
    if not name:
        raise HTTPException(400, "客人姓名必填")

    conn = _conn()
    # 找或建立客人記錄
    row = conn.execute("SELECT id FROM customers WHERE name=?", (name,)).fetchone()
    if row:
        customer_id = row["id"]
    else:
        cur = conn.execute("INSERT INTO customers(name) VALUES(?)", (name,))
        conn.commit()
        customer_id = cur.lastrowid

    # 建立 session 記錄（記錄誰建立的連結，可選）
    staff_display = body.staff_name or user.get("name", "")
    session_id = None
    try:
        staff_row = conn.execute("SELECT id FROM staff WHERE name=?", (staff_display,)).fetchone()
        staff_id = staff_row["id"] if staff_row else None
        session_cur = conn.execute(
            "INSERT INTO customer_sessions(customer_id, staff_id, notes) VALUES(?,?,?)",
            (customer_id, staff_id, "建立臨時瀏覽連結")
        )
        session_id = session_cur.lastrowid
    except Exception:
        pass

    token = secrets.token_urlsafe(16)
    expires_at = (datetime.utcnow() + timedelta(hours=LINK_HOURS)).isoformat()
    created_by = staff_display or user.get("username", "")

    conn.execute(
        """INSERT INTO guest_links(token, customer_id, customer_name, created_by, expires_at)
           VALUES(?,?,?,?,?)""",
        (token, customer_id, name, created_by, expires_at)
    )
    conn.commit()
    conn.close()
    return {
        "token": token,
        "customer_name": name,
        "customer_id": customer_id,
        "session_id": session_id,
        "expires_at": expires_at,
        "hours": LINK_HOURS,
    }


# ── 員工：列出連結 ──────────────────────────────────────
@router.get("")
def list_links(_user=Depends(require_editor)):
    conn = _conn()
    rows = conn.execute(
        """SELECT gl.*,
                  (SELECT COUNT(*) FROM customer_favorites cf WHERE cf.customer_id = gl.customer_id
                   AND cf.created_at >= gl.created_at) as fav_count
           FROM guest_links gl
           ORDER BY gl.created_at DESC LIMIT 100"""
    ).fetchall()
    conn.close()
    now = datetime.utcnow().isoformat()
    result = []
    for r in rows:
        d = dict(r)
        d["expired"] = d["expires_at"] < now
        d["active"] = bool(d["is_active"]) and not d["expired"]
        result.append(d)
    return result


# ── 員工：停用連結 ──────────────────────────────────────
@router.delete("/{token}")
def deactivate_link(token: str, _user=Depends(require_editor)):
    conn = _conn()
    conn.execute("UPDATE guest_links SET is_active=0 WHERE token=?", (token,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ── 公開：驗證 token ────────────────────────────────────
@router.get("/info/{token}")
def get_link_info(token: str):
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM guest_links WHERE token=?", (token,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "連結不存在")
    r = dict(row)
    now = datetime.utcnow().isoformat()
    if not r["is_active"]:
        raise HTTPException(410, "連結已停用")
    if r["expires_at"] < now:
        raise HTTPException(410, "連結已過期")
    # 計算剩餘分鐘
    exp = datetime.fromisoformat(r["expires_at"])
    remaining_min = max(0, int((exp - datetime.utcnow()).total_seconds() / 60))
    return {
        "customer_name": r["customer_name"],
        "customer_id": r["customer_id"],
        "expires_at": r["expires_at"],
        "remaining_min": remaining_min,
    }


# ── 公開：切換收藏 ──────────────────────────────────────
@router.post("/favorite/{token}/{photo_id}")
def toggle_favorite(token: str, photo_id: int):
    conn = _conn()
    # 驗證 token
    row = conn.execute("SELECT * FROM guest_links WHERE token=?", (token,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "連結不存在")
    r = dict(row)
    now = datetime.utcnow().isoformat()
    if not r["is_active"] or r["expires_at"] < now:
        conn.close()
        raise HTTPException(410, "連結已過期或停用")

    customer_id = r["customer_id"]
    existing = conn.execute(
        "SELECT id FROM customer_favorites WHERE customer_id=? AND photo_id=?",
        (customer_id, photo_id)
    ).fetchone()

    if existing:
        conn.execute("DELETE FROM customer_favorites WHERE customer_id=? AND photo_id=?",
                     (customer_id, photo_id))
        favorited = False
    else:
        conn.execute(
            "INSERT OR IGNORE INTO customer_favorites(customer_id, photo_id) VALUES(?,?)",
            (customer_id, photo_id)
        )
        favorited = True

    conn.commit()
    fav_count = conn.execute(
        "SELECT COUNT(*) FROM customer_favorites WHERE customer_id=?", (customer_id,)
    ).fetchone()[0]
    conn.close()
    return {"favorited": favorited, "photo_id": photo_id, "total_favs": fav_count}


# ── 公開：取得收藏清單 ──────────────────────────────────
@router.get("/favorites/{token}")
def get_favorites(token: str):
    conn = _conn()
    row = conn.execute("SELECT * FROM guest_links WHERE token=?", (token,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "連結不存在")
    r = dict(row)
    now = datetime.utcnow().isoformat()
    if not r["is_active"] or r["expires_at"] < now:
        conn.close()
        raise HTTPException(410, "連結已過期")

    favs = conn.execute(
        """SELECT cf.photo_id, p.filename, p.category, p.style, p.color, p.gemstone
           FROM customer_favorites cf
           JOIN photos p ON p.id = cf.photo_id
           WHERE cf.customer_id=?
           ORDER BY cf.created_at""",
        (r["customer_id"],)
    ).fetchall()
    conn.close()
    return {"customer_name": r["customer_name"], "favorites": [dict(f) for f in favs]}
