"""upload.py - 上傳新照片 POST /api/upload（含 CLIP 自動分類）"""
import sys
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, UploadFile, Depends, HTTPException
from api.auth import require_editor

MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # 30 MB per file

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

router = APIRouter(prefix="/api/upload", tags=["upload"])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


@router.post("")
async def upload_photos(files: List[UploadFile] = File(...), _user=Depends(require_editor)):
    """上傳一或多張照片：自動裁切三種尺寸 + CLIP 分類後存入 DB。"""
    from scripts.process_image import process_one, file_hash
    from scripts.classify import classify_one
    from scripts.db_writer import insert_photo, hash_exists

    uploaded = []
    errors = []

    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in ALLOWED_EXT:
            ct = (f.content_type or "").lower()
            if not ct.startswith("image/"):
                errors.append({"filename": f.filename, "error": "不支援的檔案類型"})
                continue

        suffix = ext if ext in ALLOWED_EXT else ".jpg"
        tmp_path = None
        try:
            content = await f.read()
            if len(content) > MAX_UPLOAD_BYTES:
                errors.append({"filename": f.filename, "error": f"檔案超過 30MB 限制"})
                continue
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(content)
                tmp_path = Path(tmp.name)

            h = file_hash(tmp_path)
            if hash_exists(h):
                errors.append({"filename": f.filename, "error": "重複照片"})
                continue

            # 裁切 + 產生三種尺寸
            meta = process_one(tmp_path, precomputed_hash=h)
            meta["original_filename"] = f.filename or meta["filename"]

            # CLIP 分類（M4 MPS 約 1–2 秒/張）
            classification, embedding = classify_one(Path(meta["full_path"]))

            # 寫入 SQLite + ChromaDB
            photo_id = insert_photo(meta, classification, embedding)

            uploaded.append({
                "id":                photo_id,
                "filename":          meta["filename"],
                "original_filename": meta["original_filename"],
                "thumb_url":         f"/api/thumb/{photo_id}",
                "full_url":          f"/static/full/{meta['filename']}",
                "category":          classification.get("category",   {}).get("label"),
                "style":             classification.get("style",      {}).get("label"),
                "color":             classification.get("color",      {}).get("label"),
                "gemstone":          classification.get("gemstone",   {}).get("label"),
                "material":          classification.get("material",   {}).get("label"),
                "stone_shape":       classification.get("stone_shape",{}).get("label"),
                "stone_size":        classification.get("stone_size", {}).get("label"),
                "price_band":        classification.get("price_band", {}).get("label"),
            })

        except Exception as e:
            errors.append({"filename": f.filename, "error": str(e)})
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    return {"uploaded": uploaded, "errors": errors, "count": len(uploaded)}
