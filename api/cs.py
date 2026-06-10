"""cs.py - 客服訂單追蹤（SHOPLINE 匯入 + 看板 + 交接班）

設計目標：不是把表格填滿，而是「沒客訴、正常出貨」。
- 每天匯入 SHOPLINE 報表 → 自動用訂單號去重，只把新單寫進看板。
- 看板只盯三種要命的單：🔴異常、🟠快逾期沒出、🟡付款超時。
- 已出貨滿 14 天的單自動從看板消失、轉入封存資料庫（仍可查）。
"""
import csv
import io
import json
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, CONFIG_DIR

router = APIRouter(prefix="/api/cs", tags=["customer-service"])

# 出貨後幾天自動封存進資料庫
ARCHIVE_AFTER_DAYS = 14
# 付款超過幾天未付款 → 視為付款超時（黃旗）
PAYMENT_OVERDUE_DAYS = 3

# 內部追蹤里程碑（看板下拉選單）
TRACK_STATUSES = [
    "待付款", "製作中", "待出貨", "寄送中", "待交貨", "售後處理中", "已結案",
]
RISK_TYPES = [
    "欠石", "主石裂待換貨", "退貨", "換貨", "客訴",
    "付款超時", "寄送問題", "缺貨待叫貨", "客戶指定款待確認圖", "其他",
]

# SHOPLINE 狀態關鍵字 → 判斷用（涵蓋實際匯出報表的用語）
_PAID_KEYWORDS = ["已付款", "已收款", "付款完成", "paid"]
_UNPAID_KEYWORDS = ["未付款", "待付款", "未收款", "待匯款", "超過付款時間",
                    "unpaid", "pending"]
# 送貨已進入「出貨後」階段（含已發貨/發貨中/已到達/已取貨），或訂單已完成
_SHIPPED_KEYWORDS = ["已出貨", "已發貨", "發貨中", "已寄出", "已送達", "已到達",
                     "已到貨", "已取貨", "配送中", "運送中",
                     "shipped", "delivered", "fulfilled", "completed"]
# 已取消／退款／退回／付款失敗 → 視為結案，不佔看板
_CANCELLED_KEYWORDS = ["已取消", "取消", "已退回", "退款", "付款失敗",
                       "cancel", "refund", "returned", "failed"]


def _conn():
    c = sqlite3.connect(SQLITE_PATH)
    c.row_factory = sqlite3.Row
    return c


def _load_mapping() -> dict:
    path = CONFIG_DIR / "shopline_mapping.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _norm(s: str) -> str:
    return (s or "").replace(" ", "").replace("　", "").strip().lower()


def _contains_any(text: str, keywords: List[str]) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in keywords)


def _today() -> str:
    return date.today().isoformat()


# ─── Models ──────────────────────────────────────────────────────────────────

class OrderUpdate(BaseModel):
    track_status: Optional[str] = None
    owner: Optional[str] = None
    next_action: Optional[str] = None
    due_date: Optional[str] = None
    is_risk: Optional[bool] = None
    risk_type: Optional[str] = None
    notes: Optional[str] = None
    archived: Optional[bool] = None


class HandoverCreate(BaseModel):
    shift_date: Optional[str] = None
    from_staff: Optional[str] = None
    to_staff: Optional[str] = None
    watch_orders: Optional[str] = None
    note: Optional[str] = None


# ─── CSV 匯入 ─────────────────────────────────────────────────────────────────

def _decode(raw: bytes) -> str:
    """SHOPLINE 匯出可能是 UTF-8(BOM) 或 Big5，依序嘗試。"""
    for enc in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _is_xls(filename: str, raw: bytes) -> bool:
    """判斷是否為舊版 Excel(.xls / OLE 複合文件)。"""
    name = (filename or "").lower()
    if name.endswith(".xls"):
        return True
    # OLE2 複合文件魔術位元組
    return raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _cell(value, datemode: int = 0, is_date: bool = False) -> str:
    """把一格（CSV 字串或 xls 原生值）轉成乾淨字串。"""
    if value is None:
        return ""
    if isinstance(value, float):
        if is_date and value > 0:
            try:
                import xlrd
                return xlrd.xldate_as_datetime(value, datemode).date().isoformat()
            except Exception:
                pass
        # 1360.0 → "1360"；保留非整數小數
        return str(int(value)) if value.is_integer() else str(value)
    s = str(value).strip()
    if is_date and s:
        # 字串日期取日期部分（"2026/05/01 10:00" → "2026/05/01"）
        return s.split(" ")[0]
    return s


