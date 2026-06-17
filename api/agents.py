"""agents.py - 代理商登入、滑卡推薦、收藏、分析"""
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

router = APIRouter(prefix="/api/agents", tags=["agents"])

ADMIN_PIN = "1234"  # must match frontend ADMIN_PIN


# ── DB helpers ────────────────────────────────────────────

def _conn():
    c = sqlite3.connect(SQLITE_PATH)
    c.row_factory = sqlite3.Row
    return c


def _ensure_tables():
    c = _conn()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL,
            phone      TEXT,
            pin        TEXT    NOT NULL,
            notes      TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS agent_swipes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id   INTEGER NOT NULL,
            photo_id   INTEGER NOT NULL,
            action     TEXT    NOT NULL CHECK(action IN ('like','unlike')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(agent_id, photo_id)
        );
        CREATE TABLE IF NOT EXISTS agent_favorites (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id   INTEGER NOT NULL,
            photo_id   INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(agent_id, photo_id)
        );
    """)
    c.commit()
    c.close()


_ensure_tables()


def _verify_agent(c, agent_id: int, pin: str):
    row = c.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if not row or row["pin"] != pin:
        raise HTTPException(status_code=401, detail="代理身份驗證失敗")
    return row


def _photo_row_to_dict(row) -> dict:
    d = dict(row)
    filename = d.get("filename") or ""
    if filename:
        d.setdefault("thumb_url",  f"/static/thumb/{filename}")
        d.setdefault("full_url",   f"/static/full/{filename}")
    return d


# ── Auth / CRUD ───────────────────────────────────────────

class AgentLogin:
    pass


@router.post("/login")
def agent_login(body: dict):
    name  = (body.get("name") or "").strip()
    phone = (body.get("phone") or "").strip()
    pin   = (body.get("pin") or "").strip()
    if not pin:
        raise HTTPException(status_code=400, detail="請輸入 PIN")
    c = _conn()
    row = None
    if phone:
        row = c.execute("SELECT * FROM agents WHERE phone=? AND pin=?", (phone, pin)).fetchone()
    if not row and name:
        row = c.execute("SELECT * FROM agents WHERE name=? AND pin=?", (name, pin)).fetchone()
    c.close()
    if not row:
        raise HTTPException(status_code=401, detail="代理帳號或 PIN 錯誤")
    return {"id": row["id"], "name": row["name"], "phone": row["phone"] or ""}


@router.get("")
def list_agents(admin_pin: str = ""):
    if admin_pin != ADMIN_PIN:
        raise HTTPException(status_code=403, detail="需要管理員 PIN")
    c = _conn()
    rows = c.execute("SELECT id, name, phone, notes, created_at FROM agents ORDER BY id").fetchall()
    # add swipe/fav counts
    result = []
    for r in rows:
        aid = r["id"]
        swipes   = c.execute("SELECT COUNT(*) FROM agent_swipes   WHERE agent_id=?", (aid,)).fetchone()[0]
        likes    = c.execute("SELECT COUNT(*) FROM agent_swipes   WHERE agent_id=? AND action='like'",   (aid,)).fetchone()[0]
        unlikes  = c.execute("SELECT COUNT(*) FROM agent_swipes   WHERE agent_id=? AND action='unlike'", (aid,)).fetchone()[0]
        favs     = c.execute("SELECT COUNT(*) FROM agent_favorites WHERE agent_id=?", (aid,)).fetchone()[0]
        d = dict(r)
        d.update(swipes=swipes, likes=likes, unlikes=unlikes, favs=favs)
        result.append(d)
    c.close()
    return result


@router.post("")
def create_agent(body: dict):
    if body.get("admin_pin") != ADMIN_PIN:
        raise HTTPException(status_code=403, detail="需要管理員 PIN")
    name  = (body.get("name") or "").strip()
    phone = (body.get("phone") or "").strip()
    pin   = (body.get("pin") or "").strip()
    notes = (body.get("notes") or "").strip()
    if not name or not pin:
        raise HTTPException(status_code=400, detail="姓名和 PIN 必填")
    c = _conn()
    try:
        c.execute("INSERT INTO agents (name, phone, pin, notes) VALUES (?,?,?,?)", (name, phone, pin, notes))
        c.commit()
        new_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    except Exception:
        c.close()
        raise HTTPException(status_code=400, detail="建立失敗（可能重複）")
    c.close()
    return {"id": new_id, "name": name, "phone": phone}


@router.delete("/{agent_id}")
def delete_agent(agent_id: int, admin_pin: str = ""):
    if admin_pin != ADMIN_PIN:
        raise HTTPException(status_code=403, detail="需要管理員 PIN")
    c = _conn()
    c.execute("DELETE FROM agent_swipes    WHERE agent_id=?", (agent_id,))
    c.execute("DELETE FROM agent_favorites WHERE agent_id=?", (agent_id,))
    c.execute("DELETE FROM agents WHERE id=?", (agent_id,))
    c.commit()
    c.close()
    return {"ok": True}


# ── Swipe ─────────────────────────────────────────────────

@router.post("/{agent_id}/swipe")
def record_swipe(agent_id: int, body: dict):
    pin      = (body.get("pin") or "").strip()
    photo_id = body.get("photo_id")
    action   = body.get("action")
    if action not in ("like", "unlike"):
        raise HTTPException(status_code=400, detail="action 必須是 like 或 unlike")
    c = _conn()
    _verify_agent(c, agent_id, pin)
    c.execute("""
        INSERT INTO agent_swipes (agent_id, photo_id, action)
        VALUES (?,?,?)
        ON CONFLICT(agent_id, photo_id) DO UPDATE SET action=excluded.action, created_at=CURRENT_TIMESTAMP
    """, (agent_id, photo_id, action))
    c.commit()
    c.close()
    return {"ok": True}


# ── Recommendations ───────────────────────────────────────

@router.get("/{agent_id}/recommendations")
def get_recommendations(
    agent_id: int,
    pin: str = "",
    category: str = "",
    gemstone: str = "",
    style: str = "",
    metal_color: str = "",
    stone_shape: str = "",
    color: str = "",
    limit: int = 20,
):
    c = _conn()
    _verify_agent(c, agent_id, pin)

    # Build exclude set (unlikes)
    unlike_ids = {r[0] for r in c.execute(
        "SELECT photo_id FROM agent_swipes WHERE agent_id=? AND action='unlike'", (agent_id,)
    ).fetchall()}

    # Already seen (both like and unlike)
    seen_ids = {r[0] for r in c.execute(
        "SELECT photo_id FROM agent_swipes WHERE agent_id=?", (agent_id,)
    ).fetchall()}

    # Liked photos — build preference counters
    liked_rows = c.execute("""
        SELECT p.category, p.gemstone, p.style, p.stone_shape, p.color, p.material
        FROM agent_swipes s
        JOIN photos p ON p.id = s.photo_id
        WHERE s.agent_id=? AND s.action='like'
    """, (agent_id,)).fetchall()

    cat_pref   = Counter(r["category"]    for r in liked_rows if r["category"])
    gem_pref   = Counter(r["gemstone"]    for r in liked_rows if r["gemstone"])
    sty_pref   = Counter(r["style"]       for r in liked_rows if r["style"])
    shp_pref   = Counter(r["stone_shape"] for r in liked_rows if r["stone_shape"])
    col_pref   = Counter(r["color"]       for r in liked_rows if r["color"])

    # Build query
    conds  = ["photo_type = '去背'"]
    params = []
    if category:
        conds.append("category = ?");    params.append(category)
    if gemstone:
        conds.append("gemstone = ?");    params.append(gemstone)
    if style:
        conds.append("style = ?");       params.append(style)
    if metal_color:
        conds.append("metal_color = ?"); params.append(metal_color)
    if stone_shape:
        conds.append("stone_shape = ?"); params.append(stone_shape)
    if color:
        conds.append("color = ?");       params.append(color)

    where = " AND ".join(conds)
    rows = c.execute(
        f"SELECT id, filename, category, gemstone, style, stone_shape, color, material, stone_size, metal_color "
        f"FROM photos WHERE {where} ORDER BY RANDOM() LIMIT 300",
        params,
    ).fetchall()
    c.close()

    # Filter out seen/unliked
    candidates = [r for r in rows if r["id"] not in seen_ids]

    # Score by preference similarity
    def score(p):
        s = 0
        if cat_pref and p["category"] in cat_pref:   s += cat_pref[p["category"]] * 4
        if gem_pref and p["gemstone"] in gem_pref:   s += gem_pref[p["gemstone"]] * 3
        if sty_pref and p["style"]    in sty_pref:   s += sty_pref[p["style"]] * 2
        if shp_pref and p["stone_shape"] in shp_pref: s += shp_pref[p["stone_shape"]] * 2
        if col_pref and p["color"]    in col_pref:   s += col_pref[p["color"]]
        return s

    candidates.sort(key=score, reverse=True)
    result = candidates[:limit]

    return [_photo_row_to_dict(p) for p in result]


# ── Favorites ─────────────────────────────────────────────

@router.get("/{agent_id}/favorites")
def get_favorites(agent_id: int, pin: str = ""):
    c = _conn()
    _verify_agent(c, agent_id, pin)
    rows = c.execute("""
        SELECT p.id, p.filename, p.category, p.gemstone, p.style, p.stone_shape,
               p.color, p.material, p.stone_size, p.metal_color,
               af.created_at as fav_at
        FROM agent_favorites af
        JOIN photos p ON p.id = af.photo_id
        WHERE af.agent_id = ?
        ORDER BY af.created_at DESC
    """, (agent_id,)).fetchall()
    c.close()
    return [_photo_row_to_dict(r) for r in rows]


@router.post("/{agent_id}/favorites/{photo_id}")
def add_favorite(agent_id: int, photo_id: int, body: dict = {}):
    pin = (body.get("pin") or "").strip()
    c = _conn()
    _verify_agent(c, agent_id, pin)
    try:
        c.execute("INSERT OR IGNORE INTO agent_favorites (agent_id, photo_id) VALUES (?,?)", (agent_id, photo_id))
        c.commit()
    finally:
        c.close()
    return {"ok": True}


@router.delete("/{agent_id}/favorites/{photo_id}")
def remove_favorite(agent_id: int, photo_id: int, pin: str = ""):
    c = _conn()
    _verify_agent(c, agent_id, pin)
    c.execute("DELETE FROM agent_favorites WHERE agent_id=? AND photo_id=?", (agent_id, photo_id))
    c.commit()
    c.close()
    return {"ok": True}


# ── Analytics ─────────────────────────────────────────────

@router.get("/{agent_id}/stats")
def agent_stats(agent_id: int, pin: str = ""):
    c = _conn()
    _verify_agent(c, agent_id, pin)

    total_swipes  = c.execute("SELECT COUNT(*) FROM agent_swipes WHERE agent_id=?", (agent_id,)).fetchone()[0]
    total_likes   = c.execute("SELECT COUNT(*) FROM agent_swipes WHERE agent_id=? AND action='like'",   (agent_id,)).fetchone()[0]
    total_unlikes = c.execute("SELECT COUNT(*) FROM agent_swipes WHERE agent_id=? AND action='unlike'", (agent_id,)).fetchone()[0]
    total_favs    = c.execute("SELECT COUNT(*) FROM agent_favorites WHERE agent_id=?", (agent_id,)).fetchone()[0]

    # Top liked categories/gemstones
    cat_rows = c.execute("""
        SELECT p.category, COUNT(*) as cnt FROM agent_swipes s
        JOIN photos p ON p.id=s.photo_id
        WHERE s.agent_id=? AND s.action='like' AND p.category IS NOT NULL
        GROUP BY p.category ORDER BY cnt DESC LIMIT 5
    """, (agent_id,)).fetchall()

    gem_rows = c.execute("""
        SELECT p.gemstone, COUNT(*) as cnt FROM agent_swipes s
        JOIN photos p ON p.id=s.photo_id
        WHERE s.agent_id=? AND s.action='like' AND p.gemstone IS NOT NULL
        GROUP BY p.gemstone ORDER BY cnt DESC LIMIT 5
    """, (agent_id,)).fetchall()

    sty_rows = c.execute("""
        SELECT p.style, COUNT(*) as cnt FROM agent_swipes s
        JOIN photos p ON p.id=s.photo_id
        WHERE s.agent_id=? AND s.action='like' AND p.style IS NOT NULL
        GROUP BY p.style ORDER BY cnt DESC LIMIT 5
    """, (agent_id,)).fetchall()

    c.close()
    return {
        "total_swipes":  total_swipes,
        "total_likes":   total_likes,
        "total_unlikes": total_unlikes,
        "total_favs":    total_favs,
        "top_categories": [dict(r) for r in cat_rows],
        "top_gemstones":  [dict(r) for r in gem_rows],
        "top_styles":     [dict(r) for r in sty_rows],
    }


@router.get("/analytics/all")
def all_analytics(admin_pin: str = ""):
    if admin_pin != ADMIN_PIN:
        raise HTTPException(status_code=403, detail="需要管理員 PIN")
    c = _conn()
    agents = c.execute("SELECT id, name, phone FROM agents ORDER BY id").fetchall()
    result = []
    for a in agents:
        aid = a["id"]
        stats = {
            "id": aid, "name": a["name"], "phone": a["phone"] or "",
            "likes":   c.execute("SELECT COUNT(*) FROM agent_swipes WHERE agent_id=? AND action='like'",   (aid,)).fetchone()[0],
            "unlikes": c.execute("SELECT COUNT(*) FROM agent_swipes WHERE agent_id=? AND action='unlike'", (aid,)).fetchone()[0],
            "favs":    c.execute("SELECT COUNT(*) FROM agent_favorites WHERE agent_id=?", (aid,)).fetchone()[0],
        }
        top_cat = c.execute("""
            SELECT p.category FROM agent_swipes s JOIN photos p ON p.id=s.photo_id
            WHERE s.agent_id=? AND s.action='like' AND p.category IS NOT NULL
            GROUP BY p.category ORDER BY COUNT(*) DESC LIMIT 1
        """, (aid,)).fetchone()
        stats["top_category"] = top_cat[0] if top_cat else ""
        result.append(stats)
    c.close()
    return result
