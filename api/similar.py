"""similar.py - 相關性搜尋"""
import sqlite3
import sys
from pathlib import Path
from typing import Optional
import numpy as np
from fastapi import APIRouter, Query, HTTPException
import chromadb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, CHROMA_PATH

router = APIRouter(prefix="/api/photos", tags=["similar"])

_chroma_client = None
_collection = None

def _get_collection():
    global _chroma_client, _collection
    if _collection is None:
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

def _row_to_dict(row):
    return {
        "id": row["id"],
        "filename": row["filename"],
        "micro_url": f"/static/micro/{row['filename']}",
        "thumb_url": f"/static/thumb/{row['filename']}",
        "full_url": f"/static/full/{row['filename']}",
        "color": row["color"],
        "category": row["category"],
        "material": row["material"],
        "gemstone": row["gemstone"],
        "price_band": row["price_band"],
    }

@router.get("/{photo_id}/similar")
def find_similar(
    photo_id: int,
    limit: int = Query(8, ge=1, le=50),
    exclude_seen: bool = True,
    session_id: Optional[str] = None,
    weight_visual: float = Query(0.7, ge=0, le=1),
    weight_attribute: float = Query(0.3, ge=0, le=1),
):
    conn = _conn()
    cur = conn.cursor()

    # 1. 取 anchor
    cur.execute("SELECT * FROM photos WHERE id = ?", (photo_id,))
    anchor_row = cur.fetchone()
    if not anchor_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Anchor photo not found")
    anchor = dict(anchor_row)
    anchor_category = anchor.get("category")

    # 2. 取 anchor embedding
    collection = _get_collection()
    anchor_chroma = collection.get(ids=[f"photo_{photo_id}"], include=["embeddings"])
    if not anchor_chroma["embeddings"]:
        conn.close()
        raise HTTPException(status_code=404, detail="Anchor embedding not found")
    anchor_emb = anchor_chroma["embeddings"][0]

    # 3. 從 SQLite 拿全部同品項照片（不含自己）
    cur.execute(
        "SELECT * FROM photos WHERE category = ? AND id != ?",
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
        return {"anchor": _row_to_dict(anchor_row), "similar": []}

    # 4. 批次從 ChromaDB 拿同品項的 embeddings
    chroma_ids = [f"photo_{r['id']}" for r in same_cat_rows]
    BATCH = 500
    emb_map: dict[int, list] = {}
    for i in range(0, len(chroma_ids), BATCH):
        batch_ids = chroma_ids[i : i + BATCH]
        res = collection.get(ids=batch_ids, include=["embeddings"])
        for cid, emb in zip(res["ids"], res["embeddings"]):
            if emb is not None:
                pid = int(cid.replace("photo_", ""))
                emb_map[pid] = emb

    # 5. 計算相似度並排序
    scored = []
    for row in same_cat_rows:
        pid = row["id"]
        target = dict(row)
        v_score = _cosine_sim(anchor_emb, emb_map[pid]) if pid in emb_map else 0.5
        a_score = _attribute_sim(anchor, target)
        final = weight_visual * v_score + weight_attribute * a_score
        scored.append((pid, final, target))

    scored.sort(key=lambda x: x[1], reverse=True)

    similar = []
    for pid, score, target in scored[:limit]:
        similar.append({
            "id": target["id"],
            "filename": target["filename"],
            "micro_url": f"/static/micro/{target['filename']}",
            "thumb_url": f"/static/thumb/{target['filename']}",
            "full_url": f"/static/full/{target['filename']}",
            "color": target["color"],
            "category": target["category"],
            "gemstone": target["gemstone"],
            "material": target["material"],
            "price_band": target["price_band"],
            "similarity_score": round(score, 4),
        })

    return {
        "anchor": _row_to_dict(anchor_row),
        "similar": similar,
    }
