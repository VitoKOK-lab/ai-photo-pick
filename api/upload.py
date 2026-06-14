"""upload.py - 上傳新照片 POST /api/upload"""
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, UploadFile, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

router = APIRouter(prefix="/api/upload", tags=["upload"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


def _conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.post("")
async def upload_photos(files: List[UploadFile] = File(...)):
    """上傳一張或多張照片，自動裁切成三種尺寸並存入 DB。"""
    from scripts.process_image import process_one, file_hash

    uploaded = []
    errors = []

    for f in files:
        ct = (f.content_type or "").lower()
        ext = Path(f.filename or "").suffix.lower()
        if ct not in ALLOWED_TYPES and ext not in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}:
            errors.append({"filename": f.filename, "error": "不支援的檔案類型"})
            continue

        suffix = ext if ext else ".jpg"
        tmp_path = None
        try:
            content = await f.read()
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(content)
                tmp_path = Path(tmp.name)

            h = file_hash(tmp_path)

            conn = _conn()
            dup = conn.execute("SELECT id FROM photos WHERE file_hash=?", (h,)).fetchone()
            if dup:
                conn.close()
                errors.append({"filename": f.filename, "error": "重複照片", "existing_id": dup["id"]})
                continue

            meta = process_one(tmp_path, precomputed_hash=h)
            meta["original_filename"] = f.filename or meta["filename"]

            conn.execute(
                """INSERT INTO photos
                   (filename, original_filename, original_path, full_path,
                    thumb_path, micro_path, file_hash, file_size, width, height)
                   VALUES (:filename, :original_filename, :original_path, :full_path,
                    :thumb_path, :micro_path, :file_hash, :file_size, :width, :height)""",
                meta,
            )
            conn.commit()
            photo_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()

            uploaded.append({
                "id": photo_id,
                "filename": meta["filename"],
                "original_filename": meta["original_filename"],
                "thumb_url": f"/api/thumb/{photo_id}",
                "full_url": f"/static/full/{meta['filename']}",
            })

        except Exception as e:
            errors.append({"filename": f.filename, "error": str(e)})
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    return {"uploaded": uploaded, "errors": errors, "count": len(uploaded)}
