"""admin.py - 管理員專用：員工活動 + 客人分析"""
import sqlite3
import sys
from pathlib import Path
from fastapi import APIRouter, Depends

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH
from api.auth import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _conn():
    c = sqlite3.connect(SQLITE_PATH)
    c.row_factory = sqlite3.Row
    return c


# ── 員工活動 ────────────────────────────────────────────
@router.get("/staff-activity")
def staff_activity(_user=Depends(require_admin)):
    conn = _conn()

    # 用 users 表取得帳號員工（有登入系統的）
    users = [dict(r) for r in conn.execute(
        "SELECT id, name, username, role, is_active FROM users ORDER BY name"
    ).fetchall()]

    # 用 staff 表取得傳統員工名單（staff_name 欄位）
    staff_names = [r[0] for r in conn.execute("SELECT name FROM staff ORDER BY name").fetchall()]

    result = []

    for u in users:
        uid = u["id"]
        name = u["name"]

        # 以 username 或 name 匹配 quotes.staff_name
        quotes_total = conn.execute(
            "SELECT COUNT(*) FROM quotes WHERE staff_name IN (?,?)", (name, u["username"])
        ).fetchone()[0]
        quotes_week = conn.execute(
            """SELECT COUNT(*) FROM quotes
               WHERE staff_name IN (?,?)
               AND quote_date >= date('now','-7 days')""", (name, u["username"])
        ).fetchone()[0]
        quotes_month = conn.execute(
            """SELECT COUNT(*) FROM quotes
               WHERE staff_name IN (?,?)
               AND quote_date >= date('now','-30 days')""", (name, u["username"])
        ).fetchone()[0]

        # 成交金額（本月）
        sales_month = conn.execute(
            """SELECT COALESCE(SUM(q.final_price),0) FROM quotes q
               WHERE q.staff_name IN (?,?)
               AND q.final_price > 0
               AND q.quote_date >= date('now','-30 days')""", (name, u["username"])
        ).fetchone()[0]

        # 服務客人數（透過 customer_sessions）
        customers_served = conn.execute(
            "SELECT COUNT(DISTINCT customer_id) FROM customer_sessions WHERE staff_id=?", (uid,)
        ).fetchone()[0]
        sessions_month = conn.execute(
            """SELECT COUNT(*) FROM customer_sessions WHERE staff_id=?
               AND created_at >= date('now','-30 days')""", (uid,)
        ).fetchone()[0]

        # 最近 5 筆動作（報價 + 客人 session）
        recent_quotes = conn.execute(
            """SELECT 'quote' as type, description, customer_name, final_price,
                      quote_date as action_date
               FROM quotes WHERE staff_name IN (?,?)
               ORDER BY quote_date DESC LIMIT 5""", (name, u["username"])
        ).fetchall()
        recent_sessions = conn.execute(
            """SELECT 'session' as type, c.name as customer_name, cs.notes,
                      cs.created_at as action_date
               FROM customer_sessions cs
               JOIN customers c ON c.id = cs.customer_id
               WHERE cs.staff_id=?
               ORDER BY cs.created_at DESC LIMIT 5""", (uid,)
        ).fetchall()

        # 合併並排序
        actions = []
        for r in recent_quotes:
            d = dict(r)
            label = f"估價：{d['description'] or ''}"
            if d["final_price"]: label += f" → NT${d['final_price']:,}"
            actions.append({"type": "quote", "label": label,
                            "customer": d["customer_name"] or "", "date": d["action_date"]})
        for r in recent_sessions:
            d = dict(r)
            actions.append({"type": "session", "label": f"服務客人：{d['customer_name']}",
                            "customer": d["customer_name"], "date": d["action_date"]})
        actions.sort(key=lambda x: x["date"] or "", reverse=True)

        result.append({
            **u,
            "quotes_total": quotes_total,
            "quotes_week": quotes_week,
            "quotes_month": quotes_month,
            "sales_month": sales_month,
            "customers_served": customers_served,
            "sessions_month": sessions_month,
            "recent_actions": actions[:8],
        })

    conn.close()
    return result


