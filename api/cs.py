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
from config.settings import (
    SQLITE_PATH, CONFIG_DIR, SHOPLINE_HANDLE, SHOPLINE_ORDER_URL,
)

router = APIRouter(prefix="/api/cs", tags=["customer-service"])

# 付款超過幾天未付款 → 視為付款超時（黃旗）
PAYMENT_OVERDUE_DAYS = 3
# 出貨期限剩幾天內 → 視為「快到期」（橙旗）
DUE_SOON_DAYS = 3


def _load_workflow() -> dict:
    """讀取 config/cs_workflow.json（流程關卡、品項類型、SLA、歸檔天數）。"""
    path = CONFIG_DIR / "cs_workflow.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


WORKFLOW = _load_workflow()
RISK_TYPES = WORKFLOW.get("risk_types", ["其他"])
RETURN_STATUSES = WORKFLOW.get("return_statuses", ["待簽核", "已核准", "已駁回"])
PRODUCT_TYPES = WORKFLOW.get("product_types", {"規格": {"sla_days": 14}})
DEFAULT_PRODUCT_TYPE = WORKFLOW.get("default_product_type", "規格")
# 規格與訂製共用同一套進度關卡（依內部追蹤總表）
TRACK_STATUSES = WORKFLOW.get("stages", ["下單待入帳", "已完成結案"])
# 每關「員工該做什麼」一句話提示（今日待辦用）
STAGE_ACTIONS = WORKFLOW.get("stage_actions", {})
# 客戶追蹤通知天數（從下單日起算）
CUSTOMER_NOTIFY_DAYS = WORKFLOW.get("customer_notify_days", [7, 14, 21])
# 已完成後幾天自動封存（退換貨期）
ARCHIVE_AFTER_COMPLETE_DAYS = int(WORKFLOW.get("archive_after_complete_days", 7))


def _type_cfg(product_type: str) -> dict:
    return PRODUCT_TYPES.get(product_type) or PRODUCT_TYPES.get(DEFAULT_PRODUCT_TYPE, {})


def _stages_for(product_type: str = None) -> list:
    """規格/訂製共用同一套關卡。"""
    return TRACK_STATUSES


def _detect_product_type(item_summary: str) -> str:
    """依商品名稱關鍵字判斷規格/訂製，預設規格。"""
    text = item_summary or ""
    for ptype, cfg in PRODUCT_TYPES.items():
        for kw in cfg.get("keywords", []):
            if kw and kw in text:
                return ptype
    return DEFAULT_PRODUCT_TYPE


def _sla_days(product_type: str) -> int:
    return int(_type_cfg(product_type).get("sla_days", 14))

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
# 已完成（送達）→ 退換貨期由此起算
_COMPLETED_KEYWORDS = ["已完成", "已送達", "已到達", "已到貨", "已取貨",
                       "completed", "delivered"]

_MIGRATED = False
# 後加的欄位（讓既有資料庫也能無痛升級）
_EXTRA_COLUMNS = {
    "product_type": "TEXT DEFAULT '規格'",
    "sla_days": "INTEGER",
    "due_ship_date": "TEXT",
    "last_handler": "TEXT",
    "customer_id": "TEXT",
    "completed_at": "TEXT",
    "return_status": "TEXT",
    "return_reason": "TEXT",
    "return_signed_by": "TEXT",
    "return_signed_at": "TEXT",
    # 內部追蹤總表欄位
    "customer_source": "TEXT", "sales_rep": "TEXT", "payment_method": "TEXT",
    "gold_work_date": "TEXT", "accounting_by": "TEXT", "accounting_at": "TEXT",
    "notify_7d_at": "TEXT", "notify_7d_by": "TEXT",
    "notify_14d_at": "TEXT", "notify_14d_by": "TEXT",
    "notify_21d_at": "TEXT", "notify_21d_by": "TEXT",
    "order_goods_by": "TEXT", "order_goods_at": "TEXT",
    "stone_source": "TEXT", "main_stone": "TEXT", "main_stone_photo": "TEXT",
    "custom_style_photo": "TEXT", "weight_ct": "TEXT", "dimensions": "TEXT",
    "material": "TEXT", "side_stone": "TEXT", "plating": "TEXT",
    "item_kind": "TEXT", "unit": "TEXT", "ring_size": "TEXT",
    "chase_by": "TEXT", "factory": "TEXT", "model3d_img": "TEXT", "model3d_confirmed": "TEXT",
    "arrival_date": "TEXT", "arrival_photo": "TEXT", "product_video": "TEXT",
    "ship_from": "TEXT", "warranty_card": "TEXT", "ecard_link": "TEXT",
    "ship_to_tw_at": "TEXT", "ship_tracking": "TEXT", "arrive_tw_at": "TEXT", "tw_receiver": "TEXT",
    "ship_to_customer_at": "TEXT", "ship_by": "TEXT", "review_ecard": "TEXT", "order_closed": "TEXT",
    "aftersale": "TEXT", "aftersale_notes": "TEXT",
}


