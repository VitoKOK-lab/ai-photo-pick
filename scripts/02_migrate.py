"""02_migrate.py - 補齊缺少的欄位與資料表（冪等，可重複執行）"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH
from scripts._schema import SCHEMA


def migrate():
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()

    # 1. 補 photos 缺少的欄位
    missing_cols = [
        ("stone_shape",            "TEXT"),
        ("stone_shape_confidence", "REAL"),
        ("stone_size",             "TEXT"),
        ("stone_size_confidence",  "REAL"),
        ("setting_amount",         "TEXT"),
        ("craft_complexity",       "TEXT"),
        ("metal_color",            "TEXT"),
        ("diamond_status",         "TEXT"),
        ("photo_type",             "TEXT"),
    ]
    for col, typ in missing_cols:
        try:
            cur.execute(f"ALTER TABLE photos ADD COLUMN {col} {typ}")
            print(f"  + photos.{col}")
        except Exception:
            pass  # already exists

    # 2. 建立所有缺少的資料表（CREATE TABLE IF NOT EXISTS → 安全）
    conn.executescript(SCHEMA)

    conn.commit()
    conn.close()
    print("[OK] Migration complete")


if __name__ == "__main__":
    migrate()