def _read_table(filename: str, raw: bytes):
    """讀取 .xls 或 .csv，回傳 (fieldnames, rows, datemode)。
    rows 為 list[dict]，值維持原生型別（xls 數字保留 float）。"""
    if _is_xls(filename, raw):
        try:
            import xlrd
        except ImportError:
            raise HTTPException(
                400, "偵測到 .xls 檔，但伺服器缺少 xlrd 套件，請改用 CSV 匯出或安裝 xlrd。"
            )
        wb = xlrd.open_workbook(file_contents=raw)
        sh = wb.sheet_by_index(0)
        if sh.nrows < 1:
            return [], [], wb.datemode
        fieldnames = [str(sh.cell_value(0, c)).strip() for c in range(sh.ncols)]
        rows = [
            {fieldnames[c]: sh.cell_value(r, c) for c in range(sh.ncols)}
            for r in range(1, sh.nrows)
        ]
        return fieldnames, rows, wb.datemode
    # CSV
    reader = csv.DictReader(io.StringIO(_decode(raw)))
    return list(reader.fieldnames or []), list(reader), 0


def _resolve_columns(fieldnames: List[str], mapping: dict) -> dict:
    """把實際 CSV 標題對應到內部欄位。回傳 {內部欄位: 實際標題}。"""
    norm_to_actual = {_norm(h): h for h in (fieldnames or [])}
    resolved = {}
    for field, candidates in mapping.items():
        for cand in candidates:
            actual = norm_to_actual.get(_norm(cand))
            if actual is not None:
                resolved[field] = actual
                break
    return resolved


def _initial_track_status(payment: str, shipping: str, order_status: str) -> str:
    blob = f"{order_status} {payment} {shipping}"
    if _contains_any(blob, _CANCELLED_KEYWORDS):
        return "已結案"
    if _contains_any(shipping, _SHIPPED_KEYWORDS) or _contains_any(order_status, ["已完成", "completed"]):
        return "寄送中"
    if _contains_any(payment, _UNPAID_KEYWORDS):
        return "待付款"
    if _contains_any(payment, _PAID_KEYWORDS):
        return "製作中"
    return "待處理"


def _clean_order_no(value: str) -> str:
    """SHOPLINE 訂單號常帶 '#' 前綴，去掉以利去重比對。"""
    return (value or "").lstrip("#").strip()


def _group_orders(rows: List[dict], cols: dict, datemode: int) -> List[dict]:
    """SHOPLINE 一張訂單可橫跨多列（每件商品一列）。依訂單號合併，
    訂單層欄位取第一列，商品名稱跨列彙整成一段摘要。"""
    def cv(row, field, is_date=False):
        actual = cols.get(field)
        return _cell(row.get(actual), datemode, is_date) if actual else ""

    grouped: "dict[str, dict]" = {}
    order_seq: List[str] = []
    for row in rows:
        order_number = _clean_order_no(cv(row, "order_number"))
        if not order_number:
            continue
        if order_number not in grouped:
            grouped[order_number] = {
                "order_number": order_number,
                "customer_name": cv(row, "customer_name"),
                "phone": cv(row, "phone"),
                "order_date": cv(row, "order_date", is_date=True),
                "total": cv(row, "total"),
                "sl_order_status": cv(row, "sl_order_status"),
                "sl_payment_status": cv(row, "sl_payment_status"),
                "sl_shipping_status": cv(row, "sl_shipping_status"),
                "_items": [],
                "_raw_first": row,
            }
            order_seq.append(order_number)
        name = cv(row, "item_summary")
        if name:
            qty = cv(row, "qty")
            label = f"{name}×{qty}" if qty and qty not in ("1", "1.0") else name
            items = grouped[order_number]["_items"]
            if label not in items:
                items.append(label)

    out = []
    for on in order_seq:
        g = grouped[on]
        g["item_summary"] = "、".join(g["_items"])[:300]
        out.append(g)
    return out


