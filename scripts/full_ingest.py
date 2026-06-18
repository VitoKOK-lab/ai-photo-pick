"""full_ingest.py - 一鍵完整匯入

流程：
  Step 0 — 去重複（file hash，跳過已存在的照片）
  Step 1 — 批次匯入：裁切 + 完整 CLIP 分類（11個維度全部寫入）+ 刪來源
  Step 2 — 刪空資料夾
  Step 3 — 重做所有標籤（覆蓋，不是只補空格）
  Step 4 — 重做 photo_type（PIL+CLIP 雙重偵測，只跑尚未分類的）

使用方式（在 ai-photo-pick 目錄）：
  python3 -m scripts.full_ingest
"""
import hashlib
import logging
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, UNSORTED_DIR, FULL_DIR, THUMB_DIR

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


def _file_hash(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Step 0: 去重複 ────────────────────────────────────────
def step0_dedup():
    """對 01_unsorted/ 的每張照片算 hash，已存在就刪來源，跳過匯入"""
    images = sorted([
        p for p in UNSORTED_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in VALID_EXT
    ])
    total = len(images)
    log.info(f"\n{'='*60}")
    log.info(f"STEP 0: 去重複檢查 — 找到 {total} 張照片")
    log.info(f"{'='*60}")
    if total == 0:
        return

    conn = sqlite3.connect(SQLITE_PATH)
    removed = 0
    for img_path in images:
        try:
            h = _file_hash(img_path)
            exists = conn.execute(
                "SELECT id, filename FROM photos WHERE file_hash = ?", (h,)
            ).fetchone()
            if exists:
                log.info(f"  重複 → 刪除: {img_path.name}  (已有 {exists[1]})")
                img_path.unlink()
                removed += 1
        except Exception as e:
            log.warning(f"  hash 檢查失敗 {img_path.name}: {e}")
    conn.close()
    log.info(f"STEP 0 完成: 刪除重複 {removed} 張，剩餘 {total - removed} 張待匯入")


# ── Step 1: 批次匯入 ──────────────────────────────────────
def step1_batch():
    """每張照片完整跑：裁切 → CLIP 分析（11維度）→ 寫DB → 刪來源"""
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
            tag = (f"{cls.get('category',{}).get('label','?')}/"
                   f"{cls.get('gemstone',{}).get('label','?')}/"
                   f"{cls.get('style',{}).get('label','?')}")
            try:
                img_path.unlink()
            except Exception as e:
                log.warning(f"  無法刪除來源: {e}")
        elif result["status"] == "skip_duplicate":
            tag = "重複跳過"
            try:
                img_path.unlink()
            except Exception:
                pass
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
    for d in sorted(UNSORTED_DIR.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            try:
                d.rmdir()
                log.info(f"  刪除: {d.relative_to(UNSORTED_DIR)}")
                removed += 1
            except Exception as e:
                log.warning(f"  無法刪除 {d}: {e}")
    log.info(f"STEP 2 完成: 刪除 {removed} 個空資料夾")


# ── Step 3: 重做所有標籤（覆蓋，不是只補空格）────────────
def step3_reclassify():
    """找出任何標籤欄位為 NULL 的照片，重跑 CLIP，直接覆蓋所有欄位"""
    from scripts.classify import classify_one

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    # 找出有任何一個欄位是 NULL 的照片
    check_cols = [
        "category", "color", "gemstone", "stone_shape", "stone_size",
        "material", "metal_color", "style", "setting_amount",
        "craft_complexity", "price_band"
    ]
    where = " OR ".join(f"{c} IS NULL" for c in check_cols)
    rows = conn.execute(
        f"SELECT id, filename FROM photos WHERE {where} ORDER BY id"
    ).fetchall()
    total = len(rows)

    log.info(f"\n{'='*60}")
    log.info(f"STEP 3: 重做標籤 — 找到 {total} 張有欄位缺漏")
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

            # 直接覆蓋所有欄位，不用 COALESCE
            conn.execute("""
                UPDATE photos SET
                    category               = ?,
                    category_confidence    = ?,
                    color                  = ?,
                    color_confidence       = ?,
                    gemstone               = ?,
                    gemstone_confidence    = ?,
                    stone_shape            = ?,
                    stone_shape_confidence = ?,
                    stone_size             = ?,
                    stone_size_confidence  = ?,
                    material               = ?,
                    material_confidence    = ?,
                    metal_color            = ?,
                    style                  = ?,
                    style_confidence       = ?,
                    setting_amount         = ?,
                    craft_complexity       = ?,
                    price_band             = ?,
                    updated_at             = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                cls.get("category",        {}).get("label"),
                cls.get("category",        {}).get("confidence"),
                cls.get("color",           {}).get("label"),
                cls.get("color",           {}).get("confidence"),
                cls.get("gemstone",        {}).get("label"),
                cls.get("gemstone",        {}).get("confidence"),
                cls.get("stone_shape",     {}).get("label"),
                cls.get("stone_shape",     {}).get("confidence"),
                cls.get("stone_size",      {}).get("label"),
                cls.get("stone_size",      {}).get("confidence"),
                cls.get("material",        {}).get("label"),
                cls.get("material",        {}).get("confidence"),
                cls.get("metal_color",     {}).get("label"),
                cls.get("style",           {}).get("label"),
                cls.get("style",           {}).get("confidence"),
                cls.get("setting_amount",  {}).get("label"),
                cls.get("craft_complexity",{}).get("label"),
                cls.get("price_band",      {}).get("label"),
                row["id"],
            ))
            conn.commit()
            ok += 1
            elapsed = time.time() - start
            eta = (total - i) / (i / elapsed) if elapsed > 0 else 0
            summary = (f"{cls.get('category',{}).get('label','?')}/"
                       f"{cls.get('gemstone',{}).get('label','?')}/"
                       f"{cls.get('style',{}).get('label','?')}")
            log.info(f"[{i}/{total}] (ETA {eta:.0f}s) {row['filename']} -> {summary}")
        except Exception as e:
            log.error(f"[{i}/{total}] ERROR {row['filename']}: {e}")
            err += 1

    conn.close()
    log.info(f"STEP 3 完成: OK={ok} 跳過={skip} 錯誤={err}")


# ── Step 4: 補 photo_type (PIL+CLIP 雙重偵測) ─────────────
def step4_photo_type():
    from scripts.classify_photo_type import detect_type

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, filename FROM photos WHERE photo_type IS NULL ORDER BY id"
    ).fetchall()
    total = len(rows)

    log.info(f"\n{'='*60}")
    log.info(f"STEP 4: 重做 photo_type — 找到 {total} 張需要分類")
    log.info(f"{'='*60}")
    if total == 0:
        log.info("  所有照片 photo_type 都完整，跳過")
        conn.close()
        return

    ok = err = skip = 0
    start = time.time()
    for i, row in enumerate(rows, 1):
        thumb_path = THUMB_DIR / row["filename"]
        full_path  = FULL_DIR  / row["filename"]
        if not thumb_path.exists() or not full_path.exists():
            skip += 1
            continue
        try:
            ptype = detect_type(thumb_path, full_path)
            conn.execute("UPDATE photos SET photo_type = ? WHERE id = ?", (ptype, row["id"]))
            if i % 200 == 0:
                conn.commit()
            ok += 1
            if i % 500 == 0:
                elapsed = time.time() - start
                eta = (total - i) / (i / elapsed) if elapsed > 0 else 0
                log.info(f"[{i}/{total}] ETA {eta:.0f}s -> {ptype}")
        except Exception as e:
            log.error(f"[{i}/{total}] ERROR {row['filename']}: {e}")
            err += 1

    conn.commit()
    conn.close()
    log.info(f"STEP 4 完成: OK={ok} 跳過={skip} 錯誤={err}")


# ── Main ──────────────────────────────────────────────────
if __name__ == "__main__":
    log.info(f"開始完整匯入流程 {ts}")
    step0_dedup()
    step1_batch()
    step2_remove_empty_dirs()
    step3_reclassify()
    step4_photo_type()
    log.info(f"\n{'='*60}")
    log.info("全部完成！")
    log.info(f"{'='*60}")
