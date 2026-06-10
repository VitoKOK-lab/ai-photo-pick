"""init_cs_db.py - 只建立客服訂單追蹤所需的 SQLite 資料表。

不需 chromadb，適合雲端輕量部署。
執行：python scripts/init_cs_db.py
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH
from scripts._schema import SCHEMA

SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(SQLITE_PATH)
conn.executescript(SCHEMA)
conn.commit()
conn.close()
print(f"[OK] 資料庫已建立：{SQLITE_PATH}")
