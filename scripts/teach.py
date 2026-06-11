"""teach.py - 互動式品項標記工具

給系統「教學資料」，讓 KNN 分類器能學會你的分類方式。
每個品項標記 15 張照片後，執行 reclassify_trained.py 自動分類全部。

執行：python3 scripts/teach.py
"""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
import sqlite3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, BASE_DIR

CATEGORIES = ['戒指', '手鏈', '墜子', '項鍊', '耳釘', '胸針', '其他']
LABELS_FILE = BASE_DIR / "data" / "training_labels.json"
TARGET_PER_CAT = 8


def show_progress(cat_counts):
    lines = []
    for c in CATEGORIES:
        n = cat_counts.get(c, 0)
        bar = '█' * n + '░' * max(0, TARGET_PER_CAT - n)
        done = '✓' if n >= TARGET_PER_CAT else f'{n:2d}/{TARGET_PER_CAT}'
        lines.append(f"  {c:4s} {bar} {done}")
    return '\n'.join(lines)


def main():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    # 載入已有標記
    labels = {}
    if LABELS_FILE.exists():
        with open(LABELS_FILE, encoding='utf-8') as f:
            labels = json.load(f)

    cat_counts = Counter(labels.values())

    # 取得所有照片：按「最缺的品項」優先排序，已夠的品項放最後
    # 計算每個品項的優先順序（還缺越多 = 越前面）
    priority_order = sorted(CATEGORIES, key=lambda c: cat_counts.get(c, 0))
    # 把優先品項對應的照片先撈，其餘隨機附在後面
    rows = []
    seen_ids = set()
    for cat in priority_order:
        cat_rows = conn.execute(
            "SELECT id, full_path, filename, category FROM photos "
            "WHERE full_path IS NOT NULL AND category = ? ORDER BY RANDOM()",
            (cat,)
        ).fetchall()
        for r in cat_rows:
            if r['id'] not in seen_ids:
                rows.append(r)
                seen_ids.add(r['id'])
    # 其餘（DB 未分類或品項不在清單）
    other_rows = conn.execute(
        "SELECT id, full_path, filename, category FROM photos "
        "WHERE full_path IS NOT NULL ORDER BY RANDOM()"
    ).fetchall()
    for r in other_rows:
        if r['id'] not in seen_ids:
            rows.append(r)
            seen_ids.add(r['id'])
    conn.close()

    print("\n" + "=" * 55)
    print("  品項標記工具  (KNN 訓練資料)")
    print("=" * 55)
    print(f"共 {len(rows)} 張照片  |  目標：每類 {TARGET_PER_CAT} 張\n")
    print(show_progress(cat_counts))
    print()

    labeled_this_session = 0

    for row in rows:
        pid = str(row['id'])
        if pid in labels:
            continue  # 已標記過

        still_needed = [c for c in CATEGORIES if cat_counts[c] < TARGET_PER_CAT]
        if not still_needed:
            break

        full_path = Path(row['full_path'])
        if not full_path.exists():
            continue

        # 開啟照片預覽
        try:
            subprocess.Popen(
                ['open', str(full_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

        print(f"\n{'─' * 55}")
        print(f"照片: {row['filename']}")
        db_cat = row['category'] or '未分類'
        print(f"DB 目前: {db_cat}")
        print(f"還需要: {', '.join(still_needed)}\n")

        for i, c in enumerate(CATEGORIES, 1):
            mark = ' ← 需要' if c in still_needed else ''
            print(f"  {i}. {c}{mark}")
        print()
        print("  s. 跳過   q. 儲存離開")

        try:
            choice = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n中斷")
            break

        if choice == 'q':
            break
        elif choice in ('s', ''):
            continue
        elif choice.isdigit() and 1 <= int(choice) <= len(CATEGORIES):
            cat = CATEGORIES[int(choice) - 1]
            labels[pid] = cat
            cat_counts[cat] += 1
            labeled_this_session += 1
            print(f"✓  →  {cat}")
        else:
            print("無效，跳過")

    # 儲存
    LABELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LABELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)

    total = len(labels)
    print(f"\n{'=' * 55}")
    print(f"✅ 已儲存 {total} 筆標記（本次新增 {labeled_this_session}）\n")
    print(show_progress(cat_counts))

    if all(cat_counts[c] >= TARGET_PER_CAT for c in CATEGORIES):
        print(f"\n✅ 訓練資料充足！")
        print(f"下一步：python3 scripts/reclassify_trained.py")
    else:
        missing = [c for c in CATEGORIES if cat_counts[c] < TARGET_PER_CAT]
        print(f"\n⚠  尚不足：{', '.join(missing)}")
        print(f"繼續標記：python3 scripts/teach.py")


if __name__ == "__main__":
    main()
