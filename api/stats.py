"""stats.py - 統計 Dashboard API"""
import sqlite3
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/overview")
def overview():
    """總覽：照片數、互動總量、平均停留"""
    conn = _conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM photos")
    total_photos = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(view_count), 0) FROM photos")
    total_views = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(click_count), 0) FROM photos")
    total_clicks = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(favorite_count), 0) FROM photos")
    total_favorites = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(lock_count), 0) FROM photos")
    total_locks = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(total_dwell_ms), 0) FROM photos")
    total_dwell_ms = cur.fetchone()[0]
    avg_dwell_sec = round(total_dwell_ms / total_clicks / 1000, 1) if total_clicks > 0 else 0

    cur.execute("SELECT COUNT(DISTINCT session_id) FROM events")
    total_sessions = cur.fetchone()[0]

    conn.close()
    return {
        "total_photos": total_photos,
        "total_views": total_views,
        "total_clicks": total_clicks,
        "total_favorites": total_favorites,
        "total_locks": total_locks,
        "avg_dwell_sec": avg_dwell_sec,
        "total_sessions": total_sessions,
    }


@router.get("/top-photos")
def top_photos(
    sort_by: str = Query("popular", pattern="^(popular|views|favorites|locks|dwell)$"),
    limit: int = Query(20, ge=1, le=100),
):
    """熱門照片排行"""
    order_map = {
        "popular": "(view_count + favorite_count * 3 + lock_count * 5) DESC",
        "views": "view_count DESC",
        "favorites": "favorite_count DESC",
        "locks": "lock_count DESC",
        "dwell": "total_dwell_ms DESC",
    }
    order_clause = order_map[sort_by]

    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"""SELECT id, filename, category, color, gemstone, price_band,
                   view_count, click_count, favorite_count, lock_count, total_dwell_ms
            FROM photos
            ORDER BY {order_clause}
            LIMIT ?""",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()

    return {
        "sort_by": sort_by,
        "photos": [{
            "id": r["id"],
            "filename": r["filename"],
            "thumb_url": f"/static/thumb/{r['filename']}",
            "micro_url": f"/static/micro/{r['filename']}",
            "category": r["category"],
            "color": r["color"],
            "gemstone": r["gemstone"],
            "price_band": r["price_band"],
            "view_count": r["view_count"],
            "click_count": r["click_count"],
            "favorite_count": r["favorite_count"],
            "lock_count": r["lock_count"],
            "avg_dwell_sec": round(r["total_dwell_ms"] / r["click_count"] / 1000, 1)
                             if r["click_count"] > 0 else 0,
        } for r in rows]
    }


@router.get("/by-dimension")
def by_dimension(
    dim: str = Query("category", pattern="^(category|color|gemstone|material|price_band)$"),
):
    """各維度分布：照片數 + 互動數"""
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"""SELECT {dim} as label,
                   COUNT(*) as photo_count,
                   COALESCE(SUM(view_count), 0) as views,
                   COALESCE(SUM(favorite_count), 0) as favorites,
                   COALESCE(SUM(lock_count), 0) as locks
            FROM photos
            WHERE {dim} IS NOT NULL AND {dim} != ''
            GROUP BY {dim}
            ORDER BY views DESC""",
    )
    rows = cur.fetchall()
    conn.close()

    return {
        "dimension": dim,
        "items": [{
            "label": r["label"],
            "photo_count": r["photo_count"],
            "views": r["views"],
            "favorites": r["favorites"],
            "locks": r["locks"],
        } for r in rows]
    }


@router.get("/daily")
def daily_trend(days: int = Query(30, ge=7, le=90)):
    """最近 N 天每日互動趨勢"""
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"""SELECT DATE(created_at) as day,
                   COUNT(*) as total_events,
                   SUM(CASE WHEN event_type='view' THEN 1 ELSE 0 END) as views,
                   SUM(CASE WHEN event_type='click' THEN 1 ELSE 0 END) as clicks,
                   SUM(CASE WHEN event_type='favorite' THEN 1 ELSE 0 END) as favorites,
                   SUM(CASE WHEN event_type='lock' THEN 1 ELSE 0 END) as locks,
                   COUNT(DISTINCT session_id) as sessions
            FROM events
            WHERE created_at >= DATE('now', '-{days} days')
            GROUP BY DATE(created_at)
            ORDER BY day ASC""",
    )
    rows = cur.fetchall()
    conn.close()

    return {
        "days": days,
        "data": [{
            "day": r["day"],
            "total_events": r["total_events"],
            "views": r["views"],
            "clicks": r["clicks"],
            "favorites": r["favorites"],
            "locks": r["locks"],
            "sessions": r["sessions"],
        } for r in rows]
    }


@router.get("/sessions")
def sessions_stats(limit: int = Query(20, ge=1, le=100)):
    """各 session 互動統計"""
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT session_id,
                  COUNT(*) as total_events,
                  COUNT(DISTINCT photo_id) as unique_photos,
                  SUM(CASE WHEN event_type='favorite' THEN 1 ELSE 0 END) as favorites,
                  SUM(CASE WHEN event_type='lock' THEN 1 ELSE 0 END) as locks,
                  MIN(created_at) as first_seen,
                  MAX(created_at) as last_seen
           FROM events
           GROUP BY session_id
           ORDER BY total_events DESC
           LIMIT ?""",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()

    return {
        "sessions": [{
            "session_id": r["session_id"],
            "total_events": r["total_events"],
            "unique_photos": r["unique_photos"],
            "favorites": r["favorites"],
            "locks": r["locks"],
            "first_seen": r["first_seen"],
            "last_seen": r["last_seen"],
        } for r in rows]
    }
