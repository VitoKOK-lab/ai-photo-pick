"""teach.py - 互動式品項標記工具

照片自動開啟後切回終端，按單鍵立即送出（不需 Enter）。
每個品項標記 8 張後執行 reclassify_trained.py 自動分類全部。

執行：python3 scripts/teach.py
"""
import json
import subprocess
import sys
import termios
import time
import tty
from collections import Counter
from pathlib import Path
import sqlite3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, BASE_DIR

CATEGORIES = ['戒指', '手鏈', '墜子', '項鍊', '耳釘', '胸針', '其他']
LABELS_FILE = BASE_DIR / "data" / "training_labels.json"
TARGET_PER_CAT = 8


def getch() -> str:
    """讀取單一按鍵，不需 Enter。Ctrl+C 回傳 '\x03'。"""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch


def open_photo(path: Path):
    """開啟照片預覽，0.4 秒後把終端切回前景。"""
    subprocess.Popen(
        ['open', str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.45)
    # 把終端切回前景（Terminal / iTerm2 都試）
    subprocess.run(
        ['osascript', '-e',
         'try\n  tell application "iTerm2" to activate\non error\n'
         '  tell application "Terminal" to activate\nend try'],
        capture_output=True,
        timeout=2,
    )


def show_progress(cat_counts):
    lines = []
    for c in CATEGORIES:
        n = cat_counts.get(c, 0)
        bar = '█' * n + '░' * max(0, TARGET_PER_CAT - n)
        done = '✓' if n >= TARGET_PER_CAT else f'{n}/{TARGET_PER_CAT}'
        lines.append(f"  {c:3s}  {bar}  {done}")
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

    # 照片排序：最缺的品項優先
    priority_order = sorted(CATEGORIES, key=lambda c: cat_counts.get(c, 0))
    rows = []
    seen_ids: set = set()
    for cat in priority_order:
        for r in conn.execute(
            "SELECT id, full_path, filename, category FROM photos "
            "WHERE full_path IS NOT NULL AND category = ? ORDER BY RANDOM()",
            (cat,)
        ).fetchall():
            if r['id'] not in seen_ids:
                rows.append(r)
                seen_ids.add(r['id'])
    for r in conn.execute(
        "SELECT id, full_path, filename, category FROM photos "
        "WHERE full_path IS NOT NULL ORDER BY RANDOM()"
    ).fetchall():
        if r['id'] not in seen_ids:
            rows.append(r)
            seen_ids.add(r['id'])
    conn.close()

    print("\n" + "=" * 50)
    print("  品項標記工具  (單鍵送出，不用按 Enter)")
    print("=" * 50)
    print(f"共 {len(rows)} 張  |  目標：每類 {TARGET_PER_CAT} 張\n")
    print(show_progress(cat_counts))

    # 列出快捷鍵說明
    key_map = {str(i): c for i, c in enumerate(CATEGORIES, 1)}
    print()
    for k, c in key_map.items():
        print(f"  [{k}] {c}", end="   ")
    print(f"\n  [s] 跳過   [q] 儲存離開")
    print()

    labeled_this_session = 0

    for row in rows:
        pid = str(row['id'])
        if pid in labels:
            continue

        still_needed = [c for c in CATEGORIES if cat_counts[c] < TARGET_PER_CAT]
        if not still_needed:
            break

        full_path = Path(row['full_path'])
        if not full_path.exists():
            continue

        open_photo(full_path)

        # 顯示提示（覆蓋同一行更新用 \r，保持畫面乾淨）
        needed_keys = [k for k, c in key_map.items() if c in still_needed]
        print(f"\r照片: {row['filename'][:45]}  |  還缺: {''.join(needed_keys)}  ", end='', flush=True)

        ch = getch()

        if ch == '\x03' or ch == 'q':   # Ctrl+C 或 q
            print("\n中斷")
            break
        elif ch == 's' or ch == ' ':
            print(f"\r  ↷ 跳過{' ' * 40}")
            continue
        elif ch in key_map:
            cat = key_map[ch]
            labels[pid] = cat
            cat_counts[cat] += 1
            labeled_this_session += 1
            print(f"\r  ✓  {cat}{' ' * 40}")
        else:
            print(f"\r  ? 無效鍵 [{ch}]，跳過{' ' * 30}")

    # 儲存
    LABELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LABELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 50}")
    print(f"✅ 已儲存 {len(labels)} 筆（本次新增 {labeled_this_session}）\n")
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
