"""cleanup_filenames.py - 把檔名裡的「未定」替換成 DB 實際欄位值，或直接移除

執行：
  python3 scripts/cleanup_filenames.py          ← 預覽（不改名）
  python3 scripts/cleanup_filenames.py --rename ← 真正改名
"""
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

def main():
    do_rename = '--rename' in sys.argv

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, full_path, filename, category, style, color, stone_shape "
        "FROM photos WHERE full_path IS NOT NULL"
    ).fetchall()

    to_fix = [(r, Path(r['full_path'])) for r in rows if '未定' in (r['full_path'] or '')]
    print(f"找到 {len(to_fix)} 個包含「未定」的檔案路徑")

    if not to_fix:
        print("沒有需要修正的檔名。")
        conn.close()
        return

    renamed = errors = skipped = 0
    for row, old_path in to_fix:
        # 組合新檔名：把每個「未定」換成對應欄位值（若有），或直接移除
        replacements = {
            'color':       row['color']       or '',
            'stone_shape': row['stone_shape'] or '',
        }
        # 新檔名：把 _未定 替換（連底線一起）
        new_name = old_path.name
        new_name = re.sub(r'_?未定_?', '_', new_name)  # 移除 未定 段落
        new_name = re.sub(r'_+', '_', new_name)          # 合併多個底線
        new_name = new_name.strip('_')                    # 去掉首尾底線

        if new_name == old_path.name:
            skipped += 1
            continue

        new_path = old_path.parent / new_name
        print(f"  {old_path.name}")
        print(f"→ {new_name}")

        if not do_rename:
            continue

        if not old_path.exists():
            print(f"  ⚠ 檔案不存在，跳過")
            skipped += 1
            continue

        try:
            # 避免覆蓋已有的檔案
            if new_path.exists() and new_path != old_path:
                base, ext = new_path.stem, new_path.suffix
                n = 1
                while new_path.exists():
                    new_path = old_path.parent / f"{base}_{n}{ext}"
                    n += 1

            old_path.rename(new_path)
            conn.execute(
                "UPDATE photos SET full_path=?, filename=? WHERE id=?",
                (str(new_path), new_path.name, row['id'])
            )
            renamed += 1
        except Exception as e:
            print(f"  ❌ {e}")
            errors += 1

    if do_rename:
        conn.commit()
        print(f"\n✅ 完成！改名 {renamed} 個，跳過 {skipped} 個，錯誤 {errors} 個")
    else:
        print(f"\n（預覽模式）加上 --rename 才會真正改名")

    conn.close()

if __name__ == "__main__":
    main()