def _migrate(c):
    """既有資料庫補上新欄位與時間軸表（新庫由 schema 直接建好，這裡只是保險）。"""
    cols = {r[1] for r in c.execute("PRAGMA table_info(cs_orders)").fetchall()}
    for name, decl in _EXTRA_COLUMNS.items():
        if name not in cols:
            c.execute(f"ALTER TABLE cs_orders ADD COLUMN {name} {decl}")
    c.execute("""CREATE TABLE IF NOT EXISTS cs_order_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        occurred_at TEXT, actor TEXT, actor_type TEXT DEFAULT 'staff',
        kind TEXT DEFAULT 'note', content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cs_events_order ON cs_order_events(order_id)")
    c.execute("""CREATE TABLE IF NOT EXISTS cs_import_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        source TEXT DEFAULT 'manual', filename TEXT,
        rows_read INTEGER DEFAULT 0, orders_in_file INTEGER DEFAULT 0,
        new_count INTEGER DEFAULT 0, updated_count INTEGER DEFAULT 0,
        archived_count INTEGER DEFAULT 0, status TEXT DEFAULT 'ok', message TEXT)""")
    c.commit()


def _conn():
    global _MIGRATED
    c = sqlite3.connect(SQLITE_PATH)
    c.row_factory = sqlite3.Row
    if not _MIGRATED:
        try:
            _migrate(c)
        except sqlite3.OperationalError:
            pass  # 資料表尚未建立（首次初始化前），交給 schema
        _MIGRATED = True
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


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _add_days(iso_date: str, days: int) -> str:
    """ISO 日期 + 天數；解析失敗回空字串。"""
    try:
        return (date.fromisoformat((iso_date or "")[:10]) + timedelta(days=days)).isoformat()
    except ValueError:
        return ""


# ─── Models ──────────────────────────────────────────────────────────────────

class OrderUpdate(BaseModel):
    track_status: Optional[str] = None
    product_type: Optional[str] = None
    owner: Optional[str] = None
    next_action: Optional[str] = None
    due_date: Optional[str] = None
    is_risk: Optional[bool] = None
    risk_type: Optional[str] = None
    notes: Optional[str] = None
    archived: Optional[bool] = None
    handler: Optional[str] = None       # 操作者（誰在動這張單）— 用於旅程記錄


class EventCreate(BaseModel):
    content: str
    actor: Optional[str] = None         # 員工名 或 客人名
    actor_type: Optional[str] = "staff"  # staff / customer
    occurred_at: Optional[str] = None   # 預設現在


class ReturnAction(BaseModel):
    action: str                         # request 申請 / approve 核准 / reject 駁回 / cancel 取消
    by: Optional[str] = None            # 操作/簽核人
    reason: Optional[str] = None        # 退貨原因（申請時）


class NotifyDone(BaseModel):
    day: int                            # 7 / 14 / 21（客戶追蹤通知里程碑）
    by: Optional[str] = None            # 通知的客服


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


def _cell(value, datemode: int = 0, is_date: bool = False, is_datetime: bool = False) -> str:
    """把一格（CSV 字串或 xls 原生值）轉成乾淨字串。
    is_date → 取日期；is_datetime → 取『年月日 時:分』（時間軸用）。"""
    if value is None:
        return ""
    if isinstance(value, float):
        if (is_date or is_datetime) and value > 0:
            try:
                import xlrd
                dt = xlrd.xldate_as_datetime(value, datemode)
                return dt.strftime("%Y-%m-%d %H:%M") if is_datetime else dt.date().isoformat()
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


def _initial_track_status(payment: str, shipping: str, order_status: str,
                          product_type: str = None) -> str:
    """依 SHOPLINE 狀態，落到內部流程的初始關卡。
    新單一律從『下單待入帳』起（台灣會計確認入帳是第一關，員工手動推進）。
    已出貨/完成的歷史單則落到對應後段，避免回到最前面。"""
    if _contains_any(order_status, ["已完成", "completed"]) or \
       _contains_any(shipping, _COMPLETED_KEYWORDS):
        return "已完成結案"
    if _contains_any(shipping, ["已發貨", "發貨中", "已出貨", "已寄出", "配送中", "運送中", "shipped"]):
        return "出貨回台灣(在途)"
    return TRACK_STATUSES[0] if TRACK_STATUSES else "下單待入帳"


def _clean_order_no(value: str) -> str:
    """SHOPLINE 訂單號常帶 '#' 前綴，去掉以利去重比對。"""
    return (value or "").lstrip("#").strip()


def _log_event(conn, order_id, actor_type, actor, kind, content, occurred_at=None):
    """寫一筆購物旅程事件。"""
    conn.execute(
        """INSERT INTO cs_order_events(order_id, occurred_at, actor, actor_type, kind, content)
           VALUES(?,?,?,?,?,?)""",
        (order_id, occurred_at or _now(), actor, actor_type, kind, content),
    )


def _seed_timeline(conn, order_id, o):
    """新單匯入時，依 SHOPLINE 時間戳補上系統事件（下單/付款/發貨/送達）。"""
    seeds = [
        (o.get("_ordered_at") or o.get("order_date"), "客人下單"),
        (o.get("_paid_at"), "完成付款"),
        (o.get("_ship_at"), "大陸發貨"),
        (o.get("_arrive_at"), "貨運送達 / SHOPLINE 完成"),
    ]
    for when, text in seeds:
        if when:
            _log_event(conn, order_id, "system", "系統", "system", text, when)


def _group_orders(rows: List[dict], cols: dict, datemode: int) -> List[dict]:
    """SHOPLINE 一張訂單可橫跨多列（每件商品一列）。依訂單號合併，
    訂單層欄位取第一列，商品名稱跨列彙整成一段摘要。"""
    def cv(row, field, is_date=False, is_datetime=False):
        actual = cols.get(field)
        return _cell(row.get(actual), datemode, is_date, is_datetime) if actual else ""

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
                "customer_id": cv(row, "customer_id"),
                "customer_source": cv(row, "customer_source"),
                "sales_rep": cv(row, "sales_rep"),
                "payment_method": cv(row, "payment_method"),
                "order_date": cv(row, "order_date", is_date=True),
                "total": cv(row, "total"),
                "sl_order_status": cv(row, "sl_order_status"),
                "sl_payment_status": cv(row, "sl_payment_status"),
                "sl_shipping_status": cv(row, "sl_shipping_status"),
                # 給時間軸用的原始時間戳
                "_ordered_at": cv(row, "order_date", is_datetime=True),
                "_paid_at": cv(row, "paid_at", is_datetime=True),
                "_ship_at": cv(row, "ship_at", is_datetime=True),
                "_arrive_at": cv(row, "arrive_at", is_datetime=True),
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


def _log_import(conn, source, filename, result, status, message=""):
    """寫一筆匯入記錄（成功或失敗都記），供「自動匯入」頁顯示。"""
    conn.execute(
        """INSERT INTO cs_import_log
               (source, filename, rows_read, orders_in_file,
                new_count, updated_count, archived_count, status, message)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (source, filename, result.get("rows_read", 0), result.get("orders_in_file", 0),
         result.get("new", 0), result.get("updated", 0), result.get("archived", 0),
         status, message[:500]),
    )
    conn.commit()


