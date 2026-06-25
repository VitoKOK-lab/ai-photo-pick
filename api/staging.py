"""staging.py - 預看 01_unsorted/ 待匯入 + 暫存審核佇列"""
import io
import json
import sqlite3
import sys
import threading
from datetime import date
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
from api.auth import require_editor, require_admin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import UNSORTED_DIR, STAGING_DIR, SQLITE_PATH

VALID_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
router = APIRouter(prefix="/api/staging", tags=["staging"])

STAGING_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────
# 既有 01_unsorted 預覽與匯入（保留不動）
# ─────────────────────────────────────────────────────────────

def _list_files():
    return sorted([
        p for p in UNSORTED_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in VALID_EXT
    ])


@router.get("")
def list_staging():
    files = _list_files()
    return {
        "count": len(files),
        "files": [
            {"rel": str(p.relative_to(UNSORTED_DIR)), "name": p.name, "size": p.stat().st_size}
            for p in files
        ],
    }


@router.get("/thumb/{rel_path:path}")
def staging_thumb(rel_path: str, size: int = 300):
    p = (UNSORTED_DIR / rel_path).resolve()
    if not p.is_relative_to(UNSORTED_DIR.resolve()):
        raise HTTPException(status_code=400, detail="非法路徑")
    if not p.exists() or not p.is_file() or p.suffix.lower() not in VALID_EXT:
        raise HTTPException(status_code=404)
    try:
        from PIL import Image
        img = Image.open(p).convert("RGB")
        img.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=78)
        return Response(content=buf.getvalue(), media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{rel_path:path}")
def delete_staging(rel_path: str, _user=Depends(require_admin)):
    p = (UNSORTED_DIR / rel_path).resolve()
    if not p.is_relative_to(UNSORTED_DIR.resolve()):
        raise HTTPException(status_code=400, detail="非法路徑")
    if not p.exists():
        raise HTTPException(status_code=404)
    p.unlink(missing_ok=True)
    parent = p.parent
    if parent != UNSORTED_DIR:
        try:
            parent.rmdir()
        except OSError:
            pass
    return {"deleted": rel_path}


_status: dict = {"running": False, "done": False, "step": "", "ok": 0, "err": 0, "log": []}
_lock = threading.Lock()


@router.get("/ingest-status")
def get_ingest_status():
    return dict(_status)


@router.post("/ingest")
def start_ingest(_user=Depends(require_admin)):
    with _lock:
        if _status["running"]:
            return {"message": "已在執行中", "status": dict(_status)}
        pending = len(_list_files())
        if pending == 0:
            return {"message": "沒有待匯入照片"}
        _status.update({"running": True, "done": False, "step": "準備中…", "ok": 0, "err": 0, "log": []})

    t = threading.Thread(target=_run_ingest, daemon=True)
    t.start()
    return {"message": f"開始匯入 {pending} 張", "status": dict(_status)}


def _log(msg: str):
    _status["log"].append(msg)
    if len(_status["log"]) > 200:
        _status["log"] = _status["log"][-200:]


def _run_ingest():
    try:
        from scripts.full_ingest import (
            step0_dedup, step1_batch, step2_remove_empty_dirs,
            step3_reclassify, step4_photo_type,
        )
        _status["step"] = "去重複檢查…"; step0_dedup()
        _status["step"] = "批次匯入 + CLIP 分類…"; step1_batch()
        _status["step"] = "清除空資料夾…"; step2_remove_empty_dirs()
        _status["step"] = "補齊缺漏標籤…"; step3_reclassify()
        _status["step"] = "偵測照片類型…"; step4_photo_type()
        _status["step"] = "完成"; _status["done"] = True
    except Exception as e:
        _status["step"] = f"錯誤：{e}"; _log(f"ERROR: {e}")
    finally:
        _status["running"] = False


# ─────────────────────────────────────────────────────────────
# 暫存審核佇列 (00_staging → staging_queue → photos)
# ─────────────────────────────────────────────────────────────

def _db():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _list_staging_files():
    return sorted([
        p for p in STAGING_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in VALID_EXT
    ])


@router.get("/queue")
def queue_list(_user=Depends(require_admin)):
    conn = _db()
    rows = conn.execute("SELECT * FROM staging_queue ORDER BY staged_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/queue/thumb/{item_id}")
def queue_thumb(item_id: int):
    conn = _db()
    row = conn.execute("SELECT thumb_path, source_path FROM staging_queue WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404)
    # try thumb_path first, fall back to source
    for path_str in [row["thumb_path"], row["source_path"]]:
        if path_str:
            p = Path(path_str)
            if p.exists():
                try:
                    from PIL import Image
                    img = Image.open(p).convert("RGB")
                    img.thumbnail((300, 300), Image.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, "JPEG", quality=78)
                    return Response(content=buf.getvalue(), media_type="image/jpeg")
                except Exception:
                    continue
    raise HTTPException(status_code=404)


class QueuePatch(BaseModel):
    category: Optional[str] = None
    color: Optional[str] = None
    gemstone: Optional[str] = None
    stone_shape: Optional[str] = None
    stone_size: Optional[str] = None
    material: Optional[str] = None
    metal_color: Optional[str] = None
    style: Optional[str] = None
    setting_amount: Optional[str] = None
    craft_complexity: Optional[str] = None
    photo_type: Optional[str] = None
    is_custom_order: Optional[int] = None
    display_name: Optional[str] = None


@router.patch("/queue/{item_id}")
def queue_update(item_id: int, body: QueuePatch, _user=Depends(require_admin)):
    fields = {k: v for k, v in body.dict().items() if v is not None}
    if not fields:
        return {"ok": True}
    set_clause = ", ".join(f"{k}=?" for k in fields)
    conn = _db()
    conn.execute(f"UPDATE staging_queue SET {set_clause} WHERE id=?", (*fields.values(), item_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.delete("/queue/{item_id}")
def queue_delete(item_id: int, _user=Depends(require_admin)):
    conn = _db()
    row = conn.execute("SELECT source_path FROM staging_queue WHERE id=?", (item_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404)
    conn.execute("DELETE FROM staging_queue WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    # optionally delete source file
    src = Path(row["source_path"])
    if src.exists() and src.is_relative_to(STAGING_DIR):
        src.unlink(missing_ok=True)
    return {"deleted": item_id}


@router.post("/queue/{item_id}/import")
def queue_import_one(item_id: int, _user=Depends(require_admin)):
    conn = _db()
    row = conn.execute("SELECT * FROM staging_queue WHERE id=?", (item_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404)
    row = dict(row)
    conn.close()

    if not row.get("filename"):
        raise HTTPException(status_code=400, detail="尚未完成掃描")

    try:
        _do_import(row)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # remove from queue
    conn = _db()
    conn.execute("DELETE FROM staging_queue WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "filename": row["filename"]}


@router.post("/queue/import-all")
def queue_import_all(_user=Depends(require_admin)):
    conn = _db()
    rows = conn.execute("SELECT * FROM staging_queue WHERE filename IS NOT NULL").fetchall()
    conn.close()
    ok, errors = 0, []
    for row in [dict(r) for r in rows]:
        try:
            _do_import(row)
            conn = _db()
            conn.execute("DELETE FROM staging_queue WHERE id=?", (row["id"],))
            conn.commit()
            conn.close()
            ok += 1
        except Exception as e:
            errors.append({"id": row["id"], "error": str(e)})
    return {"ok": ok, "errors": errors}


def _do_import(row: dict):
    """Insert a staging_queue row into the main photos table with added_date + is_custom_order."""
    from scripts.db_writer import get_chroma_collection

    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO photos (
            filename, original_filename, original_path,
            full_path, thumb_path, micro_path,
            color, category, material, gemstone,
            stone_shape, stone_size, metal_color,
            style, setting_amount, craft_complexity, photo_type,
            file_hash, file_size, width, height,
            added_date, is_custom_order
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        row["filename"], row["original_filename"], row["source_path"],
        row["full_path"], row["thumb_path"], row["micro_path"],
        row.get("color"), row.get("category"), row.get("material"), row.get("gemstone"),
        row.get("stone_shape"), row.get("stone_size"), row.get("metal_color"),
        row.get("style"), row.get("setting_amount"), row.get("craft_complexity"),
        row.get("photo_type"), row.get("file_hash"), row.get("file_size"),
        row.get("width"), row.get("height"),
        _get_exif_date(row.get("source_path") or row.get("full_path", "")),
        row.get("is_custom_order", 0),
    ))
    photo_id = cur.lastrowid

    # insert embedding into chromadb
    if row.get("embedding_json"):
        try:
            embedding = json.loads(row["embedding_json"])
            col = get_chroma_collection()
            col.add(
                ids=[f"photo_{photo_id}"],
                embeddings=[embedding],
                metadatas=[{"photo_id": photo_id, "filename": row["filename"]}],
            )
        except Exception:
            pass  # chromadb not critical

    conn.commit()
    conn.close()

    # delete source file
    src = Path(row["source_path"])
    if src.exists() and src.is_relative_to(STAGING_DIR):
        src.unlink(missing_ok=True)


# ── 掃描 00_staging/ 並執行 CLIP 分類 ───────────────────────

_scan_status: dict = {"running": False, "done": 0, "total": 0, "step": ""}
_scan_lock = threading.Lock()


@router.get("/queue/scan-status")
def scan_status(_user=Depends(require_admin)):
    return dict(_scan_status)


@router.post("/queue/scan")
def queue_scan(_user=Depends(require_admin)):
    with _scan_lock:
        if _scan_status["running"]:
            return {"message": "掃描中，請稍候"}
        files = _list_staging_files()
        if not files:
            return {"message": "00_staging/ 內沒有照片"}

        # filter already queued
        conn = _db()
        existing = {r[0] for r in conn.execute("SELECT source_path FROM staging_queue").fetchall()}
        conn.close()
        new_files = [f for f in files if str(f) not in existing]
        if not new_files:
            return {"message": "所有照片都已在佇列中了"}

        _scan_status.update({"running": True, "done": 0, "total": len(new_files), "step": "準備中…"})

    t = threading.Thread(target=_run_scan, args=(new_files,), daemon=True)
    t.start()
    return {"message": f"開始掃描 {len(new_files)} 張", "total": len(new_files)}


def _get_exif_date(path) -> str:
    """Return EXIF DateTimeOriginal as YYYY-MM-DD, or today's date as fallback."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        img = Image.open(path)
        exif = img._getexif()
        if exif:
            for tag_id, val in exif.items():
                if TAGS.get(tag_id) == "DateTimeOriginal" and isinstance(val, str):
                    return val[:10].replace(":", "-")
    except Exception:
        pass
    from datetime import date as _date
    return _date.today().isoformat()


def _run_scan(files: list):
    try:
        from scripts.process_image import process_one, file_hash
        from scripts.classify import classify_one

        for i, src in enumerate(files):
            _scan_status["step"] = f"處理 {src.name} ({i+1}/{len(files)})"
            try:
                h = file_hash(src)
                # check duplicate in main photos
                conn = _db()
                dup = conn.execute("SELECT id FROM photos WHERE file_hash=?", (h,)).fetchone()
                conn.close()
                if dup:
                    _scan_status["done"] += 1
                    continue

                # detect custom order: files in a subdirectory = custom order
                rel_parent = src.parent.relative_to(STAGING_DIR)
                folder_name = str(rel_parent) if str(rel_parent) != "." else None
                is_custom = 1 if folder_name else 0

                metadata = process_one(src)
                full_path = Path(metadata["full_path"])
                classification, embedding = classify_one(full_path)

                conn = _db()
                conn.execute("""
                    INSERT OR IGNORE INTO staging_queue (
                        source_path, original_filename, filename,
                        full_path, thumb_path, micro_path,
                        file_hash, file_size, width, height,
                        category, color, gemstone, stone_shape, stone_size,
                        material, metal_color, style, setting_amount,
                        craft_complexity, photo_type, embedding_json,
                        folder_name, is_custom_order
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    str(src), metadata["original_filename"], metadata["filename"],
                    metadata["full_path"], metadata["thumb_path"], metadata["micro_path"],
                    metadata["file_hash"], metadata["file_size"],
                    metadata["width"], metadata["height"],
                    classification["category"]["label"],
                    classification["color"]["label"],
                    classification["gemstone"]["label"],
                    classification["stone_shape"]["label"],
                    classification["stone_size"]["label"],
                    classification["material"]["label"],
                    classification.get("metal_color", {}).get("label"),
                    classification.get("style", {}).get("label"),
                    classification.get("setting_amount", {}).get("label"),
                    classification.get("craft_complexity", {}).get("label"),
                    classification.get("photo_type", {}).get("label"),
                    json.dumps(embedding),
                    folder_name, is_custom,
                ))
                conn.commit()
                conn.close()
            except Exception as e:
                _scan_status["step"] = f"錯誤 {src.name}: {e}"
            _scan_status["done"] += 1

        _scan_status["step"] = "完成"
    finally:
        _scan_status["running"] = False
