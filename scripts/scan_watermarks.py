"""scan_watermarks.py — 掃描現有「情境」照片，標記出有文字／浮水印／他牌名稱的

只『標記』不刪除。標記後到網頁 App 的情境模式，點「⚠ 疑似浮水印」篩選審查，
確認是別家浮水印/文字的就刪（刪除會同步移除原圖與縮圖），要保留的按「保留」清除標記。

用法（在 Mac 上跑，需 GEMINI_API_KEY）：
  python3 -m scripts.02_migrate            # 先補欄位（第一次）
  python3 -m scripts.scan_watermarks       # 只掃尚未檢查的情境照
  python3 -m scripts.scan_watermarks --rescan   # 全部情境照重掃
  python3 -m scripts.scan_watermarks --limit 50 # 只掃前 50 張（試跑）
"""
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH
from scripts.detect_watermark import detect_text

try:
    from config.settings import FULL_DIR, THUMB_DIR, MICRO_DIR
except Exception:
    FULL_DIR = THUMB_DIR = MICRO_DIR = None


def _resolve_path(r):
    """在多個可能的位置中找出真的存在的照片檔（縮圖優先，快）。找不到回 None。"""
    cands = [r["thumb_path"], r["full_path"], r["original_path"]]
    fn = r["filename"]
    if fn:
        for d in (THUMB_DIR, FULL_DIR, MICRO_DIR):
            if d:
                cands.append(str(Path(d) / fn))
    for c in cands:
        if c and Path(c).exists():
            return c
    return None


def scan(rescan: bool = False, limit: int = 0):
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    where = "photo_type = '情境'"
    if not rescan:
        where += " AND watermark_flag IS NULL"   # 只掃還沒檢查過的
    sql = f"SELECT id, full_path, thumb_path, original_path, filename FROM photos WHERE {where} ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()
    total = len(rows)
    print(f"要掃描的情境照：{total} 張")
    if total == 0:
        conn.close()
        return

    flagged = missing = 0
    for i, r in enumerate(rows, 1):
        path = _resolve_path(r)
        if not path:
            missing += 1
            if missing <= 5:   # 只印前幾筆，避免洗版
                print(f"  [{i}/{total}] #{r['id']} 找不到檔案，跳過（DB 記錄：thumb={r['thumb_path']} full={r['full_path']}）")
            continue
        res = detect_text(path)
        if res["kind"] == "錯誤":
            print(f"  [{i}/{total}] #{r['id']} 偵測失敗，跳過：{res['sample']}")
            continue
        flag = 1 if res["has_text"] else 0
        note = f"{res['kind']}｜{res['sample']}" if res["has_text"] else None
        conn.execute(
            "UPDATE photos SET watermark_flag = ?, watermark_note = ? WHERE id = ?",
            (flag, note, r["id"]),
        )
        conn.commit()
        if flag:
            flagged += 1
            print(f"  [{i}/{total}] ⚠ #{r['id']} {r['filename']} — {note}")
        elif i % 20 == 0:
            print(f"  [{i}/{total}] …乾淨 {i - flagged} 張")
        time.sleep(0.05)   # 輕微節流，避免打太快

    conn.close()
    print(f"\n完成：共標記 {flagged} 張疑似有浮水印/文字。")
    if missing:
        print(f"（另有 {missing} 張找不到檔案，已跳過）")
    print("→ 到網頁 App 情境模式，點「⚠ 疑似浮水印」篩選審查後刪除或保留。")


if __name__ == "__main__":
    rescan = "--rescan" in sys.argv
    limit = 0
    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except (ValueError, IndexError):
            limit = 0
    scan(rescan=rescan, limit=limit)
