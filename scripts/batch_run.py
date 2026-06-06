"""batch_run.py - 批次處理 01_unsorted/ 裡所有照片"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import UNSORTED_DIR
from scripts.ingest import ingest_one

VALID_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic")

def main(source_dir: Path = UNSORTED_DIR):
    images = sorted([
        p for p in source_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in VALID_EXT
    ])
    total = len(images)
    print(f"Found {total} images in {source_dir}")
    if total == 0:
        return

    stats = {"ok": 0, "skip_duplicate": 0, "error": 0}
    start = time.time()

    for i, img_path in enumerate(images, 1):
        result = ingest_one(img_path)
        stats[result["status"]] += 1

        elapsed = time.time() - start
        rate = i / elapsed if elapsed > 0 else 0
        eta = (total - i) / rate if rate > 0 else 0

        status = result["status"]
        if status == "ok":
            cls = result["classification"]
            tag = f"{cls['category']['label']}/{cls['color']['label']}/{cls['gemstone']['label']}"
        elif status == "skip_duplicate":
            tag = "DUPLICATE"
        else:
            tag = f"ERROR: {result.get('error', '')}"

        print(f"[{i}/{total}] ({elapsed:.0f}s, ETA {eta:.0f}s) {img_path.name} -> {tag}")

        # 處理完從 01_unsorted/ 刪除（已備份到 02_original/）
        if status == "ok":
            try:
                img_path.unlink()
            except Exception as e:
                print(f"  [WARN] Cannot delete source: {e}")

    elapsed = time.time() - start
    print(f"\n[DONE] {total} processed in {elapsed:.1f}s")
    print(f"  OK: {stats['ok']}, Skipped (duplicate): {stats['skip_duplicate']}, Errors: {stats['error']}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(Path(sys.argv[1]))
    else:
        main()
