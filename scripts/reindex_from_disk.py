"""reindex_from_disk.py - 從 02_classified 資料夾重新建立 photos 資料表

資料夾結構：02_classified/{品項}/{款式}/{檔名}.jpg
檔名格式：  {品項}_{款式}_{顏色}_{寶石}_{編號}.jpg

執行：python3 scripts/reindex_from_disk.py
"""
import hashlib
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, BASE_DIR

CLASSIFIED_DIR = BASE_DIR / "data" / "02_classified"

conn = sqlite3.connect(SQLITE_PATH)
conn.row_factory = sqlite3.Row

# 清空舊資料（保留表格結構）
conn.execute("DELETE FROM photos")
conn.commit()
print("清空 photos 資料表")

inserted = 0
errors   = 0

# 掃描所有 jpg 檔
for jpg in sorted(CLASSIFIED_DIR.rglob("*.jpg")):
    try:
        parts = jpg.relative_to(CLASSIFIED_DIR).parts
        # parts[0] = 品項, parts[1] = 款式(style), parts[-1] = 檔名
        category = parts[0] if len(parts) >= 2 else None
        style    = parts[1] if len(parts) >= 3 else None
        filename = jpg.stem  # 無副檔名

        # 從檔名解析其他屬性（格式：品項_款式_顏色_寶石_編號）
        seg = filename.split("_")
        color    = seg[2] if len(seg) > 2 else None
        gemstone = seg[3] if len(seg) > 3 else None

        # 清理「未定」→ None（讓篩選更乾淨）
        def clean(v):
            return None if v in (None, "未定", "其他") else v

        file_hash = hashlib.md5(str(jpg).encode()).hexdigest()

        conn.execute(
            """INSERT INTO photos
               (filename, original_filename, original_path, full_path, thumb_path, micro_path,
                file_hash, category, style, color, gemstone, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            (
                filename,
                jpg.name,
                str(jpg),
                str(jpg),
                str(jpg),
                str(jpg),
                file_hash,
                category,
                clean(style),
                clean(color),
                clean(gemstone),
            )
        )
        inserted += 1

        if inserted % 500 == 0:
            conn.commit()
            print(f"  已索引 {inserted} 張...")

    except Exception as e:
        print(f"  錯誤 {jpg}: {e}")
        errors += 1

conn.commit()
conn.close()
print(f"\n✅ 完成！索引 {inserted} 張，錯誤 {errors} 張")
