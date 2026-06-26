"""upload.py - 直接上傳 + Gemini Flash 即時分類 → 暫存審核佇列"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, UploadFile, Depends, HTTPException
from api.auth import require_editor

MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # 30 MB

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, STAGING_DIR

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

router = APIRouter(prefix="/api/upload", tags=["upload"])

STAGING_DIR.mkdir(parents=True, exist_ok=True)


def _db():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.post("")
async def upload_and_classify(
    files: List[UploadFile] = File(...),
    folder_name: Optional[str] = Form(None),  # 客製訂單資料夾名稱
    _user=Depends(require_editor),
):
    """
    上傳一或多張照片，用 Gemini Flash 即時分類，存入 staging_queue 等待審核。
    folder_name 非空 → 視為同一件客製品的多角度（is_custom_order=1）。
    """
    from scripts.process_image import process_one, file_hash
    from scripts.classify_gemini import classify_image, confidence_color

    is_custom = 1 if folder_name else 0
    results = []
    errors = []

    # 多角度客製：先把所有圖存起來，再一起送 Gemini
    tmp_paths = []
    valid_files = []

    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in ALLOWED_EXT:
            ct = (f.content_type or "").lower()
            if not ct.startswith("image/"):
                errors.append({"filename": f.filename, "error": "不支援的檔案類型"})
                continue
        suffix = ext if ext in ALLOWED_EXT else ".jpg"
        try:
            content = await f.read()
            if len(content) > MAX_UPLOAD_BYTES:
                errors.append({"filename": f.filename, "error": "檔案超過 30MB"})
                continue
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(content)
                tmp_paths.append(Path(tmp.name))
            valid_files.append(f.filename or f"photo{len(tmp_paths)}{suffix}")
        except Exception as e:
            errors.append({"filename": f.filename, "error": str(e)})

    if not tmp_paths:
        return {"uploaded": [], "errors": errors, "count": 0}

    try:
        # 客製多角度：主圖用第一張，其餘作為輔助角度
        main_tmp = tmp_paths[0]
        extra_tmps = tmp_paths[1:] if is_custom else []

        # Gemini 分類（一次看所有角度）
        classification = classify_image(main_tmp, extra_images=extra_tmps)

        # 每張分別處理 + 寫入 staging_queue
        conn = _db()
        for i, (tmp_path, orig_name) in enumerate(zip(tmp_paths, valid_files)):
            try:
                h = file_hash(tmp_path)

                # 檢查是否重複
                dup = conn.execute("SELECT id FROM photos WHERE file_hash=?", (h,)).fetchone()
                if dup:
                    errors.append({"filename": orig_name, "error": "重複照片，已在系統中"})
                    continue

                # 處理圖片（生成三種尺寸）
                meta = process_one(tmp_path, precomputed_hash=h)
                meta["original_filename"] = orig_name

                # 寫入 staging_queue（含信心分數）
                low_fields = classification["low_confidence_fields"] if i == 0 else []
                needs_review = 1 if low_fields else 0

                conn.execute("""
                    INSERT OR IGNORE INTO staging_queue (
                        source_path, original_filename, filename,
                        full_path, thumb_path, micro_path,
                        file_hash, file_size, width, height,
                        folder_name, is_custom_order,
                        category,         category_confidence,
                        color,            color_confidence,
                        gemstone,         gemstone_confidence,
                        stone_shape,      stone_shape_confidence,
                        stone_size,       stone_size_confidence,
                        material,         material_confidence,
                        metal_color,      metal_color_confidence,
                        metal_weight,     metal_weight_confidence,
                        style,            style_confidence,
                        setting_amount,   setting_amount_confidence,
                        craft_complexity, craft_complexity_confidence,
                        photo_type,       photo_type_confidence,
                        price_band,       price_band_confidence,
                        low_confidence_fields, needs_review
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    meta.get("original_path", str(tmp_path)), orig_name, meta["filename"],
                    meta["full_path"], meta["thumb_path"], meta["micro_path"],
                    meta["file_hash"], meta["file_size"], meta["width"], meta["height"],
                    folder_name, is_custom,
                    classification["category"],         classification["category_confidence"],
                    classification["color"],            classification["color_confidence"],
                    classification["gemstone"],         classification["gemstone_confidence"],
                    classification["stone_shape"],      classification["stone_shape_confidence"],
                    classification["stone_size"],       classification["stone_size_confidence"],
                    classification["material"],         classification["material_confidence"],
                    classification["metal_color"],      classification["metal_color_confidence"],
                    classification["metal_weight"],     classification["metal_weight_confidence"],
                    classification["style"],            classification["style_confidence"],
                    classification["setting_amount"],   classification["setting_amount_confidence"],
                    classification["craft_complexity"], classification["craft_complexity_confidence"],
                    classification["photo_type"],       classification["photo_type_confidence"],
                    classification["price_band"],       classification["price_band_confidence"],
                    json.dumps(low_fields, ensure_ascii=False), needs_review,
                ))
                conn.commit()

                item_id = conn.execute(
                    "SELECT id FROM staging_queue WHERE file_hash=?", (h,)
                ).fetchone()["id"]

                # 回傳給前端的分類結果（含信心顏色）
                fields_info = {}
                for field in ["category","color","gemstone","stone_shape","stone_size",
                               "material","metal_color","metal_weight","style","setting_amount",
                               "craft_complexity","photo_type","price_band"]:
                    conf = classification.get(f"{field}_confidence", 0)
                    fields_info[field] = {
                        "label": classification.get(field),
                        "confidence": conf,
                        "color": confidence_color(field, conf),
                    }

                results.append({
                    "id": item_id,
                    "original_filename": orig_name,
                    "thumb_url": f"/api/staging/queue/thumb/{item_id}",
                    "fields": fields_info,
                    "needs_review": bool(low_fields),
                    "low_confidence_fields": low_fields,
                    "folder_name": folder_name,
                })

            except Exception as e:
                errors.append({"filename": orig_name, "error": str(e)})

        conn.close()

    finally:
        for p in tmp_paths:
            p.unlink(missing_ok=True)

    return {
        "uploaded": results,
        "errors": errors,
        "count": len(results),
        "needs_review_count": sum(1 for r in results if r["needs_review"]),
    }
