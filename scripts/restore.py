"""restore.py - 從備份還原 DB

使用方式：
  python -m scripts.restore                     # 列出本地可用快照
  python -m scripts.restore --latest            # 還原最新快照
  python -m scripts.restore jewelry_20240615.sqlite
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import DB_DIR, SQLITE_PATH

LOCAL_BACKUP_DIR = DB_DIR / "backups"


def list_snapshots() -> list[Path]:
    if not LOCAL_BACKUP_DIR.exists():
        return []
    return sorted(LOCAL_BACKUP_DIR.glob("jewelry_*.sqlite"), reverse=True)


def restore(snapshot: Path):
    if not snapshot.exists():
        print(f"[ERROR] 快照不存在：{snapshot}")
        sys.exit(1)

    # 先備份現有 DB
    if SQLITE_PATH.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        pre_backup = LOCAL_BACKUP_DIR / f"jewelry_pre_restore_{ts}.sqlite"
        LOCAL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SQLITE_PATH, pre_backup)
        print(f"[OK] 現有 DB 已備份至 {pre_backup.name}")

    shutil.copy2(snapshot, SQLITE_PATH)
    print(f"[OK] 已還原：{snapshot.name} → {SQLITE_PATH}")


def main():
    snapshots = list_snapshots()

    if "--latest" in sys.argv:
        if not snapshots:
            print("[ERROR] 找不到任何本地快照")
            sys.exit(1)
        restore(snapshots[0])
        return

    # 指定檔名
    targets = [a for a in sys.argv[1:] if not a.startswith("--")]
    if targets:
        name = targets[0]
        path = LOCAL_BACKUP_DIR / name if not Path(name).is_absolute() else Path(name)
        restore(path)
        return

    # 列出快照
    if not snapshots:
        print("目前沒有本地快照。")
        print(f"快照目錄：{LOCAL_BACKUP_DIR}")
        return

    print(f"本地快照（{LOCAL_BACKUP_DIR}）：\n")
    for i, s in enumerate(snapshots):
        size_mb = s.stat().st_size / 1024 / 1024
        mtime = datetime.fromtimestamp(s.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  [{i+1}] {s.name}  {size_mb:.1f} MB  {mtime}")

    print("\n還原指令：")
    print(f"  python -m scripts.restore {snapshots[0].name}")
    print("  python -m scripts.restore --latest")


if __name__ == "__main__":
    main()
