"""photos.py - /api/photos 列表 + 單張詳細"""
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel
from api.auth import require_editor, require_admin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, BASE_DIR

CAT_LABELS_FILE   = BASE_DIR / "data" / "training_labels.json"
STYLE_LABELS_FILE = BASE_DIR / "data" / "training_labels_style.json"
CHAIN_LABELS_FILE  = BASE_DIR / "data" / "training_labels_chain.json"
CRAFT_LABELS_FILE  = BASE_DIR / "data" / "training_labels_craft.json"


def _save_label(photo_id: int, field: str, value: str):
    """把 UI 手動修正存回訓練標記檔，讓 KNN 越用越準。"""
    if field == "category":
        path = CAT_LABELS_FILE
    elif field == "style":
        path = STYLE_LABELS_FILE
    elif field == "setting_amount":
        path = CHAIN_LABELS_FILE
    elif field == "craft_complexity":
        path = CRAFT_LABELS_FILE
    else:
        return
    try:
        labels = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        labels[str(photo_id)] = value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # 不因儲存失敗中斷主流程

router = APIRouter(prefix="/api/photos", tags=["photos"])

PAGE_SIZE = 9

def _conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _safe(row, key, default=None):
    try:
        return row[key]
    except (IndexError, KeyError):
        return default

def _photo_url(row) -> str:
    try:
        full_path = row["full_path"] or ""
    except (IndexError, KeyError):
        full_path = ""
    if "02_classified" in str(full_path):
        from config.settings import BASE_DIR
        classified_dir = str(BASE_DIR / "data" / "02_classified")
        rel = str(full_path).replace(classified_dir, "").lstrip("/\\")
        if rel:
            return f"/static/classified/{rel}"
    return f"/static/full/{row['filename']}"

def _row_to_dict(row) -> dict:
    url   = _photo_url(row)
    thumb = f"/api/thumb/{row['id']}"
    return {
        "id":                  row["id"],
        "filename":            row["filename"],
        "micro_url":           thumb,
        "thumb_url":           thumb,
        "full_url":            url,
        "color":               row["color"],
        "category":            row["category"],
        "material":            row["material"],
        "gemstone":            row["gemstone"],
        "style":               _safe(row, "style"),
        "stone_shape":         _safe(row, "stone_shape"),
        "stone_size":          _safe(row, "stone_size"),
        "diamond_status":      _safe(row, "diamond_status"),
        "setting_amount":         _safe(row, "setting_amount"),
        "craft_complexity":       _safe(row, "craft_complexity"),
        "metal_color":            _safe(row, "metal_color"),
        "photo_type":          _safe(row, "photo_type"),
        "price_band":          row["price_band"],
        "price_estimate_low":  row["price_estimate_low"],
        "price_estimate_high": row["price_estimate_high"],
        "price_source":        row["price_source"],
        "view_count":          row["view_count"],
        "favorite_count":      row["favorite_count"],
    }

