"""classify_photo_type.py - 白底去背 vs 情境照片 偵測

方法：採樣縮圖四邊整圈像素，若 65%+ 像素的三個 channel 都 > 235 → 去背。
這比只看角落更可靠，不受珠寶佔角落影響。

使用方式：
  python3 -m scripts.classify_photo_type          # 全部重新分類
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

WHITE_THRESHOLD = 235   # 每個 channel 都要大於這個值才算白
BORDER_WIDTH    = 8     # 採樣邊緣幾個 pixel 厚
WHITE_RATIO_MIN = 0.60  # 邊緣像素 60%+ 是白 → 去背


def detect_type(thumb_path: Path) -> str:
    img = Image.open(thumb_path).convert('RGB')
    w, h = img.size
    b = min(BORDER_WIDTH, w // 6, h // 6)

    # 取四條邊框（上、下、左、右），合成一個像素陣列
    top    = img.crop((0,   0,   w,   b  ))
    bottom = img.crop((0,   h-b, w,   h  ))
    left   = img.crop((0,   b,   b,   h-b))
    right  = img.crop((w-b, b,   w,   h-b))

    all_pixels = (
        list(top.getdata()) +
        list(bottom.getdata()) +
        list(left.getdata()) +
        list(right.getdata())
    )

    if not all_pixels:
        return '情境'

    white_count = sum(
        1 for r, g, b_ch in all_pixels
        if r > WHITE_THRESHOLD and g > WHITE_THRESHOLD and b_ch > WHITE_THRESHOLD
    )
    ratio = white_count / len(all_pixels)
    return '去背' if ratio >= WHITE_RATIO_MIN else '情境'


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
    log.info(f"共 {total} 張，用邊緣亮度偵測去背/情境")
    if total == 0:
        conn.close()
        return

    counts = {'去背': 0, '情境': 0, 'miss': 0}
    start = time.time()
    for i, row in enumerate(rows, 1):
        thumb_path = THUMB_DIR / row['filename']
        if not thumb_path.exists():
            counts['miss'] += 1
            continue
        try:
            ptype = detect_type(thumb_path)
            conn.execute("UPDATE photos SET photo_type = ? WHERE id = ?", (ptype, row['id']))
            if i % 500 == 0:
                conn.commit()
            counts[ptype] += 1
            if i % 2000 == 0:
                elapsed = time.time() - start
                eta = (total - i) / (i / elapsed) if elapsed > 0 else 0
                log.info(f"[{i}/{total}] ETA {eta:.0f}s 去背={counts['去背']} 情境={counts['情境']}")
        except Exception as e:
            counts['miss'] += 1
            log.error(f"  [{i}] {row['filename']}: {e}")

    conn.commit()
    conn.close()
    log.info(f"\n完成 {time.time()-start:.1f}s — 去背:{counts['去背']} 情境:{counts['情境']} 跳過:{counts['miss']}")


if __name__ == '__main__':
    main(missing_only='--missing' in sys.argv)
