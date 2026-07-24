"""similar.py - 找相似
優先用 CLIP 視覺向量（ChromaDB，匯入時就算好的 embeddings），
向量不可用時退回標籤比對（同品項 → 鑽石款式 → 價格帶）。"""
import sqlite3
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

router = APIRouter(prefix="/api/photos", tags=["similar"])


def _vector_similar_ids(photo_id: int, n: int):
    """用 ChromaDB 向量找視覺相似的 photo_id 列表（近→遠）。失敗回 None。"""
    try:
        from scripts.db_writer import get_chroma_collection
        col = get_chroma_collection()
        got = col.get(ids=[f"photo_{photo_id}"], include=["embeddings"])
        embs = got.get("embeddings")
        if embs is None or len(embs) == 0:
            return None
        res = col.query(query_embeddings=[embs[0]], n_results=n + 1)
        ids = (res.get("ids") or [[]])[0]
        out = []
        for cid in ids:
            try:
                pid = int(str(cid).replace("photo_", ""))
            except ValueError:
                continue
            if pid != photo_id:
                out.append(pid)
        return out or None
    except Exception:
        return None

def _conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _photo_url(d: dict) -> str:
    full_path = d.get("full_path") or "" if isinstance(d, dict) else (d["full_path"] or "")
    if "02_classified" in str(full_path):
        from config.settings import BASE_DIR
        classified_dir = str(BASE_DIR / "data" / "02_classified")
        rel = str(full_path).replace(classified_dir, "").lstrip("/\\")
        if rel and not rel.endswith(('.jpg','.jpeg','.png','.webp')):
            rel += ".jpg"
        if rel:
            return f"/static/classified/{rel}"
    return f"/static/full/{d['filename']}"

def _to_dict(row) -> dict:
    d = dict(row)
    url = _photo_url(d)
    return {
        "id":         d["id"],
        "filename":   d["filename"],
        "micro_url":  f"/api/thumb/{d['id']}",
        "thumb_url":  f"/api/thumb/{d['id']}",
        "full_url":   url,
        "category":   d.get("category"),
        "style":      d.get("style"),
        "material":   d.get("material"),
        "gemstone":   d.get("gemstone"),
        "color":      d.get("color"),
        "price_band": d.get("price_band"),
    }

@router.get("/{photo_id}/similar")
def find_similar(
    photo_id: int,
    limit: int = Query(12, ge=1, le=50),
):
    conn = _conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM photos WHERE id = ?", (photo_id,))
    anchor_row = cur.fetchone()
    if not anchor_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Photo not found")
    anchor = dict(anchor_row)

    # ── 第一優先：CLIP 視覺向量（真的「長得像」，不只是標籤相同） ──
    vec_ids = _vector_similar_ids(photo_id, limit * 3)
    if vec_ids:
        placeholders = ",".join("?" * len(vec_ids))
        cur.execute(
            f"SELECT * FROM photos WHERE id IN ({placeholders})"
            "  AND (photo_type = ? OR (? IS NULL AND photo_type IS NULL))",
            vec_ids + [anchor.get("photo_type"), anchor.get("photo_type")],
        )
        by_id = {r["id"]: r for r in cur.fetchall()}
        ordered = [by_id[pid] for pid in vec_ids if pid in by_id][:limit]
        if len(ordered) >= min(3, limit):
            conn.close()
            return {
                "anchor": _to_dict(anchor_row),
                "similar": [_to_dict(r) for r in ordered],
                "mode": "vector",
            }

    # ── 備援：標籤比對 ──
    # 相似分：gemstone +3, style +2, color +2, setting_amount +2, material +1, price_band +1
    cur.execute(
        """
        SELECT *,
          (CASE WHEN gemstone    = ? AND gemstone    IS NOT NULL AND gemstone    != '' THEN 3 ELSE 0 END
         + CASE WHEN style       = ? AND style       IS NOT NULL AND style       != '' THEN 2 ELSE 0 END
         + CASE WHEN color       = ? AND color       IS NOT NULL AND color       != '' THEN 2 ELSE 0 END
         + CASE WHEN setting_amount = ? AND setting_amount IS NOT NULL AND setting_amount != '' THEN 2 ELSE 0 END
         + CASE WHEN material    = ? AND material    IS NOT NULL AND material    != '' THEN 1 ELSE 0 END
         + CASE WHEN price_band  = ? AND price_band  IS NOT NULL AND price_band  != '' THEN 1 ELSE 0 END
          ) AS sim_score
        FROM photos
        WHERE category = ? AND id != ?
          AND (photo_type = ? OR (? IS NULL AND photo_type IS NULL))
        ORDER BY sim_score DESC, RANDOM()
        """,
        (
            anchor.get("gemstone")    or "",
            anchor.get("style")       or "",
            anchor.get("color")       or "",
            anchor.get("setting_amount") or "",
            anchor.get("material")    or "",
            anchor.get("price_band")  or "",
            anchor.get("category"),
            photo_id,
            anchor.get("photo_type"),
            anchor.get("photo_type"),
        ),
    )
    rows = cur.fetchall()
    conn.close()

    similar = [_to_dict(r) for r in rows[:limit]]
    return {
        "anchor": _to_dict(anchor_row),
        "similar": similar,
        "mode": "label",
    }


# ── 以圖搜款：上傳參考圖 → CLIP 向量 → 找照片庫裡視覺最像的款 ──
from fastapi import UploadFile, File, Depends
from api.auth import require_auth


@router.post("/search-by-image")
async def search_by_image(
    file: UploadFile = File(...),
    limit: int = Query(12, ge=1, le=30),
    _user=Depends(require_auth),  # 任何登入者（含來賓 viewer）皆可，唯讀搜尋
):
    import tempfile, os

    suffix = Path(file.filename or "ref.jpg").suffix or ".jpg"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)

        # CLIP 向量（跟匯入同一顆模型；第一次呼叫需載入模型，Mac 上約數秒）
        try:
            from scripts.classify import embed_image
            embedding = embed_image(tmp_path)
        except Exception as e:
            raise HTTPException(503, f"CLIP 模型不可用：{e}")

        try:
            from scripts.db_writer import get_chroma_collection
            col = get_chroma_collection()
            res = col.query(query_embeddings=[embedding], n_results=limit * 2)
        except Exception as e:
            raise HTTPException(503, f"向量庫不可用：{e}")

        ids_raw   = (res.get("ids") or [[]])[0]
        dists_raw = (res.get("distances") or [[]])[0]
        pid_dist = []
        for cid, dist in zip(ids_raw, dists_raw):
            try:
                pid_dist.append((int(str(cid).replace("photo_", "")), dist))
            except ValueError:
                continue
        if not pid_dist:
            return {"results": [], "count": 0}

        conn = _conn()
        placeholders = ",".join("?" * len(pid_dist))
        rows = conn.execute(
            f"SELECT * FROM photos WHERE id IN ({placeholders})",
            [pid for pid, _ in pid_dist],
        ).fetchall()
        conn.close()
        by_id = {r["id"]: r for r in rows}

        results = []
        for pid, dist in pid_dist:
            if pid in by_id:
                d = _to_dict(by_id[pid])
                # cosine distance → 相似度百分比（僅供陳列參考）
                d["similarity"] = round(max(0.0, 1.0 - dist) * 100)
                results.append(d)
            if len(results) >= limit:
                break
        return {"results": results, "count": len(results)}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
