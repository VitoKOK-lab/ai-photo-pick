"""cleanup_gemstone.py - 清除 gemstone 欄位中誤混入的鑽石等級值

舊版 CLIP 分類把「無鑽/簡約/輕奢/豪鑲」等 style 值錯放到 gemstone 欄位，
導致詳情頁出現「無鑽」+「輕奢(20顆鑽內)」矛盾標籤。
本腳本將這些錯誤值清為 NULL。

執行：python3 scripts/cleanup_gemstone.py
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

# 這些值屬於 style，不屬於 gemstone
STYLE_VALS_IN_GEMSTONE = [
    '無鑽', '無鑽石',
    '簡約', '簡約(5顆鑽內)',
    '輕奢', '輕奢(20顆鑽內)',
    '豪鑲', '豪鑲滿鑲鑽',
]

conn = sqlite3.connect(SQLITE_PATH)

# 先統計有多少筆受影響
placeholders = ','.join('?' * len(STYLE_VALS_IN_GEMSTONE))
count = conn.execute(
    f"SELECT COUNT(*) FROM photos WHERE gemstone IN ({placeholders})",
    STYLE_VALS_IN_GEMSTONE
).fetchone()[0]

print(f"找到 {count} 筆 gemstone 欄位混入了鑽石等級值")

if count > 0:
    conn.execute(
        f"UPDATE photos SET gemstone = NULL WHERE gemstone IN ({placeholders})",
        STYLE_VALS_IN_GEMSTONE
    )
    conn.commit()
    print(f"✅ 已清除 {count} 筆錯誤值")
else:
    print("✅ 無需清理")

conn.close()
