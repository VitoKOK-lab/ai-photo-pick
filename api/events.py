"""events.py - 互動事件埋點"""
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

router = APIRouter(prefix="/api/events", tags=["events"])

class EventCreate(BaseModel):
    photo_id: int
    event_type: str
    session_id: str
    dwell_ms: Optional[int] = None
    metadata: Optional[dict] = None

VALID_TYPES = {"view", "click", "favorite", "unfavorite", "lock", "unlock", "dwell"}

@router.post("")
def log_event(body: EventCreate):
    if body.event_type not in VALID_TYPES:
        return {"error": f"Invalid event_type. Valid: {VALID_TYPES}"}

    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()

    cur.execute(
        """INSERT INTO events (photo_id, event_type, dwell_ms, session_id, metadata_json)
           VALUES (?, ?, ?, ?, ?)""",
        (
            body.photo_id,
            body.event_type,
            body.dwell_ms,
            body.session_id,
            json.dumps(body.metadata, ensure_ascii=False) if body.metadata else None,
        )
    )
    event_id = cur.lastrowid

    if body.event_type == "view":
        cur.execute("UPDATE photos SET view_count = view_count + 1 WHERE id = ?", (body.photo_id,))
    elif body.event_type == "click":
        cur.execute("UPDATE photos SET click_count = click_count + 1 WHERE id = ?", (body.photo_id,))
    elif body.event_type == "dwell" and body.dwell_ms:
        cur.execute(
            "UPDATE photos SET total_dwell_ms = total_dwell_ms + ? WHERE id = ?",
            (body.dwell_ms, body.photo_id)
        )

    conn.commit()
    conn.close()
    return {"id": event_id}
