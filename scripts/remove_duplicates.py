"""remove_duplicates.py - 用 embedding 相似度找出重複照片並刪除

相似度 > 0.985 視為重複，每組只保留最早的一張。

執行：
  python3 scripts/remove_duplicates.py          ← 預覽（不刪除）
  python3 scripts/remove_duplicates.py --delete ← 真正刪除
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, BASE_DIR

EMBED_CACHE_FILE = BASE_DIR / "data" / "embeddings_cache.npz"
THRESHOLD = 0.985   # 相似度閾值，越高越嚴格（只刪幾乎一模一樣的）


def main():
    do_delete = '--delete' in sys.argv

    if not EMBED_CACHE_FILE.exists():
        print("❌ 找不到 embeddings_cache.npz，請先執行 classify_setting_amount.py")
        sys.exit(1)

    # 載入快取
    print("載入 embedding 快取…")
    data = np.load(EMBED_CACHE_FILE, allow_pickle=True)
    ids_arr  = [str(x) for x in data['ids']]
    emb_arr  = data['embeddings'].astype(np.float32)

    # 只處理 DB 中存在的照片
    conn = sqlite3.connect(SQLITE_PATH)
    rows = conn.execute("SELECT id, full_path, filename FROM photos WHERE full_path IS NOT NULL").fetchall()
    conn.close()
    db_ids = {str(r[0]) for r in rows}
    id_to_row = {str(r[0]): r for r in rows}

    # 過濾快取，只保留 DB 中存在的
    valid_idx = [i for i, pid in enumerate(ids_arr) if pid in db_ids]
    valid_ids  = [ids_arr[i] for i in valid_idx]
    valid_embs = emb_arr[valid_idx]

    print(f"共 {len(valid_ids)} 張照片的 embedding")

    # 批次計算相似度矩陣（分批避免 OOM）
    BATCH = 500
    n = len(valid_ids)
    to_delete = set()   # 要刪除的 photo id（字串）

    print(f"計算相似度（閾值 {THRESHOLD}）…")
    for i in range(0, n, BATCH):
        batch_embs = valid_embs[i:i+BATCH]   # (B, dim)
        sims = batch_embs @ valid_embs.T       # (B, n)
        for bi, row_sims in enumerate(sims):
            gi = i + bi
            if valid_ids[gi] in to_delete:
                continue
            # 找出所有與 gi 相似的（排除自己，且 index > gi 避免重複）
            dups = np.where((row_sims > THRESHOLD))[0]
            for dj in dups:
                if dj > gi and valid_ids[dj] not in to_delete:
                    to_delete.add(valid_ids[dj])

    print(f"\n找到 {len(to_delete)} 張重複照片（每組保留最早一張）")

    if not to_delete:
        print("沒有重複，不需要刪除。")
        return

    # 顯示清單
    print("\n重複照片清單：")
    for pid in sorted(to_delete, key=lambda x: int(x)):
        row = id_to_row.get(pid)
        if row:
            print(f"  id={pid}  {row[2]}")

    if not do_delete:
        print(f"\n（預覽模式，未刪除）加上 --delete 參數才會真正刪除")
        return

    # 真正刪除
    confirm = input(f"\n確定刪除這 {len(to_delete)} 張照片？（輸入 yes 確認）：").strip()
    if confirm != 'yes':
        print("取消。")
        return

    conn = sqlite3.connect(SQLITE_PATH)
    deleted = 0
    for pid in to_delete:
        row = id_to_row.get(pid)
        if not row:
            continue
        conn.execute("DELETE FROM photos WHERE id=?", (int(pid),))
        if row[1]:
            try:
                Path(row[1]).unlink(missing_ok=True)
            except Exception:
                pass
        deleted += 1
    conn.commit()
    conn.close()

    print(f"\n✅ 已刪除 {deleted} 張重複照片（DB 紀錄 + 檔案）")


if __name__ == "__main__":
    main()
