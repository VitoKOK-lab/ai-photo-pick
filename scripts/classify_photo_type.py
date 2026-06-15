"""classify_photo_type.py - 用 CLIP 分類去背（白底）vs 情境照片

原理與 classify.py 相同：CLIP 比對圖片和文字描述的語意相似度。
photo_type 維度已加入 config/prompts.json。

使用方式：
  python3 -m scripts.classify_photo_type          # 全部重新分類
  python3 -m scripts.classify_photo_type --missing  # 只補 NULL 的
"""
import sqlite3
import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, FULL_DIR
from scripts.classify import classify_one

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.StreamHandler()])
log = logging.getLogger(__name__)


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
    log.info(f"共 {total} 張需要分類（CLIP 語意判斷）")
    if total == 0:
        conn.close()
        return

    counts = {'去背': 0, '情境': 0, 'error': 0}
    start = time.time()
    for i, row in enumerate(rows, 1):
        full_path = FULL_DIR / row['filename']
        if not full_path.exists():
            counts['error'] += 1
            continue
        try:
            cls, _ = classify_one(full_path)
            ptype = cls.get('photo_type', {}).get('label', '情境')
            conn.execute("UPDATE photos SET photo_type = ? WHERE id = ?", (ptype, row['id']))
            if i % 200 == 0:
                conn.commit()
            counts[ptype] = counts.get(ptype, 0) + 1
            if i % 500 == 0:
                elapsed = time.time() - start
                eta = (total - i) / (i / elapsed) if elapsed > 0 else 0
                log.info(f"[{i}/{total}] ETA {eta:.0f}s 去背={counts.get('去背',0)} 情境={counts.get('情境',0)}")
        except Exception as e:
            counts['error'] += 1
            log.error(f"  [{i}] ERROR {row['filename']}: {e}")

    conn.commit()
    conn.close()
    elapsed = time.time() - start
    log.info(f"\n完成 {elapsed:.1f}s — 去背:{counts.get('去背',0)} 情境:{counts.get('情境',0)} 錯誤:{counts['error']}")


if __name__ == '__main__':
    main(missing_only='--missing' in sys.argv)
