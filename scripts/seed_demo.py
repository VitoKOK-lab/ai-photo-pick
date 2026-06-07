"""seed_demo.py - 插入示範資料（員工、客戶、成交記錄）"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

conn = sqlite3.connect(SQLITE_PATH)
conn.row_factory = sqlite3.Row

# ─── 員工 ─────────────────────────────────────────────────────────────────────
STAFF = ["小雅", "志明", "怡君", "建宏"]

staff_ids = {}
for name in STAFF:
    try:
        cur = conn.execute("INSERT INTO staff(name) VALUES(?)", (name,))
        staff_ids[name] = cur.lastrowid
        print(f"  ✓ 員工：{name}")
    except sqlite3.IntegrityError:
        row = conn.execute("SELECT id FROM staff WHERE name=?", (name,)).fetchone()
        staff_ids[name] = row["id"]
        print(f"  - 員工已存在：{name}")

# ─── 客戶 ─────────────────────────────────────────────────────────────────────
CUSTOMERS = [
    { "name": "林美玲", "line_id": "@meiling",  "phone": "0912-345-678", "notes": "偏好彩寶，預算彈性大", "tags": ["彩寶", "自然", "靈動", "玫瑰金"] },
    { "name": "陳雅婷", "line_id": "@yating88", "phone": "0923-456-789", "notes": "新婚，找婚戒對戒",   "tags": ["鑽石", "古典", "K金", "婚戒"] },
    { "name": "王建志", "line_id": "@jz_wang",  "phone": None,           "notes": "幫太太挑禮物",        "tags": ["現代", "簡約", "白金"] },
    { "name": "張淑芬", "line_id": None,         "phone": "0934-567-890", "notes": "喜歡花朵主題",        "tags": ["浪漫", "花朵", "玫瑰金", "粉色"] },
    { "name": "李怡萱", "line_id": "@yixuan",   "phone": "0945-678-901", "notes": "收藏家，品味獨特",    "tags": ["古典", "璀璨", "頂級", "鑽石"] },
]

customer_ids = {}
for c in CUSTOMERS:
    try:
        cur = conn.execute(
            "INSERT INTO customers(name, line_id, phone, notes, session_count) VALUES(?,?,?,?,1)",
            (c["name"], c["line_id"], c["phone"], c["notes"])
        )
        cid = cur.lastrowid
        customer_ids[c["name"]] = cid
        for tag in c["tags"]:
            try:
                conn.execute("INSERT INTO customer_tags(customer_id, tag) VALUES(?,?)", (cid, tag))
            except sqlite3.IntegrityError:
                pass
        print(f"  ✓ 客戶：{c['name']}  標籤：{', '.join(c['tags'])}")
    except Exception as e:
        print(f"  - 客戶已存在或錯誤：{c['name']} ({e})")

# ─── 成交記錄 ─────────────────────────────────────────────────────────────────
TRANSACTIONS = [
    { "item_name": "玫瑰金彩寶戒指",    "category": "戒指", "material": "18K玫瑰金", "gemstone": "粉色剛玉", "stone_spec": "1.2ct 橢圓切",  "metal_weight": 3.8,  "price": 68000,  "sale_date": "2025-05-20", "client_name": "林美玲" },
    { "item_name": "鑽石婚戒對戒",       "category": "戒指", "material": "鉑金PT950", "gemstone": "鑽石",     "stone_spec": "0.5ct F VS1",   "metal_weight": 5.2,  "price": 128000, "sale_date": "2025-05-15", "client_name": "陳雅婷" },
    { "item_name": "白金鑽石項鍊",       "category": "項鍊", "material": "18K白金",   "gemstone": "鑽石",     "stone_spec": "0.3ct G VVS2",  "metal_weight": 4.1,  "price": 85000,  "sale_date": "2025-05-10", "client_name": "李怡萱" },
    { "item_name": "玫瑰金花朵耳環",     "category": "耳環", "material": "18K玫瑰金", "gemstone": "珍珠",     "stone_spec": "8mm 圓珠 AAA",  "metal_weight": 2.6,  "price": 32000,  "sale_date": "2025-05-05", "client_name": "張淑芬" },
    { "item_name": "極簡白金手環",       "category": "手環", "material": "鉑金PT900", "gemstone": None,        "stone_spec": None,             "metal_weight": 8.5,  "price": 55000,  "sale_date": "2025-04-28", "client_name": "王建志" },
    { "item_name": "祖母綠鑽石套鍊",     "category": "項鍊", "material": "18K黃金",   "gemstone": "祖母綠",   "stone_spec": "2.1ct 哥倫比亞", "metal_weight": 6.3,  "price": 220000, "sale_date": "2025-04-20", "client_name": "李怡萱" },
    { "item_name": "粉鑽玫瑰金戒指",     "category": "戒指", "material": "18K玫瑰金", "gemstone": "粉鑽",     "stone_spec": "0.2ct 粉鑽 SI", "metal_weight": 2.9,  "price": 96000,  "sale_date": "2025-04-15", "client_name": "林美玲" },
    { "item_name": "黃金古典胸針",       "category": "胸針", "material": "18K黃金",   "gemstone": "紅寶石",   "stone_spec": "0.8ct 緬甸",    "metal_weight": 7.2,  "price": 78000,  "sale_date": "2025-04-08", "client_name": None },
]

for tx in TRANSACTIONS:
    conn.execute(
        """INSERT INTO transactions
           (item_name, category, material, gemstone, stone_spec, metal_weight, price, sale_date, client_name)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (tx["item_name"], tx["category"], tx["material"], tx["gemstone"],
         tx["stone_spec"], tx["metal_weight"], tx["price"], tx["sale_date"], tx["client_name"])
    )
    print(f"  ✓ 成交：{tx['item_name']}  NT${tx['price']:,}")

conn.commit()
conn.close()
print("\n✅ 示範資料已寫入完成！")
print("   員工可在 APP 中直接切換，客戶/成交記錄可在 APP 中刪除。")
