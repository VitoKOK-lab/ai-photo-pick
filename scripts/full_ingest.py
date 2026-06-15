"""full_ingest.py - 一鍵完整匯入：處理所有照片 + 補標籤 + 刪空資料夾

使用方式（在 ai-photo-pick 目錄）：
  python3 -m scripts.full_ingest
"""
import logging
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, UNSORTED_DIR, FULL_DIR

VALID_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic")

ts = time.strftime("%Y%m%d_%H%M")
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / f"full_ingest_{ts}.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ── Step 1: 跑 batch_run ───────────────────────────────────
def step1_batch():
    from scripts.ingest import ingest_one

    images = sorted([
        p for p in UNSORTED_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in VALID_EXT
    ])
    total = len(images)
    log.info(f"\n{'='*60}")
    log.info(f"STEP 1: 批次匯入 — 找到 {total} 張照片")
    log.info(f"{'='*60}")
    if total == 0:
        log.info("  沒有新照片，跳過")
        return

    stats = {"ok": 0, "skip_duplicate": 0, "error": 0}
    start = time.time()
    for i, img_path in enumerate(images, 1):
        result = ingest_one(img_path)
        stats[result["status"]] += 1
        elapsed = time.time() - start
        rate = i / elapsed if elapsed > 0 else 0
        eta = (total - i) / rate if rate > 0 else 0

        if result["status"] == "ok":
            cls = result.get("classification", {})
            tag = f"{cls.get('category',{}).get('label','?')}/{cls.get('color',{}).get('label','?')}/{cls.get('gemstone',{}).get('label','?')}"
            try:
                img_path.unlink()
            except Exception as e:
                log.warning(f"  無法刪除來源: {e}")
        elif result["status"] == "skip_duplicate":
            tag = "重複跳過"
        else:
            tag = f"ERROR: {result.get('error','')}"
            log.error(f"  [{i}/{total}] {img_path.name} -> {tag}")

        log.info(f"[{i}/{total}] (ETA {eta:.0f}s) {img_path.name} -> {tag}")

    log.info(f"STEP 1 完成: OK={stats['ok']} 重複={stats['skip_duplicate']} 錯誤={stats['error']}")


# ── Step 2: 刪空資料夾 ────────────────────────────────────
def step2_remove_empty_dirs():
    log.info(f"\n{'='*60}")
    log.info("STEP 2: 刪除空資料夾")
    log.info(f"{'='*60}")
    removed = 0
    # 由深到淺刪（rglob 先跑深層）
    for d in sorted(UNSORTED_DIR.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            try:
                d.rmdir()
                log.info(f"  刪除空資料夾: {d.relative_to(UNSORTED_DIR)}")
                removed += 1
            except Exception as e:
                log.warning(f"  無法刪除 {d}: {e}")
    log.info(f"STEP 2 完成: 刪除 {removed} 個空資料夾")


# ── Step 3: 補標籤 ────────────────────────────────────────
def step3_backfill():
    from scripts.classify import classify_one

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    fill_cols = ["gemstone", "metal_color", "setting_amount", "craft_complexity"]
    where = " OR ".join(f"{c} IS NULL" for c in fill_cols)
    rows = conn.execute(
        f"SELECT id, filename FROM photos WHERE {where} ORDER BY id"
    ).fetchall()
    total = len(rows)

    log.info(f"\n{'='*60}")
    log.info(f"STEP 3: 補標籤 — 找到 {total} 張需要補填")
    log.info(f"{'='*60}")
    if total == 0:
        log.info("  所有照片標籤都完整，跳過")
        conn.close()
        return

    ok = err = skip = 0
    start = time.time()
    for i, row in enumerate(rows, 1):
        full_path = FULL_DIR / row["filename"]
        if not full_path.exists():
            log.warning(f"[{i}/{total}] 找不到檔案: {row['filename']}")
            skip += 1
            continue
        try:
            cls, _ = classify_one(full_path)
            conn.execute("""
                UPDATE photos SET
                    gemstone            = COALESCE(gemstone,            ?),
                    gemstone_confidence = COALESCE(gemstone_confidence, ?),
                    metal_color         = COALESCE(metal_color,         ?),
                    setting_amount      = COALESCE(setting_amount,      ?),
                    craft_complexity    = COALESCE(craft_complexity,     ?)
                WHERE id = ?
            """, (
                cls["gemstone"]["label"],
                cls["gemstone"]["confidence"],
                cls.get("metal_color", {}).get("label"),
                cls.get("setting_amount", {}).get("label"),
                cls.get("craft_complexity", {}).get("label"),
                row["id"],
            ))
            conn.commit()
            ok += 1
            elapsed = time.time() - start
            eta = (total - i) / (i / elapsed) if elapsed > 0 else 0
            log.info(f"[{i}/{total}] (ETA {eta:.0f}s) {row['filename']} -> {cls['gemstone']['label']}")
        except Exception as e:
            log.error(f"[{i}/{total}] ERROR {row['filename']}: {e}")
            err += 1

    conn.close()
    log.info(f"STEP 3 完成: OK={ok} 跳過={skip} 錯誤={err}")


# ── Main ──────────────────────────────────────────────────
if __name__ == "__main__":
    log.info(f"開始完整匯入流程 {ts}")
    step1_batch()
    step2_remove_empty_dirs()
    step3_backfill()
    log.info(f"\n{'='*60}")
    log.info("全部完成！")
    log.info(f"{'='*60}")
