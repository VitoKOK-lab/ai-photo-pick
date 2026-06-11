"""reclassify_others.py - 只重新分類「其他」和「未定」的照片

執行：python3 scripts/reclassify_others.py
"""
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH
from scripts.classify import classify_one

conn = sqlite3.connect(SQLITE_PATH)
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT id, full_path, category FROM photos WHERE category IN ('其他', '未定') ORDER BY id"
).fetchall()
total = len(rows)
print(f"\n共 {total} 張「其他/未定」照片，開始重新分類...\n")

stats = {"ok": 0, "skip": 0, "error": 0}
changed = {}
start = time.time()

for i, row in enumerate(rows, 1):
    photo_id   = row["id"]
    old_cat    = row["category"]
    full_path  = Path(row["full_path"])

    if not full_path.exists():
        print(f"  [{i}/{total}] 找不到檔案：{full_path.name}")
        stats["skip"] += 1
        continue

    try:
        cls, _ = classify_one(full_path)
        new_cat = cls["category"]["label"]
        conf    = cls["category"]["confidence"]

        conn.execute(
            """UPDATE photos SET
                category            = ?, category_confidence = ?,
                color               = ?, color_confidence    = ?,
                style               = ?, style_confidence    = ?,
                updated_at          = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (
                new_cat, conf,
                cls["color"]["label"],    cls["color"]["confidence"],
                cls["style"]["label"],    cls["style"]["confidence"],
                photo_id,
            ),
        )

        elapsed = time.time() - start
        rate    = i / elapsed if elapsed > 0 else 0
        eta     = (total - i) / rate if rate > 0 else 0

        marker = " ★" if new_cat != old_cat else ""
        print(f"  [{i}/{total}] ETA {eta:.0f}s  {full_path.name[:40]:40s}  {old_cat} → {new_cat} ({conf:.2f}){marker}")

        if new_cat != old_cat:
            changed[new_cat] = changed.get(new_cat, 0) + 1

        stats["ok"] += 1

        if i % 50 == 0:
            conn.commit()
            print(f"\n  >>> 已存檔，目前變更：{dict(changed)}\n")

    except Exception as e:
        print(f"  [{i}/{total}] 錯誤：{full_path.name} — {e}")
        stats["error"] += 1

conn.commit()
conn.close()

elapsed = time.time() - start
print(f"\n{'='*60}")
print(f"✅ 完成！{total} 張 in {elapsed:.1f}s")
print(f"   成功：{stats['ok']}  略過：{stats['skip']}  錯誤：{stats['error']}")
print(f"\n分類變更統計（原本是「其他/未定」，現在變成）：")
for cat, n in sorted(changed.items(), key=lambda x: -x[1]):
    print(f"   {cat}：{n} 張")