@router.get("")
def list_photos(
    color:        Optional[str] = None,
    category:     Optional[str] = None,
    material:     Optional[str] = None,
    diamond_status: Optional[str] = None,
    gemstone:     Optional[str] = None,
    price_band:   Optional[str] = None,
    style:        Optional[str] = None,
    stone_shape:  Optional[str] = None,
    stone_size:   Optional[str] = None,
    metal_color:  Optional[str] = None,
    photo_type:   Optional[str] = None,
    page:         int = Query(1, ge=1),
    sort:         str = Query("random", pattern="^(random|newest|popular)$"),
    exclude_seen: bool = False,
    session_id:   Optional[str] = None,
):
    wheres = []
    params = []

    def add_in(field: str, value: Optional[str]):
        if value:
            items = [v.strip() for v in value.split(",") if v.strip()]
            if items:
                placeholders = ",".join("?" * len(items))
                wheres.append(f"{field} IN ({placeholders})")
                params.extend(items)

    add_in("color",          color)
    # 查「其他」時同時包含「未定」，避免未定照片消失
    if category == "其他":
        wheres.append("(category IN ('其他','未定') OR category IS NULL)")
    else:
        add_in("category", category)
    add_in("material",       material)
    add_in("diamond_status", diamond_status)
    add_in("gemstone",       gemstone)
    add_in("price_band",     price_band)
    add_in("style",          style)
    add_in("stone_shape",    stone_shape)
    add_in("stone_size",     stone_size)
    add_in("metal_color",    metal_color)
    add_in("photo_type",     photo_type)

    if exclude_seen and session_id:
        wheres.append(
            "id NOT IN (SELECT DISTINCT photo_id FROM events WHERE session_id = ? AND event_type IN ('view', 'click'))"
        )
        params.append(session_id)

    where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    if sort == "random":
        # 去背照片排前，情境照片排後，各組內隨機
        order_clause = "ORDER BY CASE WHEN photo_type = '去背' THEN 0 ELSE 1 END, RANDOM()"
    elif sort == "newest":
        order_clause = "ORDER BY created_at DESC"
    elif sort == "popular":
        order_clause = "ORDER BY (view_count + favorite_count * 3 + lock_count * 5) DESC"
    else:
        order_clause = "ORDER BY id"

    offset = (page - 1) * PAGE_SIZE

    conn = _conn()
    cur = conn.cursor()

    cur.execute(f"SELECT COUNT(*) FROM photos {where_clause}", params)
    total = cur.fetchone()[0]

    cur.execute(
        f"SELECT * FROM photos {where_clause} {order_clause} LIMIT ? OFFSET ?",
        params + [PAGE_SIZE, offset]
    )
    rows = cur.fetchall()
    conn.close()

    photos = [_row_to_dict(r) for r in rows]
    return {
        "photos":   photos,
        "total":    total,
        "page":     page,
        "has_more": offset + len(photos) < total,
    }

@router.get("/category-counts")
def category_counts():
    """回傳各 category 的照片數量"""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT category, COUNT(*) as cnt FROM photos WHERE category IS NOT NULL AND category != '' GROUP BY category")
    rows = cur.fetchall()
    conn.close()
    return {r["category"]: r["cnt"] for r in rows}

@router.get("/filter-counts")
def filter_counts(
    category:    Optional[str] = None,
    style:       Optional[str] = None,
    color:       Optional[str] = None,
    metal_color: Optional[str] = None,
    gemstone:    Optional[str] = None,
    stone_shape: Optional[str] = None,
    stone_size:  Optional[str] = None,
    price_band:  Optional[str] = None,
    photo_type:  Optional[str] = None,
):
    """根據目前已選篩選器，回傳各維度每個值的照片數量（faceted counts）。"""
    CFG_VALS = {
        "category":    ['戒指','耳釘','手鏈','項鍊','胸針','其他'],
        "style":       ['無鑽','簡約','輕奢','奢華'],
        "gemstone":    ['鑽石','紅寶石','藍寶石','祖母綠','坦桑石','海藍寶','碧璽','紫水晶','黃水晶','月光石','歐泊','橄欖石','石榴石','珍珠','翡翠','托帕石','尖晶石','其他彩寶','無寶石'],
        "stone_shape": ['橢圓形','圓形','水滴形','心形','方形','長方形','馬眼形','枕形','梨形','三角形','花形','不規則','無主石'],
        "stone_size":  ['1克拉以內','1克拉','2克拉','3克拉','5克拉','10克拉','10克拉以上'],
        "color":       ['紅','粉','黃','綠','藍','紫','白','彩'],
        "metal_color": ['金','銀'],
        "price_band":  ['入門','中階','高階','奢華','頂級'],
    }
    # photo_type 不列入 facet，但納入每個欄位的計數條件
    base_filter = {"photo_type": photo_type} if photo_type else {}
    active = {
        **base_filter,
        "category": category, "style": style, "color": color, "metal_color": metal_color,
        "gemstone": gemstone, "stone_shape": stone_shape, "stone_size": stone_size,
        "price_band": price_band,
    }
    conn = _conn()
    result = {}
    for field, values in CFG_VALS.items():
        others = {k: v for k, v in active.items() if k != field and v}
        counts = {}
        if others:
            where = " AND ".join(f"{k} = ?" for k in others)
            base_params = list(others.values())
            for val in values:
                counts[val] = conn.execute(
                    f"SELECT COUNT(*) FROM photos WHERE {where} AND {field} = ?",
                    base_params + [val]
                ).fetchone()[0]
        else:
            for val in values:
                counts[val] = conn.execute(
                    f"SELECT COUNT(*) FROM photos WHERE {field} = ?", [val]
                ).fetchone()[0]
        result[field] = counts
    conn.close()
    return result

