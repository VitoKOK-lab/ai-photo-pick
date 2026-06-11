"""teach.py - 互動式標記工具（品項 + 鑽石等級 + 鍊子粗細）

按單鍵立即送出，照片開啟後自動切回終端。

執行：
  python3 scripts/teach.py           ← 標記品項
  python3 scripts/teach.py --style   ← 標記鑽石等級
  python3 scripts/teach.py --chain   ← 標記鍊子粗細
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

# ── 品項設定 ─────────────────────────────────────────────────
CATEGORIES = ['戒指', '手鏈', '墜子', '項鍊', '耳釘', '胸針', '其他']
CAT_LABELS_FILE = BASE_DIR / "data" / "training_labels.json"

# ── 鑽石等級設定 ──────────────────────────────────────────────
STYLE_DISPLAY  = ['無鑽', '簡約', '輕奢', '豪鑲']
STYLE_DB_VALS  = ['無鑽', '簡約(5顆鑽內)', '輕奢(20顆鑽內)', '豪鑲滿鑲鑽']
STYLE_LABELS_FILE = BASE_DIR / "data" / "training_labels_style.json"

# ── 鍊子粗細設定 ──────────────────────────────────────────────
CHAIN_DISPLAY  = ['無鍊', '細鍊', '中等', '粗鍊']
CHAIN_DB_VALS  = ['無鍊', '細鍊', '中等', '粗鍊']
CHAIN_LABELS_FILE = BASE_DIR / "data" / "training_labels_chain.json"

TARGET_PER_CAT = 8


# ── 通用工具 ──────────────────────────────────────────────────

def getch() -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch


def open_photo(path: Path):
    subprocess.Popen(['open', str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.45)
    subprocess.run(
        ['osascript', '-e',
         'try\n  tell application "iTerm2" to activate\non error\n'
         '  tell application "Terminal" to activate\nend try'],
        capture_output=True, timeout=2,
    )


def show_progress(labels_dict, label_list, target):
    counts = Counter(labels_dict.values())
    lines = []
    for c in label_list:
        n = counts.get(c, 0)
        bar = '█' * n + '░' * max(0, target - n)
        done = '✓' if n >= target else f'{n}/{target}'
        lines.append(f"  {c:8s}  {bar}  {done}")
    return '\n'.join(lines)


def build_row_order(conn, label_list, labels_done):
    """最缺的品項優先顯示"""
    counts = Counter(labels_done.values())
    priority = sorted(label_list, key=lambda c: counts.get(c, 0))
    rows, seen = [], set()
    for cat in priority:
        for r in conn.execute(
            "SELECT id, full_path, filename, category, style FROM photos "
            "WHERE full_path IS NOT NULL AND category = ? ORDER BY RANDOM()", (cat,)
        ).fetchall():
            if r['id'] not in seen:
                rows.append(r)
                seen.add(r['id'])
    for r in conn.execute(
        "SELECT id, full_path, filename, category, style FROM photos "
        "WHERE full_path IS NOT NULL ORDER BY RANDOM()"
    ).fetchall():
        if r['id'] not in seen:
            rows.append(r)
            seen.add(r['id'])
    return rows


# ── 品項標記 ──────────────────────────────────────────────────

def run_category():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    labels = {}
    if CAT_LABELS_FILE.exists():
        with open(CAT_LABELS_FILE, encoding='utf-8') as f:
            labels = json.load(f)

    rows = build_row_order(conn, CATEGORIES, labels)
    conn.close()

    key_map = {str(i): c for i, c in enumerate(CATEGORIES, 1)}

    print("\n" + "=" * 50)
    print("  品項標記  (單鍵送出)")
    print("=" * 50)
    print(show_progress(labels, CATEGORIES, TARGET_PER_CAT))
    print()
    for k, c in key_map.items():
        print(f"  [{k}] {c}", end="   ")
    print(f"\n  [s] 跳過   [q] 儲存離開\n")

    new = 0
    for row in rows:
        pid = str(row['id'])
        if pid in labels:
            continue
        still_needed = [c for c in CATEGORIES if Counter(labels.values()).get(c, 0) < TARGET_PER_CAT]
        if not still_needed:
            break
        full_path = Path(row['full_path'])
        if not full_path.exists():
            continue

        open_photo(full_path)
        needed_keys = [k for k, c in key_map.items() if c in still_needed]
        print(f"\r{row['filename'][:48]}  |  還缺:[{''.join(needed_keys)}]  ", end='', flush=True)

        ch = getch()
        if ch in ('\x03', 'q'):
            print("\n中斷"); break
        elif ch in ('s', ' '):
            print(f"\r  ↷ 跳過{' '*40}")
        elif ch in key_map:
            cat = key_map[ch]
            labels[pid] = cat
            new += 1
            print(f"\r  ✓  {cat}{' '*40}")
        else:
            print(f"\r  ? 無效[{ch}]{' '*40}")

    CAT_LABELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CAT_LABELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"✅ 已儲存 {len(labels)} 筆（本次新增 {new}）\n")
    print(show_progress(labels, CATEGORIES, TARGET_PER_CAT))
    counts = Counter(labels.values())
    if all(counts.get(c, 0) >= TARGET_PER_CAT for c in CATEGORIES):
        print("\n✅ 訓練資料充足！下一步：python3 scripts/reclassify_trained.py")
    else:
        missing = [c for c in CATEGORIES if counts.get(c, 0) < TARGET_PER_CAT]
        print(f"\n⚠  尚不足：{', '.join(missing)}")


# ── 鑽石等級標記 ──────────────────────────────────────────────

def run_style():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    labels = {}
    if STYLE_LABELS_FILE.exists():
        with open(STYLE_LABELS_FILE, encoding='utf-8') as f:
            labels = json.load(f)

    # 所有照片，依 style 現況優先排序
    rows_all = conn.execute(
        "SELECT id, full_path, filename, category, style FROM photos "
        "WHERE full_path IS NOT NULL ORDER BY RANDOM()"
    ).fetchall()
    conn.close()

    key_map = {str(i): (STYLE_DISPLAY[i-1], STYLE_DB_VALS[i-1])
               for i in range(1, len(STYLE_DISPLAY)+1)}

    print("\n" + "=" * 50)
    print("  鑽石等級標記  (單鍵送出)")
    print("=" * 50)
    print(show_progress(labels, STYLE_DB_VALS, TARGET_PER_CAT))
    print()
    for k, (disp, _) in key_map.items():
        print(f"  [{k}] {disp}", end="   ")
    print(f"\n  [s] 跳過   [q] 儲存離開")
    print()
    print("  鑽石等級說明：")
    print("    無鑽   = 完全沒有鑽石")
    print("    簡約   = 5 顆以內小鑽")
    print("    輕奢   = 20 顆以內鑽石")
    print("    豪鑲   = 整體滿鑲鑽\n")

    new = 0
    for row in rows_all:
        pid = str(row['id'])
        if pid in labels:
            continue
        counts = Counter(labels.values())
        still_needed = [db for db in STYLE_DB_VALS if counts.get(db, 0) < TARGET_PER_CAT]
        if not still_needed:
            break
        full_path = Path(row['full_path'])
        if not full_path.exists():
            continue

        open_photo(full_path)
        print(f"\r{row['filename'][:45]}  品項:{row['category'] or '?'}  ", end='', flush=True)

        ch = getch()
        if ch in ('\x03', 'q'):
            print("\n中斷"); break
        elif ch in ('s', ' '):
            print(f"\r  ↷ 跳過{' '*40}")
        elif ch in key_map:
            disp, db_val = key_map[ch]
            labels[pid] = db_val
            new += 1
            print(f"\r  ✓  {disp}{' '*40}")
        else:
            print(f"\r  ? 無效[{ch}]{' '*40}")

    STYLE_LABELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STYLE_LABELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)

    counts = Counter(labels.values())
    print(f"\n{'='*50}")
    print(f"✅ 已儲存 {len(labels)} 筆（本次新增 {new}）\n")
    print(show_progress(labels, STYLE_DB_VALS, TARGET_PER_CAT))
    if all(counts.get(db, 0) >= TARGET_PER_CAT for db in STYLE_DB_VALS):
        print("\n✅ 鑽石等級訓練充足！")
        print("下一步：python3 scripts/reclassify_trained.py --style")
    else:
        missing = [STYLE_DISPLAY[STYLE_DB_VALS.index(db)] for db in STYLE_DB_VALS
                   if counts.get(db, 0) < TARGET_PER_CAT]
        print(f"\n⚠  尚不足：{', '.join(missing)}")
        print("繼續標記：python3 scripts/teach.py --style")


# ── 鍊子粗細標記 ──────────────────────────────────────────────

def run_chain_width():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    labels = {}
    if CHAIN_LABELS_FILE.exists():
        with open(CHAIN_LABELS_FILE, encoding='utf-8') as f:
            labels = json.load(f)

    rows_all = conn.execute(
        "SELECT id, full_path, filename, category, style FROM photos "
        "WHERE full_path IS NOT NULL ORDER BY RANDOM()"
    ).fetchall()
    conn.close()

    key_map = {str(i): (CHAIN_DISPLAY[i-1], CHAIN_DB_VALS[i-1])
               for i in range(1, len(CHAIN_DISPLAY)+1)}

    print("\n" + "=" * 50)
    print("  鍊子粗細標記  (單鍵送出)")
    print("=" * 50)
    print(show_progress(labels, CHAIN_DB_VALS, TARGET_PER_CAT))
    print()
    for k, (disp, _) in key_map.items():
        print(f"  [{k}] {disp}", end="   ")
    print(f"\n  [s] 跳過   [q] 儲存離開")
    print()
    print("  說明：")
    print("    無鍊 = 戒指/耳釘/單獨墜子（沒有鍊子）")
    print("    細鍊 = 纖細精緻鍊子（< 2mm）")
    print("    中等 = 標準鍊子（2-4mm）")
    print("    粗鍊 = 粗重鍊子（> 4mm）\n")

    new = 0
    for row in rows_all:
        pid = str(row['id'])
        if pid in labels:
            continue
        counts = Counter(labels.values())
        still_needed = [db for db in CHAIN_DB_VALS if counts.get(db, 0) < TARGET_PER_CAT]
        if not still_needed:
            break
        full_path = Path(row['full_path'])
        if not full_path.exists():
            continue

        open_photo(full_path)
        print(f"\r{row['filename'][:45]}  品項:{row['category'] or '?'}  ", end='', flush=True)

        ch = getch()
        if ch in ('\x03', 'q'):
            print("\n中斷"); break
        elif ch in ('s', ' '):
            print(f"\r  ↷ 跳過{' '*40}")
        elif ch in key_map:
            disp, db_val = key_map[ch]
            labels[pid] = db_val
            new += 1
            print(f"\r  ✓  {disp}{' '*40}")
        else:
            print(f"\r  ? 無效[{ch}]{' '*40}")

    CHAIN_LABELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHAIN_LABELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)

    counts = Counter(labels.values())
    print(f"\n{'='*50}")
    print(f"✅ 已儲存 {len(labels)} 筆（本次新增 {new}）\n")
    print(show_progress(labels, CHAIN_DB_VALS, TARGET_PER_CAT))
    if all(counts.get(db, 0) >= TARGET_PER_CAT for db in CHAIN_DB_VALS):
        print("\n✅ 鍊子粗細訓練充足！")
        print("下一步：python3 scripts/reclassify_trained.py --chain")
    else:
        missing = [CHAIN_DISPLAY[CHAIN_DB_VALS.index(db)] for db in CHAIN_DB_VALS
                   if counts.get(db, 0) < TARGET_PER_CAT]
        print(f"\n⚠  尚不足：{', '.join(missing)}")
        print("繼續標記：python3 scripts/teach.py --chain")


# ── 入口 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    if '--style' in sys.argv:
        run_style()
    elif '--chain' in sys.argv:
        run_chain_width()
    else:
        run_category()