# ── 客人分析 ────────────────────────────────────────────
@router.get("/customer-analytics")
def customer_analytics(_user=Depends(require_admin)):
    conn = _conn()

    # 被收藏最多的照片（前 20）
    top_photos = conn.execute(
        """SELECT p.id, p.filename, p.category, p.gemstone, p.style, p.color,
                  COUNT(cf.id) as fav_count
           FROM customer_favorites cf
           JOIN photos p ON p.id = cf.photo_id
           GROUP BY cf.photo_id ORDER BY fav_count DESC LIMIT 20"""
    ).fetchall()

    # 喜好分佈：類別
    cat_dist = conn.execute(
        """SELECT p.category, COUNT(*) as cnt
           FROM customer_favorites cf JOIN photos p ON p.id=cf.photo_id
           WHERE p.category IS NOT NULL
           GROUP BY p.category ORDER BY cnt DESC"""
    ).fetchall()

    # 喜好分佈：寶石
    gem_dist = conn.execute(
        """SELECT p.gemstone, COUNT(*) as cnt
           FROM customer_favorites cf JOIN photos p ON p.id=cf.photo_id
           WHERE p.gemstone IS NOT NULL
           GROUP BY p.gemstone ORDER BY cnt DESC LIMIT 10"""
    ).fetchall()

    # 喜好分佈：款式
    style_dist = conn.execute(
        """SELECT p.style, COUNT(*) as cnt
           FROM customer_favorites cf JOIN photos p ON p.id=cf.photo_id
           WHERE p.style IS NOT NULL
           GROUP BY p.style ORDER BY cnt DESC"""
    ).fetchall()

    # 喜好分佈：顏色
    color_dist = conn.execute(
        """SELECT p.color, COUNT(*) as cnt
           FROM customer_favorites cf JOIN photos p ON p.id=cf.photo_id
           WHERE p.color IS NOT NULL
           GROUP BY p.color ORDER BY cnt DESC"""
    ).fetchall()

    # 近期互動（最近 30 筆 customer_sessions）
    recent = conn.execute(
        """SELECT cs.id, cs.created_at, cs.notes,
                  c.id as customer_id, c.name as customer_name,
                  s.name as staff_name,
                  COUNT(cf.id) as fav_count
           FROM customer_sessions cs
           JOIN customers c ON c.id = cs.customer_id
           LEFT JOIN staff s ON s.id = cs.staff_id
           LEFT JOIN customer_favorites cf ON cf.session_id = cs.id
           GROUP BY cs.id
           ORDER BY cs.created_at DESC LIMIT 30"""
    ).fetchall()

    # 客人總覽（最近活躍）
    customers = conn.execute(
        """SELECT c.id, c.name, c.phone, c.line_id,
                  COUNT(DISTINCT cs.id) as session_count,
                  COUNT(DISTINCT cf.photo_id) as fav_count,
                  MAX(cs.created_at) as last_interaction,
                  (SELECT COUNT(*) FROM transactions t WHERE t.client_name = c.name) as tx_count
           FROM customers c
           LEFT JOIN customer_sessions cs ON cs.customer_id = c.id
           LEFT JOIN customer_favorites cf ON cf.customer_id = c.id
           GROUP BY c.id
           ORDER BY last_interaction DESC NULLS LAST
           LIMIT 50"""
    ).fetchall()

    # 總收藏數
    total_favs = conn.execute("SELECT COUNT(*) FROM customer_favorites").fetchone()[0]
    total_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    total_sessions = conn.execute("SELECT COUNT(*) FROM customer_sessions").fetchone()[0]

    conn.close()
    return {
        "summary": {
            "total_customers": total_customers,
            "total_sessions": total_sessions,
            "total_favs": total_favs,
        },
        "top_photos": [dict(r) for r in top_photos],
        "distribution": {
            "category": [dict(r) for r in cat_dist],
            "gemstone":  [dict(r) for r in gem_dist],
            "style":     [dict(r) for r in style_dist],
            "color":     [dict(r) for r in color_dist],
        },
        "recent_interactions": [dict(r) for r in recent],
        "customers": [dict(r) for r in customers],
    }


# ── 建檔品質：各欄位缺標籤統計 ──────────────────────────
@router.get("/data-quality")
def data_quality(_user=Depends(require_admin)):
    FIELDS = [
        ("category", "品項"), ("gemstone", "寶石"), ("stone_shape", "形狀"),
        ("stone_size", "大小"), ("color", "色系"), ("metal_color", "金工色"),
        ("style", "鑽飾"), ("setting_amount", "配石量"), ("craft_complexity", "複雜度"),
        ("price_band", "價位"), ("photo_type", "照片類型"), ("material", "材質"),
    ]
    conn = _conn()
    total = conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
    fields = []
    for col, label in FIELDS:
        missing = conn.execute(
            f"SELECT COUNT(*) FROM photos WHERE {col} IS NULL OR {col} = '' OR {col} = '未定'"
        ).fetchone()[0]
        fields.append({"field": col, "label": label, "missing": missing})
    conn.close()
    return {"total": total, "fields": fields}
