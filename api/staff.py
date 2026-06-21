"""staff.py - 客服人員管理"""
import sqlite3
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from api.auth import require_admin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

router = APIRouter(prefix="/api/staff", tags=["staff"])


def _conn():
    c = sqlite3.connect(SQLITE_PATH)
    c.row_factory = sqlite3.Row
    return c


class StaffBody(BaseModel):
    name: str


@router.get("")
def list_staff():
    conn = _conn()
    rows = conn.execute("SELECT * FROM staff ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_staff(body: StaffBody, _user=Depends(require_admin)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "name required")
    conn = _conn()
    try:
        cur = conn.execute("INSERT INTO staff(name) VALUES(?)", (name,))
        conn.commit()
        sid = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(409, "名稱已存在")
    conn.close()
    return {"id": sid, "name": name}


@router.put("/{staff_id}")
def update_staff(staff_id: int, body: StaffBody, _user=Depends(require_admin)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "name required")
    conn = _conn()
    cur = conn.execute("UPDATE staff SET name=? WHERE id=?", (name, staff_id))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Staff not found")
    return {"id": staff_id, "name": name}


@router.delete("/{staff_id}")
def delete_staff(staff_id: int, _user=Depends(require_admin)):
    conn = _conn()
    cur = conn.execute("DELETE FROM staff WHERE id=?", (staff_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Staff not found")
    return {"deleted": True}
