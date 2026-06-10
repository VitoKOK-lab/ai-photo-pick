"""similar.py - 相關性搜尋"""
import sqlite3
import sys
from pathlib import Path
from typing import Optional
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

def _attribute_sim(anchor: dict, target: dict) -> float:
    """屬性相似度，0-1"""
    score = 0.0
    if anchor.get("category") == target.get("category"):
        score += 0.4
    if anchor.get("color") == target.get("color"):
        score += 0.3
    if anchor.get("gemstone") == target.get("gemstone"):
        score += 0.2
    if anchor.get("material") == target.get("material"):
        score += 0.1
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
    cur.execute("SELECT * FROM photos WHERE id = ?", (photo_id,))
    anchor_row = cur.fetchone()
    if not anchor_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Anchor photo not found")
    anchor = dict(anchor_row)

    collection = _get_collection()
    anchor_chroma = collection.get(ids=[f"photo_{photo_id}"], include=["embeddings"])
    if not anchor_chroma["embeddings"]:
        conn.close()
        raise HTTPException(status_code=404, detail="Anchor embedding not found")
    anchor_embedding = anchor_chroma["embeddings"][0]

    # 查足夠多結果確保能找到同品項：最多 300 筆，至少 1 筆
    total = collection.count()
    n_query = max(1, min(total - 1, 300))
    chroma_result = collection.query(
        query_embeddings=[anchor_embedding],
        n_results=n_query,
    )

    candidate_ids = []
    visual_scores = {}
    for cid, distance in zip(chroma_result["ids"][0], chroma_result["distances"][0]):
        if cid == f"photo_{photo_id}":
            continue
        visual_sim = 1.0 - distance
        photo_id_int = int(cid.replace("photo_", ""))
        candidate_ids.append(photo_id_int)
        visual_scores[photo_id_int] = visual_sim

    if not candidate_ids:
        conn.close()
        return {"anchor": _row_to_dict(anchor_row), "similar": []}

    placeholders = ",".join("?" * len(candidate_ids))
    cur.execute(f"SELECT * FROM photos WHERE id IN ({placeholders})", candidate_ids)
    candidate_rows = cur.fetchall()
    candidates = {row["id"]: dict(row) for row in candidate_rows}

    if exclude_seen and session_id:
        cur.execute(
            "SELECT DISTINCT photo_id FROM events WHERE session_id = ? AND event_type IN ('view', 'click')",
            (session_id,)
        )
        seen_ids = {row[0] for row in cur.fetchall()}
        candidates = {k: v for k, v in candidates.items() if k not in seen_ids}

    conn.close()

    # 強制同品項優先：先取同品項，不足再補其他
    same_cat  = {k: v for k, v in candidates.items() if v.get("category") == anchor.get("category")}
    other_cat = {k: v for k, v in candidates.items() if v.get("category") != anchor.get("category")}

    if len(same_cat) >= max(3, limit // 2):
        pool = same_cat
    else:
        # 同品項不夠時補其他，但同品項排前面
        extra = dict(list(other_cat.items())[: limit - len(same_cat)])
        pool = {**same_cat, **extra}

    scored = []
    for pid, target in pool.items():
        v_score = visual_scores.get(pid, 0)
        a_score = _attribute_sim(anchor, target)
        # 同品項加分
        cat_bonus = 0.3 if target.get("category") == anchor.get("category") else 0.0
        final = weight_visual * v_score + weight_attribute * a_score + cat_bonus
        scored.append((pid, final, target))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:limit]

    similar = []
    for pid, score, target in top:
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
