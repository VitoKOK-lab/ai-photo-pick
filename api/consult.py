"""consult.py - 顧問選款紀錄（每次帶客人選款自動存檔）"""
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from api.auth import require_editor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

router = APIRouter(prefix="/api/consult-sessions", tags=["consult"])


def _conn():
    c = sqlite3.connect(SQLITE_PATH)
    c.row_factory = sqlite3.Row
    return c


def _init():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS consult_sessions (
            id INTEGER PRIMARY KEY,
            customer_name TEXT,
            staff_name TEXT,
            picks TEXT NOT NULL DEFAULT '[]',
            quoted TEXT NOT NULL DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


_init()


class SessionBody(BaseModel):
    customer_name: Optional[str] = None
    staff_name: Optional[str] = None
    picks: Optional[List[int]] = None
    quoted: Optional[List[int]] = None


@router.post("", status_code=201)
def create_session(body: SessionBody, user=Depends(require_editor)):
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO consult_sessions (customer_name, staff_name, picks, quoted) VALUES (?,?,?,?)",
        (
            (body.customer_name or "").strip() or None,
            body.staff_name or user.get("name", ""),
            json.dumps(body.picks or []),
            json.dumps(body.quoted or []),
        ),
    )
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return {"id": sid}


@router.patch("/{session_id}")
def update_session(session_id: int, body: SessionBody, _user=Depends(require_editor)):
    conn = _conn()
    row = conn.execute("SELECT id FROM consult_sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Session not found")
    sets, params = ["updated_at=CURRENT_TIMESTAMP"], []
    if body.customer_name is not None:
        sets.append("customer_name=?"); params.append(body.customer_name.strip() or None)
    if body.picks is not None:
        sets.append("picks=?"); params.append(json.dumps(body.picks))
    if body.quoted is not None:
        sets.append("quoted=?"); params.append(json.dumps(body.quoted))
    params.append(session_id)
    conn.execute(f"UPDATE consult_sessions SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    conn.close()
    return {"ok": True}


@router.get("")
def list_sessions(limit: int = 50, _user=Depends(require_editor)):
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM consult_sessions ORDER BY updated_at DESC LIMIT ?", (min(limit, 200),)
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        try:
            picks = json.loads(r["picks"] or "[]")
        except Exception:
            picks = []
        try:
            quoted = json.loads(r["quoted"] or "[]")
        except Exception:
            quoted = []
        out.append({
            "id": r["id"],
            "customer_name": r["customer_name"],
            "staff_name": r["staff_name"],
            "picks": picks,
            "quoted": quoted,
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        })
    return out


@router.delete("/{session_id}")
def delete_session(session_id: int, _user=Depends(require_editor)):
    conn = _conn()
    conn.execute("DELETE FROM consult_sessions WHERE id=?", (session_id,))
    conn.commit()
    conn.close()
    return {"ok": True}
