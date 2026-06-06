"""import_quotes.py - 從 CSV 匯入舊報價記錄

CSV 格式（第一行為 header）：
  description,final_price,material,gemstone,gemstone_origin,quote_date,notes

範例：
  紅寶石戒指,85000,18k黃金,紅寶石,緬甸,2024-01-15,豬血紅
  藍寶石項鍊,120000,鉑金,藍寶石,斯里蘭卡,2023-11-20,

使用方式：
  python -m scripts.import_quotes data/quotes.csv
  python -m scripts.import_quotes data/quotes.csv --dry-run
"""
import csv
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

VALID_MATERIALS = {
    "925銀", "18k黃金", "18k白金", "18k玫瑰金", "鉑金", "其他金屬"
}

PRICE_BAND_RANGES = [
    (0,      10000,  "< 1萬"),
    (10000,  30000,  "1-3萬"),
    (30000,  60000,  "3-6萬"),
    (60000,  100000, "6-10萬"),
    (100000, 150000, "10-15萬"),
    (150000, None,   "> 15萬"),
]

def price_to_band(price: int) -> str:
    for lo, hi, label in PRICE_BAND_RANGES:
        if hi is None or price < hi:
            return label
    return "> 15萬"


def import_csv(csv_path: Path, dry_run: bool = False):
    if not csv_path.exists():
        print(f"[ERROR] 找不到檔案：{csv_path}")
        sys.exit(1)

    rows = []
    errors = []

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"description", "final_price"}
        if not required.issubset(set(reader.fieldnames or [])):
            print(f"[ERROR] CSV 缺少必要欄位：{required}")
            sys.exit(1)

        for i, row in enumerate(reader, start=2):
            line_errors = []

            desc = row.get("description", "").strip()
            if not desc:
                line_errors.append("description 不能為空")

            try:
                price = int(str(row.get("final_price", "")).strip())
                if price <= 0:
                    raise ValueError()
            except ValueError:
                line_errors.append("final_price 需為正整數")
                price = 0

            material = row.get("material", "").strip() or None
            gemstone = row.get("gemstone", "").strip() or None
            origin   = row.get("gemstone_origin", "").strip() or None
            date_val = row.get("quote_date", "").strip() or None
            notes    = row.get("notes", "").strip() or None

            if line_errors:
                errors.append(f"  第 {i} 行：{', '.join(line_errors)}")
                continue

            rows.append((desc, price, material, gemstone, origin, date_val, notes))

    if errors:
        print(f"[WARN] 以下 {len(errors)} 行有錯誤，將跳過：")
        for e in errors:
            print(e)

    if not rows:
        print("[ERROR] 沒有可匯入的資料")
        sys.exit(1)

    if dry_run:
        print(f"[DRY-RUN] 將匯入 {len(rows)} 筆（未實際寫入）：")
        for r in rows[:5]:
            print(f"  {r[0]} | {r[1]:,} | {r[2]} | {r[3]}")
        if len(rows) > 5:
            print(f"  ... 共 {len(rows)} 筆")
        return

    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()
    cur.executemany(
        """INSERT INTO quotes (description, final_price, material, gemstone,
                               gemstone_origin, quote_date, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows
    )
    conn.commit()
    conn.close()
    print(f"[OK] 成功匯入 {len(rows)} 筆報價，跳過 {len(errors)} 筆錯誤")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not paths:
        print("Usage: python -m scripts.import_quotes <csv_file> [--dry-run]")
        sys.exit(1)
    import_csv(Path(paths[0]), dry_run=dry)
