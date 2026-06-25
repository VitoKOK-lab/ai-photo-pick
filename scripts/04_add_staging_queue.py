"""04_add_staging_queue.py - 新增 staging_queue 表 + photos 的兩個隱藏欄位"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, STAGING_DIR

STAGING_DIR.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(SQLITE_PATH)
cur = conn.cursor()

# 為 photos 表加入兩個新欄位（已存在則跳過）
for col, dflt in [("added_date", "TEXT"), ("is_custom_order", "INTEGER DEFAULT 0")]:
    try:
        cur.execute(f"ALTER TABLE photos ADD COLUMN {col} {dflt}")
        print(f"✓ photos.{col} 新增完成")
    except sqlite3.OperationalError:
        print(f"  photos.{col} 已存在，跳過")

# 建立 staging_queue 表
cur.execute("""
CREATE TABLE IF NOT EXISTS staging_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL UNIQUE,
    original_filename TEXT NOT NULL,
    filename TEXT,
    full_path TEXT,
    thumb_path TEXT,
    micro_path TEXT,
    file_hash TEXT,
    file_size INTEGER,
    width INTEGER,
    height INTEGER,
    category TEXT, color TEXT, gemstone TEXT,
    stone_shape TEXT, stone_size TEXT, material TEXT,
    metal_color TEXT, style TEXT, setting_amount TEXT,
    craft_complexity TEXT, photo_type TEXT,
    is_custom_order INTEGER DEFAULT 0,
    display_name TEXT,
    embedding_json TEXT,
    staged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
print("✓ staging_queue 表建立完成")

conn.commit()
conn.close()
print("遷移完成。")
