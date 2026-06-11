"""rename_others.py - 把檔名開頭的「其他_」移除，並更新資料庫

執行：python3 scripts/rename_others.py
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

conn = sqlite3.connect(SQLITE_PATH)
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT id, filename, full_path, thumb_path, micro_path FROM photos WHERE filename LIKE '其他_%' OR full_path LIKE '%/其他_%'"
).fetchall()

print(f"找到 {len(rows)} 筆需要更名的記錄\n")

renamed = 0
errors  = 0

for row in rows:
    old_full = Path(row["full_path"])
    if not old_full.exists():
        print(f"  找不到: {old_full}")
        errors += 1
        continue

    # 新檔名：去掉開頭的「其他_」
    old_name = old_full.name
    new_name = old_name
    while new_name.startswith("其他_"):
        new_name = new_name[3:]
    if not new_name or new_name == old_name:
        continue

    new_full = old_full.parent / new_name

    # 若新路徑已存在就加數字避免衝突
    if new_full.exists():
        stem = new_full.stem
        suffix = new_full.suffix
        n = 1
        while new_full.exists():
            new_full = old_full.parent / f"{stem}_{n}{suffix}"
            n += 1

    try:
        old_full.rename(new_full)
        new_filename = row["filename"]
        while new_filename.startswith("其他_"):
            new_filename = new_filename[3:]

        conn.execute(
            "UPDATE photos SET filename=?, full_path=?, thumb_path=?, micro_path=? WHERE id=?",
            (new_filename, str(new_full), str(new_full), str(new_full), row["id"])
        )
        renamed += 1
        if renamed % 100 == 0:
            conn.commit()
            print(f"  已處理 {renamed} 張...")
    except Exception as e:
        print(f"  錯誤 {old_full.name}: {e}")
        errors += 1

conn.commit()
conn.close()
print(f"\n✅ 完成！更名 {renamed} 張，錯誤 {errors} 張")
