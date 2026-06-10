"""check_others.py - 查看被分類為「其他」的照片有哪些"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

conn = sqlite3.connect(SQLITE_PATH)
conn.row_factory = sqlite3.Row

print("=" * 60)
print("各欄位「其他」統計")
print("=" * 60)

for col in ["category", "stone_shape", "style", "color", "material"]:
    try:
        row = conn.execute(f"SELECT COUNT(*) as n FROM photos WHERE {col} LIKE '%其他%'").fetchone()
        total = conn.execute("SELECT COUNT(*) as n FROM photos").fetchone()["n"]
        print(f"  {col:20s} 其他：{row['n']:4d} / {total} 張 ({row['n']/total*100:.1f}%)")
    except:
        pass

print()
print("=" * 60)
print("stone_shape 分布")
print("=" * 60)
for row in conn.execute("SELECT stone_shape, COUNT(*) as n FROM photos GROUP BY stone_shape ORDER BY n DESC").fetchall():
    print(f"  {str(row['stone_shape']):20s}  {row['n']:4d} 張")

print()
print("=" * 60)
print("style 分布")
print("=" * 60)
for row in conn.execute("SELECT style, COUNT(*) as n FROM photos GROUP BY style ORDER BY n DESC").fetchall():
    print(f"  {str(row['style']):30s}  {row['n']:4d} 張")

print()
print("=" * 60)
print("stone_shape=其他 的前 20 張原始檔名")
print("=" * 60)
rows = conn.execute(
    "SELECT original_filename, stone_shape_confidence FROM photos WHERE stone_shape LIKE '%其他%' ORDER BY stone_shape_confidence ASC LIMIT 20"
).fetchall()
for r in rows:
    print(f"  {r['stone_shape_confidence']:.2f}  {r['original_filename']}")

print()
print("=" * 60)
print("style=其他 的前 20 張原始檔名")
print("=" * 60)
rows = conn.execute(
    "SELECT original_filename, style_confidence FROM photos WHERE style LIKE '%其他%' ORDER BY style_confidence ASC LIMIT 20"
).fetchall()
for r in rows:
    print(f"  {r['style_confidence']:.2f}  {r['original_filename']}")

conn.close()