@router.post("/import")
async def import_report(file: UploadFile = File(...), source: str = Query("manual")):
    """上傳 SHOPLINE 報表（.xls 或 .csv）：依訂單號合併多列、自動去重，
    只新增新單並更新既有單的 SHOPLINE 狀態。source=auto 為排程自動匯入。"""
    raw = await file.read()
    fname = file.filename or ""
    mapping = _load_mapping()

    fieldnames, rows, datemode = _read_table(fname, raw)
    cols = _resolve_columns(fieldnames, mapping)
    if "order_number" not in cols:
        c = _conn()
        _log_import(c, source, fname, {}, "error", f"找不到訂單號欄位；偵測到標題：{fieldnames}")
        c.close()
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
        completed_now = _contains_any(order_status, ["已完成", "completed"]) or \
            _contains_any(shipping, _COMPLETED_KEYWORDS)

        existing = conn.execute(
            "SELECT * FROM cs_orders WHERE order_number=?", (order_number,)
        ).fetchone()

        if existing:
            # 只更新 SHOPLINE 端欄位與原始備份，不動同仁維護的追蹤欄位
            shipped_at = existing["shipped_at"]
            if shipped_now and not shipped_at:
                shipped_at = _today()
                _log_event(conn, existing["id"], "system", "系統", "stage",
                           "SHOPLINE 顯示已出貨", _now())
            completed_at = existing["completed_at"]
            if completed_now and not completed_at:
                completed_at = _today()
                _log_event(conn, existing["id"], "system", "系統", "stage",
                           "SHOPLINE 顯示已完成（送達），退換貨期起算", _now())
            conn.execute(
                """UPDATE cs_orders SET
                       customer_name=?, phone=?, customer_id=?,
                       customer_source=?, sales_rep=?, payment_method=?,
                       order_date=?, total=?, item_summary=?,
                       sl_order_status=?, sl_payment_status=?, sl_shipping_status=?,
                       shipped_at=?, completed_at=?, raw_json=?, updated_at=CURRENT_TIMESTAMP
                   WHERE order_number=?""",
                (o["customer_name"], o["phone"], o["customer_id"],
                 o.get("customer_source"), o.get("sales_rep"), o.get("payment_method"),
                 o["order_date"], o["total"], o["item_summary"],
                 order_status, payment, shipping, shipped_at, completed_at,
                 json.dumps(o["_raw_first"], ensure_ascii=False, default=str), order_number),
            )
            updated_count += 1
        else:
            # 只追未完成：新單若一進來就已出貨/完成/取消，直接進封存（可查、不佔看板）
            closed = shipped_now or _contains_any(
                f"{order_status} {payment} {shipping}", _CANCELLED_KEYWORDS
            )
            ptype = _detect_product_type(o["item_summary"])
            sla = _sla_days(ptype)
            due_ship = _add_days(o["order_date"], sla)
            cur = conn.execute(
                """INSERT INTO cs_orders
                       (order_number, customer_name, phone, customer_id,
                        customer_source, sales_rep, payment_method,
                        order_date, total, item_summary,
                        sl_order_status, sl_payment_status, sl_shipping_status,
                        product_type, sla_days, due_ship_date,
                        track_status, shipped_at, completed_at, archived, raw_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (order_number, o["customer_name"], o["phone"], o["customer_id"],
                 o.get("customer_source"), o.get("sales_rep"), o.get("payment_method"),
                 o["order_date"], o["total"], o["item_summary"],
                 order_status, payment, shipping,
                 ptype, sla, due_ship,
                 _initial_track_status(payment, shipping, order_status, ptype),
                 _today() if shipped_now else None,
                 _today() if completed_now else None,
                 1 if closed else 0,
                 json.dumps(o["_raw_first"], ensure_ascii=False, default=str)),
            )
            _seed_timeline(conn, cur.lastrowid, o)
            new_count += 1
            if not closed:
                new_orders.append(order_number)

    conn.commit()
    archived = _run_archive(conn)
    result = {
        "rows_read": len(rows),
        "orders_in_file": len(orders),
        "new": new_count,
        "updated": updated_count,
        "archived": archived,
        "new_orders": new_orders[:50],
        "columns_matched": cols,
        "columns_in_file": fieldnames,
    }
    _log_import(conn, source, fname, result, "ok")
    conn.close()
    return result


def _run_archive(conn) -> int:
    """已完成（送達）滿退換貨期天數 → 自動封存（移出看板，仍可查）。
    舊資料若只有 shipped_at 沒有 completed_at，退而求其次用 shipped_at。"""
    cutoff = (date.today() - timedelta(days=ARCHIVE_AFTER_COMPLETE_DAYS)).isoformat()
    cur = conn.execute(
        """UPDATE cs_orders SET archived=1, updated_at=CURRENT_TIMESTAMP
           WHERE archived=0
             AND COALESCE(completed_at, shipped_at) IS NOT NULL
             AND COALESCE(completed_at, shipped_at) <= ?""",
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


@router.get("/import-log")
def import_log(limit: int = Query(20)):
    """最近的匯入記錄（自動/手動），供「自動匯入」頁顯示狀態與歷史。"""
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM cs_import_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── 今日待辦（員工端核心：知道現在該做什麼、不漏單→不被客訴）────────────────

def _due_notify(row) -> Optional[int]:
    """回傳『該通知客人』的最大里程碑天數（下單日+N<=今天 且尚未通知），無則 None。"""
    od = (row["order_date"] or "")[:10]
    try:
        d0 = date.fromisoformat(od)
    except ValueError:
        return None
    keys = row.keys()
    # 取「已到期里程碑中的最大者」；它若已通知 → 視為已盡到通知義務（較早的不再追）
    due_ns = [n for n in CUSTOMER_NOTIFY_DAYS if d0 + timedelta(days=n) <= date.today()]
    if not due_ns:
        return None
    n = max(due_ns)
    col = f"notify_{n}d_at"
    done = row[col] if col in keys else None
    return None if done else n


@router.get("/worklist")
def worklist(owner: Optional[str] = Query(None)):
    """今日待辦：系統排好順序，每筆寫『為什麼 + 該做什麼』。
    🔴 急(可能被客訴) 排最前：異常 / 出貨逾期 / 該通知客人(7/14/21)。
    🟠 今天該推進：快到期或一般待推進。"""
    conn = _conn()
    where = ["archived=0", "track_status != '已完成結案'"]
    args: list = []
    if owner:
        where.append("owner=?")
        args.append(owner)
    rows = conn.execute(
        f"SELECT * FROM cs_orders WHERE {' AND '.join(where)} "
        "ORDER BY (due_ship_date IS NULL) ASC, due_ship_date ASC", args
    ).fetchall()
    conn.close()

    urgent, today_list = [], []
    for r in rows:
        o = _decorate(r)
        nd = _due_notify(r)
        bucket, reason = "today", None
        if r["is_risk"]:
            bucket, reason = "urgent", f"🔴 異常：{r['risk_type'] or '待處理'}"
        elif o["ship_overdue"]:
            bucket, reason = "urgent", f"出貨已逾期 {abs(o['days_left'])} 天"
        elif nd:
            bucket, reason = "urgent", f"下單滿 {nd} 天，該主動通知客人進度"
        elif o["due_soon"]:
            bucket, reason = "today", f"出貨期僅剩 {o['days_left']} 天"
        item = {
            "id": r["id"], "order_number": r["order_number"],
            "customer_name": r["customer_name"], "product_type": r["product_type"],
            "track_status": r["track_status"], "due_ship_date": r["due_ship_date"],
            "days_left": o["days_left"], "is_risk": bool(r["is_risk"]),
            "notify_due": nd, "reason": reason,
            "action": STAGE_ACTIONS.get(r["track_status"], ""),
            "last_handler": r["last_handler"],
        }
        (urgent if bucket == "urgent" else today_list).append(item)
    return {"urgent": urgent, "today": today_list,
            "counts": {"urgent": len(urgent), "today": len(today_list)}}


@router.post("/orders/{order_id}/notify")
def notify_customer_done(order_id: int, body: NotifyDone):
    """標記『已主動通知客人進度』（7/14/21 里程碑），記人+時間並寫進購物旅程。"""
    if body.day not in CUSTOMER_NOTIFY_DAYS:
        raise HTTPException(400, f"day 需為 {CUSTOMER_NOTIFY_DAYS} 之一")
    conn = _conn()
    row = conn.execute("SELECT id FROM cs_orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Order not found")
    who = (body.by or "").strip() or "員工"
    conn.execute(
        f"UPDATE cs_orders SET notify_{body.day}d_at=?, notify_{body.day}d_by=?, "
        "last_handler=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (_now(), who, who, order_id),
    )
    _log_event(conn, order_id, "staff", who, "note", f"已主動通知客人進度（下單滿 {body.day} 天）")
    conn.commit()
    out = _decorate(conn.execute("SELECT * FROM cs_orders WHERE id=?", (order_id,)).fetchone())
    out["timeline"] = _timeline(conn, order_id)
    conn.close()
    return out


# ─── 看板 ────────────────────────────────────────────────────────────────────

def _days_left(due: str) -> Optional[int]:
    """距出貨期限還有幾天（負數=已逾期）。"""
    try:
        return (date.fromisoformat((due or "")[:10]) - date.today()).days
    except ValueError:
        return None


def _decorate(row: dict) -> dict:
    """加上前端要用的計算旗標：出貨期限急迫度 + 自訂預計日逾期。"""
    o = dict(row)
    done = o.get("track_status") == "已完成結案"
    dl = None if done else _days_left(o.get("due_ship_date"))
    o["days_left"] = dl                       # 距出貨期限天數（None=無法計算/已完成）
    o["ship_overdue"] = bool(dl is not None and dl < 0)   # 出貨期限已逾期
    o["due_soon"] = bool(dl is not None and 0 <= dl <= DUE_SOON_DAYS)  # 快到期
    o["overdue"] = bool(o.get("due_date") and o["due_date"] < _today() and not done)
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
        # 出貨期限或自訂預計日已逾期，且尚未完成
        where.append(
            "track_status != '已完成結案' AND ("
            "(due_ship_date IS NOT NULL AND due_ship_date < ?) OR "
            "(due_date IS NOT NULL AND due_date < ?))"
        )
        args += [_today(), _today()]
    elif view == "duesoon":
        # 快到期（含逾期）且尚未完成
        cutoff = _add_days(_today(), DUE_SOON_DAYS)
        where.append("due_ship_date IS NOT NULL AND due_ship_date <= ? AND track_status != '已完成結案'")
        args.append(cutoff)

    if status:
        where.append("track_status=?")
        args.append(status)
    if owner:
        where.append("owner=?")
        args.append(owner)
    if q:
        like = f"%{q}%"
        where.append("(order_number LIKE ? OR customer_name LIKE ? OR item_summary LIKE ? OR phone LIKE ?)")
        args += [like, like, like, like]

    sql = "SELECT * FROM cs_orders"
    if where:
        sql += " WHERE " + " AND ".join(where)
    # 異常最前 → 再依出貨期限由近到遠（急的排上面），未完成優先
    sql += (" ORDER BY is_risk DESC,"
            " (track_status='已完成結案') ASC,"
            " (due_ship_date IS NULL) ASC, due_ship_date ASC, updated_at DESC")

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

    soon = _add_days(today, DUE_SOON_DAYS)
    active = count("SELECT COUNT(*) FROM cs_orders WHERE archived=0")
    risk = count("SELECT COUNT(*) FROM cs_orders WHERE archived=0 AND is_risk=1")
    overdue = count(
        "SELECT COUNT(*) FROM cs_orders WHERE archived=0 AND due_ship_date IS NOT NULL "
        "AND due_ship_date < ? AND track_status != '已完成結案'", (today,)
    )
    due_soon = count(
        "SELECT COUNT(*) FROM cs_orders WHERE archived=0 AND due_ship_date IS NOT NULL "
        "AND due_ship_date >= ? AND due_ship_date <= ? AND track_status != '已完成結案'", (today, soon)
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
    last_log = conn.execute(
        "SELECT imported_at, source, status, new_count, updated_count, archived_count "
        "FROM cs_import_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return {
        "active": active,
        "risk": risk,
        "overdue": overdue,
        "due_soon": due_soon,
        "by_status": by_status,
        "last_import": last_import,
        "last_import_log": dict(last_log) if last_log else None,
    }


def _timeline(conn, order_id: int) -> list:
    rows = conn.execute(
        """SELECT occurred_at, actor, actor_type, kind, content, created_at
           FROM cs_order_events WHERE order_id=?
           ORDER BY occurred_at ASC, id ASC""",
        (order_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/orders/{order_id}")
def get_order(order_id: int):
    conn = _conn()
    row = conn.execute("SELECT * FROM cs_orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Order not found")
    o = _decorate(row)
    o["timeline"] = _timeline(conn, order_id)
    conn.close()
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
    product_type = pick("product_type", row["product_type"])
    owner        = pick("owner", row["owner"])
    next_action  = pick("next_action", row["next_action"])
    due_date     = pick("due_date", row["due_date"])
    risk_type    = pick("risk_type", row["risk_type"])
    notes        = pick("notes", row["notes"])
    is_risk      = int(body.is_risk) if body.is_risk is not None else row["is_risk"]
    archived     = int(body.archived) if body.archived is not None else row["archived"]
    handler      = (body.handler or "").strip()

    # 改了品項類型 → 重算出貨期限
    sla_days = row["sla_days"]
    due_ship = row["due_ship_date"]
    if product_type != row["product_type"]:
        sla_days = _sla_days(product_type)
        due_ship = _add_days(row["order_date"], sla_days)

    # 完成時補記完成日（退換貨期起算）
    completed_at = row["completed_at"]
    if track_status == "已完成結案" and not completed_at:
        completed_at = _today()

    last_handler = handler or row["last_handler"]

    conn.execute(
        """UPDATE cs_orders SET track_status=?, product_type=?, sla_days=?, due_ship_date=?,
               owner=?, last_handler=?, next_action=?, due_date=?,
               is_risk=?, risk_type=?, notes=?, completed_at=?, archived=?,
               updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (track_status, product_type, sla_days, due_ship, owner, last_handler,
         next_action, due_date, is_risk, risk_type, notes, completed_at, archived, order_id),
    )

    # 旅程記錄：進度推進 / 標記異常（誰、何時）
    who = handler or owner or "員工"
    if track_status != row["track_status"]:
        _log_event(conn, order_id, "staff", who, "stage", f"進度 → {track_status}")
    if is_risk and not row["is_risk"]:
        _log_event(conn, order_id, "staff", who, "risk",
                   f"標記異常：{risk_type or '異常'}" + (f"（{next_action}）" if next_action else ""))

    conn.commit()
    row = conn.execute("SELECT * FROM cs_orders WHERE id=?", (order_id,)).fetchone()
    o = _decorate(row)
    o["timeline"] = _timeline(conn, order_id)
    conn.close()
    return o


