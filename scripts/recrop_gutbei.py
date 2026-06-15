"""recrop_gutbei.py - 重新裁切所有「去背」照片，讓珠寶置中佔畫面 50%

使用方式：
  python3 -m scripts.recrop_gutbei            # 處理所有 photo_type='去背' 的照片
  python3 -m scripts.recrop_gutbei --dry-run  # 只列出會處理的檔案，不實際修改
"""
import logging
import sqlite3
import sys
import time
from pathlib import Path
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    SQLITE_PATH, ORIGINAL_DIR, FULL_DIR, THUMB_DIR, MICRO_DIR,
    FULL_SIZE, THUMB_SIZE, MICRO_SIZE, JPEG_QUALITY
)
from scripts.process_image import crop_jewelry_centered, crop_square, is_white_background

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.StreamHandler()])
log = logging.getLogger(__name__)


def recrop_one(row: dict, dry_run: bool = False) -> str:
    """重新裁切單張照片，回傳 'ok' | 'skip' | 'error'"""
    filename = row["filename"]
    original_filename = row.get("original_filename") or filename

    # 找原始檔（支援 .heic / .jpg / .jpeg / .png / .webp）
    base = Path(filename).stem
    original_path = None
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".heic", ".HEIC", ".JPG", ".PNG"):
        candidate = ORIGINAL_DIR / f"{base}{ext}"
        if candidate.exists():
            original_path = candidate
            break

    if original_path is None:
        log.warning(f"  找不到原始檔: {base}.*")
        return "skip"

    if dry_run:
        log.info(f"  [DRY] {filename} <- {original_path.name}")
        return "ok"

    try:
        img = Image.open(original_path)
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")

        # 智能裁切（已確認是去背，但再做一次 is_white_background 確保安全）
        if is_white_background(img):
            img_square = crop_jewelry_centered(img, target_fill=0.25)
        else:
            img_square = crop_square(img)

        img_full  = img_square.resize(FULL_SIZE,  Image.LANCZOS)
        img_thumb = img_square.resize(THUMB_SIZE, Image.LANCZOS)
        img_micro = img_square.resize(MICRO_SIZE, Image.LANCZOS)

        img_full.save(FULL_DIR  / filename, "JPEG", quality=JPEG_QUALITY)
        img_thumb.save(THUMB_DIR / filename, "JPEG", quality=JPEG_QUALITY)
        img_micro.save(MICRO_DIR / filename, "JPEG", quality=JPEG_QUALITY)
        return "ok"
    except Exception as e:
        log.error(f"  ERROR {filename}: {e}")
        return "error"


def main(dry_run: bool = False):
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, filename, original_filename FROM photos WHERE photo_type = '去背' ORDER BY id"
    ).fetchall()
    conn.close()

    total = len(rows)
    log.info(f"{'='*60}")
    log.info(f"重新裁切去背照片 — 共 {total} 張{'（DRY RUN）' if dry_run else ''}")
    log.info(f"{'='*60}")
    if total == 0:
        log.info("沒有去背照片需要處理")
        return

    stats = {"ok": 0, "skip": 0, "error": 0}
    start = time.time()
    for i, row in enumerate(rows, 1):
        result = recrop_one(dict(row), dry_run=dry_run)
        stats[result] += 1
        if i % 200 == 0 or i == total:
            elapsed = time.time() - start
            eta = (total - i) / (i / elapsed) if elapsed > 0 else 0
            log.info(f"[{i}/{total}] ETA {eta:.0f}s — OK={stats['ok']} 跳過={stats['skip']} 錯誤={stats['error']}")

    elapsed = time.time() - start
    log.info(f"\n完成 {elapsed:.1f}s — OK={stats['ok']} 跳過={stats['skip']} 錯誤={stats['error']}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
