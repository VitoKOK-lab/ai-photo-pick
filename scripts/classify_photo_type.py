"""classify_photo_type.py - 白底去背 vs 情境照片 偵測

偵測方式：取縮圖四個角落 30×30 px 的平均亮度，
若 3 個以上角落亮度 > 220 → '去背'，否則 → '情境'

使用方式：
  python3 -m scripts.classify_photo_type          # 全部照片
  python3 -m scripts.classify_photo_type --missing  # 只補 NULL 的
"""
import sqlite3
import sys
import time
import logging
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, THUMB_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.StreamHandler()])
log = logging.getLogger(__name__)

PATCH = 30
THRESHOLD = 220
WHITE_CORNERS_NEEDED = 3


def detect_type(thumb_path: Path) -> str:
    img = Image.open(thumb_path).convert('RGB')
    w, h = img.size
    p = min(PATCH, w // 4, h // 4)
    corners = [
        img.crop((0,   0,   p,   p  )),
        img.crop((w-p, 0,   w,   p  )),
        img.crop((0,   h-p, p,   h  )),
        img.crop((w-p, h-p, w,   h  )),
    ]
    white = 0
    for c in corners:
        pixels = list(c.getdata())
        avg = sum(r + g + b for r, g, b in pixels) / (len(pixels) * 3)
        if avg > THRESHOLD:
            white += 1
    return '去背' if white >= WHITE_CORNERS_NEEDED else '情境'


def main(missing_only: bool = False):
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    if missing_only:
        rows = conn.execute(
            "SELECT id, filename FROM photos WHERE photo_type IS NULL ORDER BY id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, filename FROM photos ORDER BY id"
        ).fetchall()

    total = len(rows)
    log.info(f"共 {total} 張需要分類")
    if total == 0:
        conn.close()
        return

    counts = {'去背': 0, '情境': 0, 'error': 0}
    start = time.time()
    for i, row in enumerate(rows, 1):
        thumb_path = THUMB_DIR / row['filename']
        if not thumb_path.exists():
            counts['error'] += 1
            continue
        try:
            ptype = detect_type(thumb_path)
            conn.execute("UPDATE photos SET photo_type = ? WHERE id = ?", (ptype, row['id']))
            if i % 500 == 0:
                conn.commit()
            counts[ptype] += 1
            if i % 1000 == 0:
                elapsed = time.time() - start
                eta = (total - i) / (i / elapsed) if elapsed > 0 else 0
                log.info(f"[{i}/{total}] ETA {eta:.0f}s 去背={counts['去背']} 情境={counts['情境']}")
        except Exception as e:
            counts['error'] += 1
            if i % 1000 == 0:
                log.error(f"  [{i}] ERROR {row['filename']}: {e}")

    conn.commit()
    conn.close()
    elapsed = time.time() - start
    log.info(f"\n完成 {elapsed:.1f}s — 去背:{counts['去背']} 情境:{counts['情境']} 錯誤:{counts['error']}")


if __name__ == '__main__':
    main(missing_only='--missing' in sys.argv)
