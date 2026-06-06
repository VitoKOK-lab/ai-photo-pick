"""watch_folder.py - 監聽 01_unsorted/，新照片自動處理"""
import sys
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import UNSORTED_DIR
from scripts.ingest import ingest_one

VALID_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic")

class JewelryHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() not in VALID_EXT:
            return

        # 等 1 秒避免檔案還沒寫完
        time.sleep(1)
        if not path.exists():
            return

        print(f"[WATCH] New file: {path.name}")
        result = ingest_one(path)
        if result["status"] == "ok":
            cls = result["classification"]
            print(f"  -> {cls['category']['label']}/{cls['color']['label']}/{cls['gemstone']['label']}")
            try:
                path.unlink()
            except Exception:
                pass
        else:
            print(f"  -> {result['status']}")

def main():
    print(f"[WATCH] Monitoring {UNSORTED_DIR}")
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
