"""watch_folder.py - 監聽 01_unsorted/，新照片自動處理"""
import logging
import sys
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import UNSORTED_DIR, LOG_DIR

VALID_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WATCH] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "watcher.log", encoding="utf-8"),
    ]
)
log = logging.getLogger(__name__)


def wait_for_stable(path: Path, timeout: int = 30) -> bool:
    """
    等待檔案大小穩定（寫入完成）
    每 0.5 秒檢查一次，最多等 timeout 秒
    """
    prev_size = -1
    deadline  = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.5)
        if not path.exists():
            return False
        cur_size = path.stat().st_size
        if cur_size == prev_size and cur_size > 0:
            return True
        prev_size = cur_size
    log.warning(f"Timeout waiting for {path.name} to stabilize")
    return False


class JewelryHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() not in VALID_EXT:
            return

        log.info(f"New file detected: {path.name}")

        if not wait_for_stable(path):
            log.error(f"File not stable or disappeared: {path.name}")
            return

        from scripts.ingest import ingest_one
        result = ingest_one(path)

        if result["status"] == "ok":
            cls = result["classification"]
            log.info(
                f"OK -> {cls['category']['label']}/"
                f"{cls['color']['label']}/"
                f"{cls['gemstone']['label']} "
                f"[id={result['photo_id']}]"
            )
            try:
                path.unlink()
            except Exception as e:
                log.warning(f"Cannot delete source: {e}")

        elif result["status"] == "skip_duplicate":
            log.info(f"Skipped (duplicate): {path.name}")

        else:
            log.error(f"Error processing {path.name}: {result.get('error')}")


def main():
    UNSORTED_DIR.mkdir(parents=True, exist_ok=True)
    log.info(f"Monitoring {UNSORTED_DIR}")
    observer = Observer()
    observer.schedule(JewelryHandler(), str(UNSORTED_DIR), recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
