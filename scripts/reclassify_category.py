"""reclassify_category.py - 只重跑 category 欄位（品項分類）

用於 prompt 改版後，強制重新分類所有照片的品項。
其他欄位不動。

使用方式：
  cd /Users/vitomini/ai-photo-pick
  python3 -m scripts.reclassify_category
"""
import sqlite3
import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, FULL_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.StreamHandler()])
log = logging.getLogger(__name__)


def main():
    from scripts.classify import classify_one

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, filename, category FROM photos ORDER BY id"
    ).fetchall()
    total = len(rows)
    log.info(f"共 {total} 張照片，重新分類 category…")

    stats = {"ok": 0, "skip": 0, "err": 0}
    start = time.time()
    changed = 0

    for i, row in enumerate(rows, 1):
        full_path = FULL_DIR / row["filename"]
        if not full_path.exists():
            stats["skip"] += 1
            continue
        try:
            cls, _ = classify_one(full_path)
            new_cat = cls.get("category", {}).get("label")
            new_conf = cls.get("category", {}).get("confidence")

            conn.execute(
                "UPDATE photos SET category=?, category_confidence=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (new_cat, new_conf, row["id"])
            )
            if new_cat != row["category"]:
                changed += 1
                log.info(f"[{i}/{total}] {row['filename']}: {row['category']} → {new_cat} ({new_conf:.2f})")

            if i % 500 == 0:
                conn.commit()
                elapsed = time.time() - start
                eta = (total - i) / (i / elapsed)
                log.info(f"[{i}/{total}] ETA {eta:.0f}s — 已變更 {changed} 筆")

            stats["ok"] += 1
        except Exception as e:
            log.error(f"[{i}/{total}] ERROR {row['filename']}: {e}")
            stats["err"] += 1

    conn.commit()
    conn.close()

    elapsed = time.time() - start
    log.info(f"\n完成 {elapsed:.1f}s")
    log.info(f"OK={stats['ok']} 跳過={stats['skip']} 錯誤={stats['err']}")
    log.info(f"共變更 {changed} 筆品項標籤")


if __name__ == "__main__":
    main()