@router.post("/import")
async def import_report(file: UploadFile = File(...)):
    """上傳 SHOPLINE 報表（.xls 或 .csv）：依訂單號合併多列、自動去重，
    只新增新單並更新既有單的 SHOPLINE 狀態。"""
    raw = await file.read()
    mapping = _load_mapping()

    fieldnames, rows, datemode = _read_table(file.filename or "", raw)
    cols = _resolve_columns(fieldnames, mapping)
    if "order_number" not in cols:
        raise HTTPException(
            400,
            "找不到訂單號欄位。請確認報表標題列，或把實際欄名加進 config/shopline_mapping.json。"
            f" 偵測到的標題：{fieldnames}",
        )

    orders = _group_orders(rows, cols, datemode)

    conn = _conn()
    new_count = updated_count = 0
    new_orders: List[str] = []

    for o in orders:
        order_number = o["order_number"]
        payment = o["sl_payment_status"]
        shipping = o["sl_shipping_status"]
        order_status = o["sl_order_status"]
        shipped_now = _contains_any(shipping, _SHIPPED_KEYWORDS) or \
            _contains_any(order_status, ["已完成", "completed"])

        existing = conn.execute(
            "SELECT * FROM cs_orders WHERE order_number=?", (order_number,)
        ).fetchone()

        if existing:
            # 只更新 SHOPLINE 端欄位與原始備份，不動同仁維護的追蹤欄位
            shipped_at = existing["shipped_at"]
            if shipped_now and not shipped_at:
                shipped_at = _today()
            conn.execute(
                """UPDATE cs_orders SET
                       customer_name=?, phone=?, order_date=?, total=?, item_summary=?,
                       sl_order_status=?, sl_payment_status=?, sl_shipping_status=?,
                       shipped_at=?, raw_json=?, updated_at=CURRENT_TIMESTAMP
                   WHERE order_number=?""",
                (o["customer_name"], o["phone"], o["order_date"],
                 o["total"], o["item_summary"],
                 order_status, payment, shipping, shipped_at,
                 json.dumps(o["_raw_first"], ensure_ascii=False, default=str), order_number),
            )
            updated_count += 1
        else:
            # 只追未完成：新單若一進來就已出貨/完成/取消，直接進封存（可查、不佔看板）
            closed = shipped_now or _contains_any(
                f"{order_status} {payment} {shipping}", _CANCELLED_KEYWORDS
            )
            conn.execute(
                """INSERT INTO cs_orders
                       (order_number, customer_name, phone, order_date, total, item_summary,
                        sl_order_status, sl_payment_status, sl_shipping_status,
                        track_status, shipped_at, archived, raw_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (order_number, o["customer_name"], o["phone"],
                 o["order_date"], o["total"], o["item_summary"],
                 order_status, payment, shipping,
                 _initial_track_status(payment, shipping, order_status),
                 _today() if shipped_now else None,
                 1 if closed else 0,
                 json.dumps(o["_raw_first"], ensure_ascii=False, default=str)),
            )
            new_count += 1
            if not closed:
                new_orders.append(order_number)

    conn.commit()
    archived = _run_archive(conn)
    conn.close()

    return {
        "rows_read": len(rows),
        "orders_in_file": len(orders),
        "new": new_count,
        "updated": updated_count,
        "archived": archived,
        "new_orders": new_orders[:50],
        "columns_matched": cols,
        "columns_in_file": fieldnames,
    }


def _run_archive(conn) -> int:
    """把已出貨超過 ARCHIVE_AFTER_DAYS 天的單封存（移出看板）。"""
    cutoff = (date.today() - timedelta(days=ARCHIVE_AFTER_DAYS)).isoformat()
    cur = conn.execute(
        """UPDATE cs_orders SET archived=1, updated_at=CURRENT_TIMESTAMP
           WHERE archived=0 AND shipped_at IS NOT NULL AND shipped_at <= ?""",
        (cutoff,),
    )
    conn.commit()
    return cur.rowcount


@router.post("/archive-run")
def archive_run():
    conn = _conn()
    n = _run_archive(conn)
    conn.close()
    return {"archived": n}


# ─── 看板 ────────────────────────────────────────────────────────────────────

def _decorate(row: dict) -> dict:
    """加上前端要用的計算旗標。"""
    o = dict(row)
    today = _today()
    o["overdue"] = bool(
        o.get("due_date") and o["due_date"] < today and o.get("track_status") != "已結案"
    )
    return o


@router.get("/orders")
def list_orders(
    view: str = Query("active"),   # active / risk / overdue / payment / archived / all
    status: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
):
    conn = _conn()
    where = []
    args: list = []

    if view == "archived":
        where.append("archived=1")
    elif view == "all":
        pass
    else:
        where.append("archived=0")

    if view == "risk":
        where.append("is_risk=1")
    elif view == "overdue":
        where.append("due_date IS NOT NULL AND due_date < ? AND track_status != '已結案'")
        args.append(_today())
    elif view == "payment":
        where.append(
            "track_status='待付款' AND julianday('now') - julianday(first_imported_at) > ?"
        )
        args.append(PAYMENT_OVERDUE_DAYS)

    if status:
        where.append("track_status=?")
        args.append(status)
    if owner:
        where.append("owner=?")
        args.append(owner)
    if q:
        like = f"%{q}%"
        where.append("(order_number LIKE ? OR customer_name LIKE ? OR item_summary LIKE ?)")
        args += [like, like, like]

    sql = "SELECT * FROM cs_orders"
    if where:
        sql += " WHERE " + " AND ".join(where)
    # 異常 → 逾期 → 最近更新，讓要命的單排最上面
    sql += " ORDER BY is_risk DESC, (due_date IS NOT NULL AND due_date < date('now')) DESC, updated_at DESC"

    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return [_decorate(r) for r in rows]


@router.get("/dashboard")
def dashboard():
    """交班第一眼看的數字。"""
    conn = _conn()
    today = _today()

    def count(sql, args=()):
        return conn.execute(sql, args).fetchone()[0]

    active = count("SELECT COUNT(*) FROM cs_orders WHERE archived=0")
    risk = count("SELECT COUNT(*) FROM cs_orders WHERE archived=0 AND is_risk=1")
    overdue = count(
        "SELECT COUNT(*) FROM cs_orders WHERE archived=0 AND due_date IS NOT NULL "
        "AND due_date < ? AND track_status != '已結案'", (today,)
    )
    payment_overdue = count(
        "SELECT COUNT(*) FROM cs_orders WHERE archived=0 AND track_status='待付款' "
        "AND julianday('now') - julianday(first_imported_at) > ?", (PAYMENT_OVERDUE_DAYS,)
    )
    by_status = {
        r["track_status"]: r["n"]
        for r in conn.execute(
            "SELECT track_status, COUNT(*) n FROM cs_orders WHERE archived=0 GROUP BY track_status"
        ).fetchall()
    }
    last_import = conn.execute(
        "SELECT MAX(updated_at) FROM cs_orders"
    ).fetchone()[0]
    conn.close()
    return {
        "active": active,
        "risk": risk,
        "overdue": overdue,
        "payment_overdue": payment_overdue,
        "by_status": by_status,
        "last_import": last_import,
    }


@router.get("/orders/{order_id}")
def get_order(order_id: int):
    conn = _conn()
    row = conn.execute("SELECT * FROM cs_orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Order not found")
    o = _decorate(row)
    try:
        o["raw"] = json.loads(o.get("raw_json") or "{}")
    except (ValueError, TypeError):
        o["raw"] = {}
    return o


@router.put("/orders/{order_id}")
def update_order(order_id: int, body: OrderUpdate):
    conn = _conn()
    row = conn.execute("SELECT * FROM cs_orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Order not found")

    def pick(field, current):
        val = getattr(body, field)
        return val if val is not None else current

    track_status = pick("track_status", row["track_status"])
    owner        = pick("owner", row["owner"])
    next_action  = pick("next_action", row["next_action"])
    due_date     = pick("due_date", row["due_date"])
    risk_type    = pick("risk_type", row["risk_type"])
    notes        = pick("notes", row["notes"])
    is_risk      = int(body.is_risk) if body.is_risk is not None else row["is_risk"]
    archived     = int(body.archived) if body.archived is not None else row["archived"]

    conn.execute(
        """UPDATE cs_orders SET track_status=?, owner=?, next_action=?, due_date=?,
               is_risk=?, risk_type=?, notes=?, archived=?, updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (track_status, owner, next_action, due_date, is_risk, risk_type, notes, archived, order_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM cs_orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    return _decorate(row)


@router.delete("/orders/{order_id}")
def delete_order(order_id: int):
    conn = _conn()
    cur = conn.execute("DELETE FROM cs_orders WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Order not found")
    return {"deleted": True}


@router.get("/meta")
def meta():
    """前端下拉選單用。"""
    return {"track_statuses": TRACK_STATUSES, "risk_types": RISK_TYPES}


# ─── 交接班 ──────────────────────────────────────────────────────────────────

@router.get("/handover")
def list_handovers(limit: int = Query(20)):
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM cs_handovers ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/handover", status_code=201)
def create_handover(body: HandoverCreate):
    conn = _conn()
    cur = conn.execute(
        """INSERT INTO cs_handovers(shift_date, from_staff, to_staff, watch_orders, note)
           VALUES(?,?,?,?,?)""",
        (body.shift_date or _today(), body.from_staff, body.to_staff,
         body.watch_orders, body.note),
    )
    conn.commit()
    hid = cur.lastrowid
    row = conn.execute("SELECT * FROM cs_handovers WHERE id=?", (hid,)).fetchone()
    conn.close()
    return dict(row)


@router.post("/handover/{handover_id}/ack")
def ack_handover(handover_id: int):
    conn = _conn()
    cur = conn.execute(
        "UPDATE cs_handovers SET acked=1 WHERE id=?", (handover_id,)
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Handover not found")
    return {"acked": True}
