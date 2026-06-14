"""batch_reclassify.py - 用 CLIP 批次補齊照片標籤

預設：只補空白 / '未定' 欄位，不蓋掉已有的值。
加 --overwrite 旗標可強制全部重跑。
跑法：
    python3 scripts/batch_reclassify.py
    python3 scripts/batch_reclassify.py --overwrite
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH
from scripts.classify import classify_one

# classify.py 回傳的維度 → DB 欄位名稱對應
DIM_TO_COL = {
    "color":           "color",
    "stone_shape":     "stone_shape",
    "stone_size":      "stone_size",
    "material":        "material",
    "gemstone":        "gemstone",
    "price_band":      "price_band",
    "setting_amount":  "setting_amount",
    "craft_complexity":"craft_complexity",
    "metal_color":     "metal_color",
    # category / style 從資料夾來，不動
}

UNDECIDED = "未定"


def needs_update(val: str | None) -> bool:
    return val is None or val.strip() == "" or val == UNDECIDED


def derive_metal_color(material: str | None) -> str | None:
    if material in ("18K黃金", "18K玫瑰金"):
        return "金"
    if material in ("18K白金", "925銀", "鉑金"):
        return "銀"
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true",
                        help="強制覆蓋已有的標籤值")
    args = parser.parse_args()

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    # 確保欄位存在（舊 DB 可能缺少）
    for col in ("setting_amount", "craft_complexity", "metal_color", "stone_shape", "stone_size"):
        try:
            conn.execute(f"ALTER TABLE photos ADD COLUMN {col} TEXT")
            conn.commit()
            print(f"[DB] 新增欄位：{col}")
        except Exception:
            pass  # 已存在

    cur = conn.cursor()
    cur.execute("SELECT id, full_path, category, style FROM photos ORDER BY id")
    rows = cur.fetchall()
    total = len(rows)
    print(f"[INFO] 共 {total} 張照片，開始分類…")
    if args.overwrite:
        print("[INFO] --overwrite 模式：強制覆蓋所有欄位")

    done = 0
    errors = 0
    skipped = 0
    t0 = time.time()

    for row in rows:
        photo_id  = row["id"]
        full_path = row["full_path"]

        img_path = Path(full_path)
        if not img_path.exists():
            print(f"  [SKIP] id={photo_id} 檔案不存在：{full_path}")
            skipped += 1
            continue

        try:
            classification, _ = classify_one(img_path)
        except Exception as e:
            print(f"  [ERR]  id={photo_id}: {e}")
            errors += 1
            continue

        # 判斷哪些欄位需要更新
        update_fields = {}
        for dim, col in DIM_TO_COL.items():
            if dim not in classification:
                continue
            label = classification[dim]["label"]
            conf  = classification[dim]["confidence"]

            # 取得現有值
            cur2 = conn.cursor()
            cur2.execute(f"SELECT {col} FROM photos WHERE id=?", (photo_id,))
            existing = (cur2.fetchone() or [None])[0]

            if args.overwrite or needs_update(existing):
                if label != UNDECIDED:
                    update_fields[col] = label
                    update_fields[col + "_confidence"] = conf  # 有些欄位有 confidence 欄

        # 從 material 推導 metal_color（如果 CLIP 沒給或給了也補一次）
        if "metal_color" not in update_fields and "material" in update_fields:
            derived = derive_metal_color(update_fields.get("material"))
            if derived:
                update_fields["metal_color"] = derived

        if not update_fields:
            done += 1
            continue

        # 只更新存在的欄位（confidence 欄可能不存在就跳過）
        valid_fields = {}
        col_info = conn.execute("PRAGMA table_info(photos)").fetchall()
        existing_cols = {c[1] for c in col_info}
        for k, v in update_fields.items():
            if k in existing_cols:
                valid_fields[k] = v

        if valid_fields:
            set_clause = ", ".join(f"{k}=?" for k in valid_fields)
            conn.execute(
                f"UPDATE photos SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                list(valid_fields.values()) + [photo_id],
            )

        done += 1
        if done % 100 == 0:
            conn.commit()
            elapsed = time.time() - t0
            per_photo = elapsed / done
            remaining = (total - done) * per_photo
            print(f"  進度 {done}/{total}  ({done*100//total}%)  "
                  f"已用 {elapsed:.0f}s  預估剩 {remaining:.0f}s")

    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    print(f"\n✅ 完成！處理 {done} 張，跳過 {skipped} 張，錯誤 {errors} 張，共 {elapsed:.0f} 秒")


if __name__ == "__main__":
    main()
