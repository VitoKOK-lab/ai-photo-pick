"""dedup.py - 找出並刪除重複照片（依 file_hash）

保留最早匯入的那一張（最小 id），刪除其餘重複的圖檔與 DB 紀錄。

使用方式：
  python3 -m scripts.dedup            # 列出重複並刪除
  python3 -m scripts.dedup --dry-run  # 只列出，不實際刪除
"""
import sqlite3
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, FULL_DIR, THUMB_DIR, MICRO_DIR, ORIGINAL_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.StreamHandler()])
log = logging.getLogger(__name__)


def main(dry_run: bool = False):
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    # 找出有重複 hash 的組
    dupes = conn.execute("""
        SELECT file_hash, COUNT(*) as cnt
        FROM photos
        WHERE file_hash IS NOT NULL
        GROUP BY file_hash
        HAVING cnt > 1
        ORDER BY cnt DESC
    """).fetchall()

    if not dupes:
        log.info("沒有重複照片，資料庫乾淨")
        conn.close()
        return

    total_groups = len(dupes)
    total_delete = sum(d["cnt"] - 1 for d in dupes)
    log.info(f"找到 {total_groups} 組重複，共 {total_delete} 張要刪除{'（DRY RUN）' if dry_run else ''}")

    deleted = 0
    for d in dupes:
        rows = conn.execute(
            "SELECT id, filename, full_path, thumb_path, micro_path, original_path "
            "FROM photos WHERE file_hash = ? ORDER BY id ASC",
            (d["file_hash"],)
        ).fetchall()

        keep = rows[0]
        remove = rows[1:]
        log.info(f"  保留 id={keep['id']} {keep['filename']}，刪除 {len(remove)} 張重複")

        for row in remove:
            if not dry_run:
                for path_col in ("full_path", "thumb_path", "micro_path", "original_path"):
                    p = row[path_col]
                    if p:
                        try:
                            Path(p).unlink(missing_ok=True)
                        except Exception as e:
                            log.warning(f"    無法刪除檔案 {p}: {e}")
                conn.execute("DELETE FROM photos WHERE id = ?", (row["id"],))
            deleted += 1

    if not dry_run:
        conn.commit()
        log.info(f"完成：刪除 {deleted} 張重複照片")
    else:
        log.info(f"DRY RUN 完成：共 {deleted} 張會被刪除")

    conn.close()


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
