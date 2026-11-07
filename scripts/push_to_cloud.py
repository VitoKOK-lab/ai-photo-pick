"""push_to_cloud.py — 把本機照片庫搬到雲端版「線上選品」（Cloudflare）

只呼叫雲端公開 API（POST /api/photos），不需要任何 Cloudflare 金鑰。
每張照片會連同既有的品項/寶石/風格標籤一起上傳，審片時看得到。

可重複執行（中斷後重跑會自動接續，已上傳過的不會重複上傳）。

用法：
  python3 -m scripts.push_to_cloud              # 上傳全部還沒搬過的照片
  python3 -m scripts.push_to_cloud --limit 50   # 先搬 50 張試跑
  python3 -m scripts.push_to_cloud --dry-run    # 只顯示會做什麼，不真的上傳
"""
import json
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, FULL_DIR, THUMB_DIR, MICRO_DIR

CLOUD_URL = "https://ai-photo-pick.vitokok.workers.dev"
PROGRESS_FILE = Path(__file__).resolve().parent.parent / ".cloud_migration_progress.json"


def _load_progress():
    if PROGRESS_FILE.exists():
        try:
            return set(json.loads(PROGRESS_FILE.read_text()))
        except Exception:
            return set()
    return set()


def _save_progress(done_ids):
    PROGRESS_FILE.write_text(json.dumps(sorted(done_ids)))


def _resolve_image(row):
    """找出照片實際存在的檔案（原圖優先，找不到才退而求其次用縮圖）。"""
    cands = [row["full_path"], row["thumb_path"]]
    fn = row["filename"]
    if fn:
        for d in (FULL_DIR, THUMB_DIR, MICRO_DIR):
            cands.append(str(Path(d) / fn))
    for c in cands:
        if c and Path(c).exists():
            return Path(c)
    return None


def _multipart_upload(path: Path, fields: dict):
    """純標準庫組 multipart/form-data 上傳一張照片 + 欄位，回傳 (status, body)。"""
    boundary = "----cloudpush" + str(int(time.time() * 1000))
    parts = []
    for k, v in fields.items():
        if not v:
            continue
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        parts.append(f"{v}\r\n".encode())
    data = path.read_bytes()
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n".encode()
    )
    parts.append(data)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)

    req = urllib.request.Request(
        f"{CLOUD_URL}/api/photos",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            # 沒有 User-Agent 會被 Cloudflare 擋掉（code 1010）
            "User-Agent": "ai-photo-pick-migration/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


def run(limit=0, dry_run=False):
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, filename, full_path, thumb_path, category, gemstone, style, photo_type "
        "FROM photos ORDER BY id"
    ).fetchall()
    conn.close()

    done = _load_progress()
    todo = [r for r in rows if r["id"] not in done]
    if limit:
        todo = todo[:limit]

    print(f"本機共 {len(rows)} 張，已搬過 {len(done)} 張，本次要搬 {len(todo)} 張")
    if dry_run:
        for r in todo[:10]:
            print(f"  [dry-run] #{r['id']} {r['filename']}")
        if len(todo) > 10:
            print(f"  …還有 {len(todo) - 10} 張")
        return

    ok = miss = fail = 0
    for i, r in enumerate(todo, 1):
        path = _resolve_image(r)
        if not path:
            miss += 1
            print(f"  [{i}/{len(todo)}] #{r['id']} 找不到檔案，跳過")
            continue
        status, body = _multipart_upload(path, {
            "category": r["category"],
            "gemstone": r["gemstone"],
            "style": r["style"],
            "photo_type": r["photo_type"],
        })
        if status in (200, 201):
            ok += 1
            done.add(r["id"])
            if i % 20 == 0 or i == len(todo):
                _save_progress(done)  # 定期存進度，中斷也不會全部重來
                print(f"  [{i}/{len(todo)}] 已上傳 {ok} 張…")
        else:
            fail += 1
            print(f"  [{i}/{len(todo)}] #{r['id']} 上傳失敗 ({status}): {body[:150]}")
        time.sleep(0.05)  # 輕微節流

    _save_progress(done)
    print(f"\n完成：成功 {ok}、找不到檔案 {miss}、失敗 {fail}")
    print(f"→ 打開 {CLOUD_URL} 開始線上選品")
    if fail:
        print("（失敗的下次重跑這個腳本會自動重試，不會跳過）")


if __name__ == "__main__":
    limit = 0
    dry_run = "--dry-run" in sys.argv
    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except (ValueError, IndexError):
            limit = 0
    run(limit=limit, dry_run=dry_run)
