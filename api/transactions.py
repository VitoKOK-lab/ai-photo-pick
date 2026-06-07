"""transactions.py - 近期成交記錄"""
import sqlite3
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _conn():
    c = sqlite3.connect(SQLITE_PATH)
    c.row_factory = sqlite3.Row
    return c


class TransactionCreate(BaseModel):
    item_name: str
    category: Optional[str] = None
    material: Optional[str] = None
    gemstone: Optional[str] = None
    stone_spec: Optional[str] = None
    metal_weight: Optional[float] = None
    price: int
    sale_date: Optional[str] = None
    notes: Optional[str] = None
    client_name: Optional[str] = None
    photo_id: Optional[int] = None


class TransactionUpdate(BaseModel):
    item_name: Optional[str] = None
    category: Optional[str] = None
    material: Optional[str] = None
    gemstone: Optional[str] = None
    stone_spec: Optional[str] = None
    metal_weight: Optional[float] = None
    price: Optional[int] = None
    sale_date: Optional[str] = None
    notes: Optional[str] = None
    client_name: Optional[str] = None


@router.get("")
def list_transactions():
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM transactions ORDER BY sale_date DESC, created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/benchmarks")
def material_benchmarks():
    """各材質平均成交價（用於近期成交頁頂部 benchmark bar）"""
    conn = _conn()
    rows = conn.execute(
        """SELECT material,
                  COUNT(*) as count,
                  CAST(AVG(price) AS INTEGER) as avg_price,
                  MIN(price) as min_price,
                  MAX(price) as max_price
           FROM transactions
           WHERE material IS NOT NULL
           GROUP BY material
           ORDER BY avg_price DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_transaction(body: TransactionCreate):
    if body.price <= 0:
        raise HTTPException(400, "price 需為正整數")
    conn = _conn()
    cur = conn.execute(
        """INSERT INTO transactions
           (item_name, category, material, gemstone, stone_spec,
            metal_weight, price, sale_date, notes, client_name, photo_id)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (body.item_name, body.category, body.material, body.gemstone,
         body.stone_spec, body.metal_weight, body.price,
         body.sale_date, body.notes, body.client_name, body.photo_id)
    )
    conn.commit()
    tid = cur.lastrowid
    row = conn.execute("SELECT * FROM transactions WHERE id=?", (tid,)).fetchone()
    conn.close()
    return dict(row)


@router.put("/{tx_id}")
def update_transaction(tx_id: int, body: TransactionUpdate):
    conn = _conn()
    row = conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Transaction not found")
    r = dict(row)
    conn.execute(
        """UPDATE transactions SET
           item_name=?, category=?, material=?, gemstone=?, stone_spec=?,
           metal_weight=?, price=?, sale_date=?, notes=?, client_name=?,
           updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (
            body.item_name    if body.item_name    is not None else r["item_name"],
            body.category     if body.category     is not None else r["category"],
            body.material     if body.material     is not None else r["material"],
            body.gemstone     if body.gemstone     is not None else r["gemstone"],
            body.stone_spec   if body.stone_spec   is not None else r["stone_spec"],
            body.metal_weight if body.metal_weight is not None else r["metal_weight"],
            body.price        if body.price        is not None else r["price"],
            body.sale_date    if body.sale_date    is not None else r["sale_date"],
            body.notes        if body.notes        is not None else r["notes"],
            body.client_name  if body.client_name  is not None else r["client_name"],
            tx_id,
        )
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
    conn.close()
    return dict(updated)


@router.delete("/{tx_id}")
def delete_transaction(tx_id: int):
    conn = _conn()
    cur = conn.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Transaction not found")
    return {"deleted": True}
