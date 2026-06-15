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


def is_white_background(img: Image.Image, white_threshold: int = 235, border_width: int = 8, min_ratio: float = 0.60) -> bool:
    """邊緣像素 60%+ 是白色 → True（去背）"""
    w, h = img.size
    b = min(border_width, w // 6, h // 6)
    top_strip    = img.crop((0,   0,   w,   b))
    bottom_strip = img.crop((0,   h-b, w,   h))
    left_strip   = img.crop((0,   b,   b,   h-b))
    right_strip  = img.crop((w-b, b,   w,   h-b))
    pixels = (list(top_strip.getdata()) + list(bottom_strip.getdata()) +
              list(left_strip.getdata()) + list(right_strip.getdata()))
    if not pixels:
        return False
    white = sum(1 for r, g, bv in pixels if r > white_threshold and g > white_threshold and bv > white_threshold)
    return (white / len(pixels)) >= min_ratio


def crop_jewelry_centered(img: Image.Image, target_fill: float = 0.25) -> Image.Image:
    """
    去背照片智能裁切：偵測珠寶邊界框，置中並填白底，
    使珠寶面積約佔畫布的 target_fill（預設 50%）。
    找不到珠寶時 fallback 到 crop_square。
    """
    gray = img.convert("L")
    mask = gray.point(lambda x: 0 if x >= 235 else 255)
    bbox = mask.getbbox()

    if bbox is None:
        return crop_square(img)

    left, top, right, bottom = bbox
    jw = right - left
    jh = bottom - top

    if jw <= 4 or jh <= 4:
        return crop_square(img)

    # canvas_size 使得 max(jw,jh) / canvas_size = sqrt(target_fill)
    jewelry_max = max(jw, jh)
    canvas_size = int(jewelry_max / (target_fill ** 0.5))

    w, h = img.size
    cx = (left + right) // 2
    cy = (top + bottom) // 2

    half = canvas_size // 2
    x1 = cx - half
    y1 = cy - half
    x2 = x1 + canvas_size
    y2 = y1 + canvas_size

    # 白底畫布，把影像對應區域貼入
    result = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))
    src_x1 = max(0, x1)
    src_y1 = max(0, y1)
    src_x2 = min(w, x2)
    src_y2 = min(h, y2)
    if src_x2 > src_x1 and src_y2 > src_y1:
        region = img.crop((src_x1, src_y1, src_x2, src_y2))
        result.paste(region, (src_x1 - x1, src_y1 - y1))
    return result


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

    # 3. 裁正方形（去背照片智能置中珠寶）
    if is_white_background(img):
        img_square = crop_jewelry_centered(img)
    else:
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
