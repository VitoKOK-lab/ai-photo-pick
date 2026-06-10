"""similar.py - 相關性搜尋"""
import sqlite3
import sys
from pathlib import Path
from typing import Optional
import numpy as np
from fastapi import APIRouter, Query, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, CHROMA_PATH

router = APIRouter(prefix="/api/photos", tags=["similar"])

_chroma_client = None
_collection = None

def _get_collection():
    global _chroma_client, _collection
    if _collection is None:
        import chromadb
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _collection = _chroma_client.get_or_create_collection(
            "jewelry_embeddings",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection

def _conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _cosine_sim(a, b) -> float:
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))

def _attribute_sim(anchor: dict, target: dict) -> float:
    score = 0.0
    if anchor.get("color")    == target.get("color"):    score += 0.4
    if anchor.get("gemstone") == target.get("gemstone"): score += 0.35
    if anchor.get("material") == target.get("material"): score += 0.15
    if anchor.get("style")    == target.get("style"):    score += 0.10
    return score

def _row_to_sim_dict(row) -> dict:
    d = dict(row)
    return {
        "id":         d["id"],
        "filename":   d["filename"],
        "micro_url":  f"/static/micro/{d['filename']}",
        "thumb_url":  f"/static/thumb/{d['filename']}",
        "full_url":   f"/static/full/{d['filename']}",
        "color":      d.get("color"),
        "category":   d.get("category"),
        "material":   d.get("material"),
        "gemstone":   d.get("gemstone"),
        "price_band": d.get("price_band"),
    }

@router.get("/{photo_id}/similar")
def find_similar(
    photo_id: int,
    limit: int = Query(12, ge=1, le=50),
    exclude_seen: bool = True,
    session_id: Optional[str] = None,
    weight_visual: float = Query(0.7, ge=0, le=1),
    weight_attribute: float = Query(0.3, ge=0, le=1),
):
    conn = _conn()
    cur = conn.cursor()

    # 1. anchor
    cur.execute("SELECT * FROM photos WHERE id = ?", (photo_id,))
    anchor_row = cur.fetchone()
    if not anchor_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Photo not found")
    anchor = dict(anchor_row)
    anchor_category = anchor.get("category")

    # 2. 同品項 candidates
    cur.execute(
        "SELECT * FROM photos WHERE category = ? AND id != ? ORDER BY RANDOM()",
        (anchor_category, photo_id),
    )
    same_cat_rows = cur.fetchall()

    if exclude_seen and session_id:
        cur.execute(
            "SELECT DISTINCT photo_id FROM events WHERE session_id = ? AND event_type IN ('view','click')",
            (session_id,),
        )
        seen_ids = {r[0] for r in cur.fetchall()}
        same_cat_rows = [r for r in same_cat_rows if r["id"] not in seen_ids]

    conn.close()

    if not same_cat_rows:
        return {"anchor": _row_to_sim_dict(anchor_row), "similar": [], "method": "none"}

    # 3. 嘗試取 anchor embedding（失敗則降級）
    anchor_emb = None
    emb_map: dict[int, list] = {}
    try:
        collection = _get_collection()
        anchor_chroma = collection.get(ids=[f"photo_{photo_id}"], include=["embeddings"])
        if anchor_chroma["embeddings"] and anchor_chroma["embeddings"][0] is not None:
            anchor_emb = anchor_chroma["embeddings"][0]
            # batch-fetch embeddings for candidates
            chroma_ids = [f"photo_{r['id']}" for r in same_cat_rows]
            BATCH = 500
            for i in range(0, len(chroma_ids), BATCH):
                batch_ids = chroma_ids[i : i + BATCH]
                res = collection.get(ids=batch_ids, include=["embeddings"])
                for cid, emb in zip(res["ids"], res["embeddings"]):
                    if emb is not None:
                        pid = int(cid.replace("photo_", ""))
                        emb_map[pid] = emb
    except Exception:
        anchor_emb = None
        emb_map = {}

    # 4. 排序：有 embedding 用 visual+attribute；否則純 attribute（+隨機noise保持多樣）
    import random
    scored = []
    for row in same_cat_rows:
        pid = row["id"]
        target = dict(row)
        a_score = _attribute_sim(anchor, target)
        if anchor_emb is not None and pid in emb_map:
            v_score = _cosine_sim(anchor_emb, emb_map[pid])
            final = weight_visual * v_score + weight_attribute * a_score
        else:
            final = a_score + random.uniform(0, 0.05)
        scored.append((pid, final, row))

    scored.sort(key=lambda x: x[1], reverse=True)
    method = "visual+attribute" if anchor_emb else "attribute"

    similar = [
        {**_row_to_sim_dict(row), "similarity_score": round(score, 4)}
        for _, score, row in scored[:limit]
    ]

    return {
        "anchor": _row_to_sim_dict(anchor_row),
        "similar": similar,
        "method": method,
    }