@router.post("/orders/{order_id}/events", status_code=201)
def add_event(order_id: int, body: EventCreate):
    """新增一筆購物旅程記錄（員工備註 或 客人對話：誰、何時、說了什麼）。"""
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(400, "內容不可空白")
    conn = _conn()
    row = conn.execute("SELECT id FROM cs_orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Order not found")
    actor_type = body.actor_type if body.actor_type in ("staff", "customer") else "staff"
    actor = (body.actor or ("客人" if actor_type == "customer" else "員工")).strip()
    _log_event(conn, order_id, actor_type, actor, "note", content, body.occurred_at)
    # 員工留言 → 更新最後處理人
    if actor_type == "staff":
        conn.execute("UPDATE cs_orders SET last_handler=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (actor, order_id))
    conn.commit()
    timeline = _timeline(conn, order_id)
    conn.close()
    return {"ok": True, "timeline": timeline}


@router.post("/orders/{order_id}/return")
def return_signoff(order_id: int, body: ReturnAction):
    """退貨簽核：申請 → 主管核准/駁回。每步都記錄誰、何時並寫進購物旅程。"""
    conn = _conn()
    row = conn.execute("SELECT * FROM cs_orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Order not found")
    who = (body.by or "").strip() or "員工"
    action = body.action
    status = row["return_status"]
    signed_by = row["return_signed_by"]
    signed_at = row["return_signed_at"]
    reason = row["return_reason"]

    if action == "request":
        status, reason = "待簽核", (body.reason or reason or "")
        signed_by = signed_at = None
        _log_event(conn, order_id, "staff", who, "return",
                   f"申請退貨簽核" + (f"：{reason}" if reason else ""))
    elif action == "approve":
        status, signed_by, signed_at = "已核准", who, _now()
        _log_event(conn, order_id, "staff", who, "return", "✅ 退貨已核准")
    elif action == "reject":
        status, signed_by, signed_at = "已駁回", who, _now()
        _log_event(conn, order_id, "staff", who, "return",
                   "❌ 退貨已駁回" + (f"：{body.reason}" if body.reason else ""))
    elif action == "cancel":
        status = signed_by = signed_at = reason = None
        _log_event(conn, order_id, "staff", who, "return", "撤銷退貨申請")
    else:
        conn.close()
        raise HTTPException(400, "action 需為 request/approve/reject/cancel")

    conn.execute(
        """UPDATE cs_orders SET return_status=?, return_reason=?, return_signed_by=?,
               return_signed_at=?, last_handler=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (status, reason, signed_by, signed_at, who, order_id),
    )
    conn.commit()
    out = _decorate(conn.execute("SELECT * FROM cs_orders WHERE id=?", (order_id,)).fetchone())
    out["timeline"] = _timeline(conn, order_id)
    conn.close()
    return out


@router.get("/customers/history")
def customer_history(customer_id: Optional[str] = Query(None),
                     phone: Optional[str] = Query(None),
                     exclude_id: Optional[int] = Query(None)):
    """同一客人過去所有訂單（依顧客ID或電話），含誰處理過、進度。"""
    if not customer_id and not phone:
        raise HTTPException(400, "需提供 customer_id 或 phone")
    conn = _conn()
    where, args = [], []
    if customer_id:
        where.append("customer_id=?"); args.append(customer_id)
    elif phone:
        where.append("phone=?"); args.append(phone)
    if exclude_id:
        where.append("id != ?"); args.append(exclude_id)
    rows = conn.execute(
        f"""SELECT id, order_number, customer_name, order_date, total, item_summary,
                  track_status, product_type, last_handler, is_risk, archived
           FROM cs_orders WHERE {' AND '.join(where)}
           ORDER BY order_date DESC""",
        args,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.delete("/orders/{order_id}")
def delete_order(order_id: int):
    conn = _conn()
    cur = conn.execute("DELETE FROM cs_orders WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Order not found")
    return {"deleted": True}


def shopline_order_url(order_number: str) -> str:
    """組出連回 SHOPLINE 後台的訂單網址（找不到設定則回空字串）。"""
    if not order_number or not SHOPLINE_ORDER_URL:
        return ""
    return (SHOPLINE_ORDER_URL
            .replace("{handle}", SHOPLINE_HANDLE or "")
            .replace("{order_number}", str(order_number)))


@router.get("/meta")
def meta():
    """前端下拉選單與外部連結設定用。"""
    return {
        "track_statuses": TRACK_STATUSES,
        "stages": TRACK_STATUSES,
        "risk_types": RISK_TYPES,
        "return_statuses": RETURN_STATUSES,
        "product_types": {k: _sla_days(k) for k in PRODUCT_TYPES},
        "customer_notify_days": CUSTOMER_NOTIFY_DAYS,
        "archive_after_complete_days": ARCHIVE_AFTER_COMPLETE_DAYS,
        "due_soon_days": DUE_SOON_DAYS,
        "shopline_order_url": SHOPLINE_ORDER_URL,
        "shopline_handle": SHOPLINE_HANDLE,
    }


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
