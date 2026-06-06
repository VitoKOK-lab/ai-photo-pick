"""batch_run.py - 批次處理 01_unsorted/ 裡所有照片

使用方式：
  python -m scripts.batch_run              # 跑 data/01_unsorted/
  python -m scripts.batch_run /path/to/dir # 指定目錄

可以安全重跑：已處理的照片會因 hash 重複而自動跳過
"""
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import UNSORTED_DIR, LOG_DIR

VALID_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic")

# ─── logging 同時輸出 stdout + log 檔 ──────────────────────
ts = time.strftime("%Y%m%d_%H%M")
log_file = LOG_DIR / f"batch_{ts}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
)
log = logging.getLogger(__name__)


def main(source_dir: Path = UNSORTED_DIR):
    from scripts.ingest import ingest_one

    images = sorted([
        p for p in source_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in VALID_EXT
    ])
    total = len(images)
    log.info(f"Found {total} images in {source_dir}")
    log.info(f"Log: {log_file}")
    if total == 0:
        return

    stats = {"ok": 0, "skip_duplicate": 0, "error": 0}
    start = time.time()

    for i, img_path in enumerate(images, 1):
        result = ingest_one(img_path)
        stats[result["status"]] += 1

        elapsed = time.time() - start
        rate    = i / elapsed if elapsed > 0 else 0
        eta     = (total - i) / rate if rate > 0 else 0

        if result["status"] == "ok":
            try:
                cls = result["classification"]
                tag = (
                    f"{cls['category']['label']}/"
                    f"{cls['color']['label']}/"
                    f"{cls['gemstone']['label']}"
                )
            except (KeyError, TypeError) as e:
                tag = f"ok (tag error: {e})"
            # 刪除來源（已備份到 02_original/）
            try:
                img_path.unlink()
            except Exception as e:
                log.warning(f"  Cannot delete source: {e}")

        elif result["status"] == "skip_duplicate":
            tag = "DUPLICATE"

        else:
            tag = f"ERROR: {result.get('error', '')}"
            log.error(f"  [{i}/{total}] {img_path.name} -> {tag}")

        log.info(
            f"[{i}/{total}] "
            f"({elapsed:.0f}s, ETA {eta:.0f}s) "
            f"{img_path.name} -> {tag}"
        )

    elapsed = time.time() - start
    log.info(f"\n[DONE] {total} processed in {elapsed:.1f}s")
    log.info(
        f"  OK: {stats['ok']}, "
        f"Skipped (duplicate): {stats['skip_duplicate']}, "
        f"Errors: {stats['error']}"
    )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(Path(sys.argv[1]))
    else:
        main()
