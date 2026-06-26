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
        ("stone_shape",                  "TEXT"),
        ("stone_shape_confidence",       "REAL"),
        ("stone_size",                   "TEXT"),
        ("stone_size_confidence",        "REAL"),
        ("setting_amount",               "TEXT"),
        ("setting_amount_confidence",    "REAL"),
        ("craft_complexity",             "TEXT"),
        ("craft_complexity_confidence",  "REAL"),
        ("metal_color",                  "TEXT"),
        ("metal_color_confidence",       "REAL"),
        ("metal_weight",                 "TEXT"),
        ("metal_weight_confidence",      "REAL"),
        ("style_confidence",             "REAL"),
        ("color_confidence",             "REAL"),
        ("gemstone_confidence",          "REAL"),
        ("category_confidence",          "REAL"),
        ("material_confidence",          "REAL"),
        ("photo_type_confidence",        "REAL"),
        ("stone_size_confidence",        "REAL"),
        ("price_band",                   "TEXT"),
        ("price_band_confidence",        "REAL"),
        ("diamond_status",               "TEXT"),
        ("photo_type",                   "TEXT"),
        ("updated_at",                   "TIMESTAMP"),
    ]
    for col, typ in missing_cols:
        try:
            cur.execute(f"ALTER TABLE photos ADD COLUMN {col} {typ}")
            print(f"  + photos.{col}")
        except Exception:
            pass  # already exists

    # 2. 建立所有缺少的資料表（CREATE TABLE IF NOT EXISTS → 安全）
    conn.executescript(SCHEMA)

    # 3. quotes 表新增欄位
    for col, typ in [("locked_at", "TEXT"), ("updated_at", "TIMESTAMP")]:
        try:
            cur.execute(f"ALTER TABLE quotes ADD COLUMN {col} {typ}")
            print(f"  + quotes.{col}")
        except Exception:
            pass  # already exists

    # 4. staging_queue 表新增欄位
    sq_cols = [
        ("folder_name",              "TEXT"),
        ("is_custom_order",          "INTEGER DEFAULT 0"),
        ("category_confidence",      "REAL"),
        ("color_confidence",         "REAL"),
        ("gemstone_confidence",      "REAL"),
        ("stone_shape_confidence",   "REAL"),
        ("stone_size_confidence",    "REAL"),
        ("material_confidence",      "REAL"),
        ("metal_color_confidence",   "REAL"),
        ("style_confidence",         "REAL"),
        ("setting_amount_confidence","REAL"),
        ("craft_complexity_confidence","REAL"),
        ("photo_type_confidence",    "REAL"),
        ("price_band",               "TEXT"),
        ("price_band_confidence",    "REAL"),
        ("metal_weight",              "TEXT"),
        ("metal_weight_confidence",  "REAL"),
        ("low_confidence_fields",    "TEXT"),
        ("needs_review",             "INTEGER DEFAULT 0"),
    ]
    for col, typ in sq_cols:
        try:
            cur.execute(f"ALTER TABLE staging_queue ADD COLUMN {col} {typ}")
            print(f"  + staging_queue.{col}")
        except Exception:
            pass  # already exists

    conn.commit()
    conn.close()
    print("[OK] Migration complete")


if __name__ == "__main__":
    migrate()
