"""clean_orphans.py - 清除 DB 裡找不到圖片檔的孤兒記錄"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, FULL_DIR

conn = sqlite3.connect(SQLITE_PATH)
conn.row_factory = sqlite3.Row

rows = conn.execute("SELECT id, filename FROM photos ORDER BY id").fetchall()
total = len(rows)

missing = [r for r in rows if not (FULL_DIR / r["filename"]).exists()]

print(f"DB 總筆數：{total}")
print(f"找不到圖片：{len(missing)}")

if not missing:
    print("沒有孤兒記錄，不需要清理")
    conn.close()
    sys.exit(0)

print("\n前 5 筆範例：")
for r in missing[:5]:
    print(f"  id={r['id']}  filename={r['filename']!r}")

print(f"\n即將刪除 {len(missing)} 筆孤兒記錄...")
confirm = input("確定刪除？(y/N) ").strip().lower()
if confirm != "y":
    print("取消")
    conn.close()
    sys.exit(0)

ids = [r["id"] for r in missing]
placeholders = ",".join("?" * len(ids))
conn.execute(f"DELETE FROM photos WHERE id IN ({placeholders})", ids)
conn.commit()
conn.close()

print(f"✅ 已刪除 {len(missing)} 筆孤兒記錄")
