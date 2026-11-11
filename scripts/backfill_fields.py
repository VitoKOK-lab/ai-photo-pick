"""backfill_fields.py — 幫雲端「審美資料庫」補齊 category/color/gemstone/style/
photo_type/stone_shape 這些標籤，只用檔名比對、純文字 JSON，不會重傳圖片。

跟 push_to_cloud.py 的差別：push_to_cloud.py 是「搬照片」（要傳圖片本體，
量大很慢）；這支是「補標籤」（只傳幾個文字欄位，秒傳）。雲端已經存在的
欄位不會被覆蓋，只補目前是空的。

用法：
  python3 -m scripts.backfill_fields              # 全部跑一次
  python3 -m scripts.backfill_fields --limit 50   # 先跑 50 張試跑
"""
import json
import sqlite3
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

CLOUD_URL = "https://ai-photo-pick.vitokok.workers.dev"


def _backfill_one(fields: dict, retries: int = 2):
    body = json.dumps(fields).encode("utf-8")
    req = urllib.request.Request(
        f"{CLOUD_URL}/api/photos/backfill",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ai-photo-pick-backfill/1.0",
        },
    )
    last_status, last_body = 0, ""
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            last_status, last_body = e.code, e.read().decode()
        except Exception as e:
            last_status, last_body = 0, str(e)
        if last_status not in (0, 500, 502, 503, 504):
            break
    return last_status, last_body


def run(limit=0):
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT filename, category, color, gemstone, style, photo_type, stone_shape "
        "FROM photos ORDER BY id"
    ).fetchall()
    conn.close()

    if limit:
        rows = rows[:limit]

    print(f"共 {len(rows)} 張要補欄位（只傳文字，不傳圖片）")
    ok = fail = 0
    for i, r in enumerate(rows, 1):
        if not r["filename"]:
            continue
        status, body = _backfill_one({
            "filename": r["filename"],
            "category": r["category"],
            "color": r["color"],
            "gemstone": r["gemstone"],
            "style": r["style"],
            "photo_type": r["photo_type"],
            "stone_shape": r["stone_shape"],
        })
        if status == 200:
            ok += 1
        else:
            fail += 1
            if fail <= 10:
                print(f"  [{i}/{len(rows)}] {r['filename']} 失敗 ({status}): {body[:150]}")
        if i % 500 == 0:
            print(f"  [{i}/{len(rows)}] 已處理 {ok} 張…")

    print(f"\n完成：成功 {ok}、失敗 {fail}")


if __name__ == "__main__":
    limit = 0
    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except (ValueError, IndexError):
            limit = 0
    run(limit=limit)
