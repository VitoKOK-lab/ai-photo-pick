"""reclassify_all.py - 用新的 categories.json 重新分類所有照片

執行：python3 scripts/reclassify_all.py
可安全重跑，會直接 UPDATE 既有記錄。
"""
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH
from scripts.classify import classify_one

# ─── 先確保新欄位存在 ─────────────────────────────────────────────────────────
def migrate(conn):
    new_cols = [
        ("stone_shape",            "TEXT"),
        ("stone_shape_confidence", "REAL"),
        ("stone_size",             "TEXT"),
        ("stone_size_confidence",  "REAL"),
    ]
    existing = {row[1] for row in conn.execute("PRAGMA table_info(photos)")}
    for col, typ in new_cols:
        if col not in existing:
            conn.execute(f"ALTER TABLE photos ADD COLUMN {col} {typ}")
            print(f"  + 新增欄位：{col}")
    conn.commit()

# ─── 主程式 ───────────────────────────────────────────────────────────────────
conn = sqlite3.connect(SQLITE_PATH)
conn.row_factory = sqlite3.Row

migrate(conn)

rows = conn.execute("SELECT id, full_path FROM photos ORDER BY id").fetchall()
total = len(rows)
print(f"\n共 {total} 張照片，開始重新分類...\n")

stats = {"ok": 0, "error": 0}
start = time.time()

for i, row in enumerate(rows, 1):
    photo_id = row["id"]
    full_path = Path(row["full_path"])

    if not full_path.exists():
        print(f"  [{i}/{total}] 找不到檔案：{full_path.name}")
        stats["error"] += 1
        continue

    try:
        cls, _ = classify_one(full_path)

        conn.execute("""
            UPDATE photos SET
                color             = ?, color_confidence      = ?,
                category          = ?, category_confidence   = ?,
                material          = ?, material_confidence   = ?,
                stone_shape       = ?, stone_shape_confidence = ?,
                stone_size        = ?, stone_size_confidence  = ?,
                style             = ?, style_confidence       = ?,
                price_band        = ?,
                updated_at        = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            cls["color"]["label"],       cls["color"]["confidence"],
            cls["category"]["label"],    cls["category"]["confidence"],
            cls["material"]["label"],    cls["material"]["confidence"],
            cls["stone_shape"]["label"], cls["stone_shape"]["confidence"],
            cls["stone_size"]["label"],  cls["stone_size"]["confidence"],
            cls["style"]["label"],       cls["style"]["confidence"],
            cls.get("price_band", {}).get("label"),
            photo_id,
        ))

        elapsed = time.time() - start
        rate = i / elapsed if elapsed > 0 else 0
        eta = (total - i) / rate if rate > 0 else 0

        tag = (
            f"{cls['category']['label']}/"
            f"{cls['color']['label']}/"
            f"{cls['stone_shape']['label']}/"
            f"{cls['style']['label']}"
        )
        print(f"  [{i}/{total}] (ETA {eta:.0f}s) {full_path.name} -> {tag}")
        stats["ok"] += 1

        if i % 100 == 0:
            conn.commit()

    except Exception as e:
        print(f"  [{i}/{total}] 錯誤：{full_path.name} — {e}")
        stats["error"] += 1

conn.commit()
conn.close()

elapsed = time.time() - start
print(f"\n✅ 完成！{total} 張 in {elapsed:.1f}s")
print(f"   成功：{stats['ok']}  錯誤：{stats['error']}")
