"""process_image.py - 影像處理：備份、裁切、產生三種尺寸"""
import hashlib
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    ORIGINAL_DIR, FULL_DIR, THUMB_DIR, MICRO_DIR,
    FULL_SIZE, THUMB_SIZE, MICRO_SIZE, JPEG_QUALITY
)

# HEIC 支援（iPhone 照片）
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass


def file_hash(path: Path) -> str:
    """算檔案 SHA256"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_filename(original_name: str) -> str:
    """產生系統檔名：YYYYMMDD_<uuid8>.jpg"""
    date_str = datetime.now().strftime("%Y%m%d")
    uid = uuid.uuid4().hex[:8]
    return f"{date_str}_{uid}.jpg"


def crop_square(img: Image.Image) -> Image.Image:
    """裁成正方形（取中心）"""
    w, h = img.size
    if w == h:
        return img
    size = min(w, h)
    left = (w - size) // 2
    top  = (h - size) // 2
    return img.crop((left, top, left + size, top + size))


def _ensure_dirs():
    for d in (ORIGINAL_DIR, FULL_DIR, THUMB_DIR, MICRO_DIR):
        d.mkdir(parents=True, exist_ok=True)


def process_one(source_path: Path, precomputed_hash: Optional[str] = None) -> dict:
    """
    處理單張照片：
    1. 備份原始檔到 02_original/
    2. 產生 1200/400/100 三種尺寸到 03_processed/
    回傳：metadata dict（含 file_hash）

    precomputed_hash：若已算過 hash 可傳入，避免重複 I/O
    """
    _ensure_dirs()

    h = precomputed_hash if precomputed_hash else file_hash(source_path)
    new_name   = generate_filename(source_path.name)
    base_name  = new_name.replace(".jpg", "")

    # 1. 備份原始檔（保留原副檔名）
    original_ext    = source_path.suffix.lower()
    original_target = ORIGINAL_DIR / f"{base_name}{original_ext}"
    shutil.copy2(source_path, original_target)

    # 2. 載入並修正方向（避免 EXIF 旋轉問題）
    img = Image.open(source_path)
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    width, height = img.size

    # 3. 裁正方形
    img_square = crop_square(img)

    # 4. 產生三種尺寸
    img_full  = img_square.resize(FULL_SIZE,  Image.LANCZOS)
    img_thumb = img_square.resize(THUMB_SIZE, Image.LANCZOS)
    img_micro = img_square.resize(MICRO_SIZE, Image.LANCZOS)

    full_path  = FULL_DIR  / new_name
    thumb_path = THUMB_DIR / new_name
    micro_path = MICRO_DIR / new_name

    img_full.save(full_path,   "JPEG", quality=JPEG_QUALITY)
    img_thumb.save(thumb_path, "JPEG", quality=JPEG_QUALITY)
    img_micro.save(micro_path, "JPEG", quality=JPEG_QUALITY)

    return {
        "filename":          new_name,
        "original_filename": source_path.name,
        "original_path":     str(original_target),
        "full_path":         str(full_path),
        "thumb_path":        str(thumb_path),
        "micro_path":        str(micro_path),
        "file_hash":         h,
        "file_size":         source_path.stat().st_size,
        "width":             width,
        "height":            height,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.process_image <image_path>")
        sys.exit(1)
    result = process_one(Path(sys.argv[1]))
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
