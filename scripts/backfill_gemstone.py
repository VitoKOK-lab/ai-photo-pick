"""backfill_gemstone.py - 補寫 gemstone / metal_color / setting_amount / craft_complexity 到 SQLite

針對已匯入但這些欄位為 NULL 的照片，重跑 CLIP 分類並更新。
可安全重跑：已有值的照片不會被覆蓋。
"""
import logging
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, FULL_DIR
from scripts.classify import classify_one

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)

FILL_COLS = ["gemstone", "metal_color", "setting_amount", "craft_complexity"]


def main():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    # 找出任一欄位為 NULL 的照片
    where = " OR ".join(f"{c} IS NULL" for c in FILL_COLS)
    rows = conn.execute(
        f"SELECT id, filename FROM photos WHERE {where} ORDER BY id"
    ).fetchall()
    total = len(rows)
    log.info(f"Found {total} photos needing backfill")
    if total == 0:
        conn.close()
        return

    ok = err = skip = 0
    start = time.time()
    for i, row in enumerate(rows, 1):
        full_path = FULL_DIR / row["filename"]
        if not full_path.exists():
            log.warning(f"[{i}/{total}] MISSING file: {row['filename']}")
            skip += 1
            continue
        try:
            cls, _ = classify_one(full_path)
            conn.execute("""
                UPDATE photos SET
                    gemstone          = COALESCE(gemstone,          ?),
                    gemstone_confidence = COALESCE(gemstone_confidence, ?),
                    metal_color       = COALESCE(metal_color,       ?),
                    setting_amount    = COALESCE(setting_amount,    ?),
                    craft_complexity  = COALESCE(craft_complexity,  ?)
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
    log.info(f"\n[DONE] ok={ok} skip={skip} err={err}")


if __name__ == "__main__":
    main()