def _is_dark_bg(thumb_path: str, threshold: int = 45) -> bool:
    """取縮圖四個角落 20x20 px，平均亮度低於 threshold 就視為黑底。"""
    try:
        from PIL import Image
        p = Path(thumb_path)
        if not p.exists():
            return False
        img = Image.open(p).convert("RGB")
        w, h = img.size
        sz = min(20, w // 4, h // 4)
        corners = [
            img.crop((0, 0, sz, sz)),
            img.crop((w - sz, 0, w, sz)),
            img.crop((0, h - sz, sz, h)),
            img.crop((w - sz, h - sz, w, h)),
        ]
        pixels = []
        for c in corners:
            pixels.extend(list(c.getdata()))
        brightness = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in pixels) / len(pixels)
        return brightness < threshold
    except Exception:
        return False


@router.get("/dark-bg")
def scan_dark_bg(threshold: int = Query(45, ge=10, le=120)):
    """偵測並回傳黑底照片清單（不刪除）。"""
    conn = _conn()
    rows = conn.execute("SELECT * FROM photos").fetchall()
    conn.close()
    results = [_row_to_dict(row) for row in rows
               if row["thumb_path"] and _is_dark_bg(row["thumb_path"], threshold)]
    return {"photos": results, "count": len(results)}


class BulkDeleteBody(BaseModel):
    ids: List[int]

@router.delete("/bulk")
def bulk_delete(body: BulkDeleteBody, _user=Depends(require_admin)):
    """批次永久刪除照片（含磁碟檔案）。"""
    if not body.ids:
        return {"deleted": []}
    conn = _conn()
    placeholders = ",".join("?" * len(body.ids))
    rows = conn.execute(
        f"SELECT id, full_path, thumb_path, micro_path FROM photos WHERE id IN ({placeholders})",
        body.ids
    ).fetchall()
    conn.execute(f"DELETE FROM photos WHERE id IN ({placeholders})", body.ids)
    conn.commit()
    conn.close()
    for row in rows:
        for col in ("full_path", "thumb_path", "micro_path"):
            p = row[col]
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass
    return {"deleted": [r["id"] for r in rows]}


@router.get("/{photo_id}")
def get_photo(photo_id: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM photos WHERE id = ?", (photo_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")
    return _row_to_dict(row)

@router.patch("/{photo_id}")
def update_photo(photo_id: int, body: dict, _user=Depends(require_editor)):
    allowed = {"category", "style", "setting_amount", "craft_complexity", "metal_color", "color", "gemstone", "material", "price_band"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields")
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [photo_id]
    conn = _conn()
    conn.execute(f"UPDATE photos SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id=?", values)
    conn.commit()
    cur = conn.cursor()
    cur.execute("SELECT * FROM photos WHERE id = ?", (photo_id,))
    row = cur.fetchone()
    conn.close()
    # 把手動修正存回訓練標記，讓 KNN 越用越準
    for field in ("category", "style", "setting_amount", "craft_complexity"):
        if field in updates and updates[field]:
            _save_label(photo_id, field, updates[field])
    return _row_to_dict(row)


class BatchUpdateBody(BaseModel):
    ids: list
    updates: dict


@router.patch("/batch/update")
def batch_update_photos(body: BatchUpdateBody, _user=Depends(require_editor)):
    allowed = {"category", "style", "setting_amount", "craft_complexity", "metal_color", "color", "gemstone", "material", "price_band"}
    updates = {k: v for k, v in body.updates.items() if k in allowed}
    if not updates or not body.ids:
        raise HTTPException(status_code=400, detail="No valid fields or ids")
    set_clause = ", ".join(f"{k}=?" for k in updates)
    placeholders = ",".join("?" * len(body.ids))
    values = list(updates.values()) + list(body.ids)
    conn = _conn()
    conn.execute(
        f"UPDATE photos SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
        values
    )
    conn.commit()
    conn.close()
    return {"updated": len(body.ids)}


def delete_photo(photo_id: int, _user=Depends(require_admin)):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT full_path FROM photos WHERE id = ?", (photo_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Photo not found")
    conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    conn.commit()
    conn.close()
    # 刪除磁碟上的實際檔案
    if row["full_path"]:
        try:
            Path(row["full_path"]).unlink(missing_ok=True)
        except Exception:
            pass
    return {"deleted": photo_id}
