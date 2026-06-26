"""reclassify_gemini_batch.py - 用 Gemini Flash 重跑全部既有照片標籤

可斷點續跑：進度存在 db/reclassify_progress.json，重跑會跳過已完成的。
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH
from scripts.classify_gemini import classify_image, CONFIDENCE_THRESHOLDS

PROGRESS_FILE = Path(__file__).resolve().parent.parent / "db" / "reclassify_progress.json"


def load_progress() -> set:
    if PROGRESS_FILE.exists():
        try:
            return set(json.loads(PROGRESS_FILE.read_text()).get("done_ids", []))
        except Exception:
            pass
    return set()


def save_progress(done_ids: set):
    PROGRESS_FILE.write_text(json.dumps({"done_ids": list(done_ids)}))


def main(limit=None, skip_done=True, dry_run=False):
    done_ids = load_progress() if skip_done else set()

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, full_path FROM photos ORDER BY id").fetchall()

    todo = [
        r for r in rows
        if (not skip_done or r["id"] not in done_ids)
        and r["full_path"]
        and Path(r["full_path"]).exists()
    ]
    if limit:
        todo = todo[:limit]

    total = len(todo)
    print(f"待重跑: {total} 張（已完成 {len(done_ids)} 張，跳過 {len(rows)-total-len(done_ids)} 張找不到檔案）")
    if dry_run:
        print("[Dry run] 不實際呼叫 API 或更新 DB")
        return

    ok = err = needs_review = 0

    for i, row in enumerate(todo):
        photo_id = row["id"]
        path = Path(row["full_path"])

        try:
            result = classify_image(path)

            conn.execute("""
                UPDATE photos SET
                    category=?,          category_confidence=?,
                    color=?,             color_confidence=?,
                    gemstone=?,          gemstone_confidence=?,
                    stone_shape=?,       stone_shape_confidence=?,
                    stone_size=?,        stone_size_confidence=?,
                    material=?,          material_confidence=?,
                    metal_color=?,
                    style=?,             style_confidence=?,
                    setting_amount=?,
                    craft_complexity=?,
                    photo_type=?,
                    price_band=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                result["category"],        result["category_confidence"],
                result["color"],           result["color_confidence"],
                result["gemstone"],        result["gemstone_confidence"],
                result["stone_shape"],     result["stone_shape_confidence"],
                result["stone_size"],      result["stone_size_confidence"],
                result["material"],        result["material_confidence"],
                result["metal_color"],
                result["style"],           result["style_confidence"],
                result["setting_amount"],
                result["craft_complexity"],
                result["photo_type"],
                result["price_band"],
                photo_id,
            ))
            conn.commit()

            done_ids.add(photo_id)
            if ok % 50 == 49:
                save_progress(done_ids)

            ok += 1
            low = result["low_confidence_fields"]
            if low:
                needs_review += 1
                flag = f"  ⚠ {', '.join(low)}"
            else:
                flag = "  ✓"
            print(f"[{i+1}/{total}] #{photo_id} {result['category']} {result.get('gemstone','')} {result.get('material','')}{flag}")

        except Exception as e:
            err += 1
            print(f"[{i+1}/{total}] #{photo_id} 錯誤: {e}")

        time.sleep(0.4)  # ~2.5 req/s，留在免費額度內

    save_progress(done_ids)
    conn.close()
    print(f"\n完成 {ok} 張  |  錯誤 {err} 張  |  需人工複核 {needs_review} 張 ({needs_review*100//max(ok,1)}%)")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="用 Gemini Flash 重跑全部照片標籤")
    p.add_argument("--limit",    type=int,  default=None, help="只跑前 N 張（測試用）")
    p.add_argument("--no-skip",  action="store_true",    help="重跑全部，包含已完成的")
    p.add_argument("--dry-run",  action="store_true",    help="只顯示待跑清單，不呼叫 API")
    args = p.parse_args()
    main(limit=args.limit, skip_done=not args.no_skip, dry_run=args.dry_run)
