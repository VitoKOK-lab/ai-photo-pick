"""backup.py - 備份腳本

備份三個目標：
  1. data/02_original/ → Google Drive（rclone sync）
  2. db/jewelry.sqlite  → db/backups/ 本地快照 + Google Drive
  3. db/chroma/         → db/backups/ 本地快照 + Google Drive

使用方式：
  python -m scripts.backup            # 完整備份
  python -m scripts.backup --db-only  # 只備份 DB（不跑 rclone，較快）
  python -m scripts.backup --dry-run  # 印出指令但不實際執行
"""
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    BASE_DIR, ORIGINAL_DIR, DB_DIR, SQLITE_PATH, CHROMA_PATH, LOG_DIR
)

# ─── 設定（可改 .env 覆寫）─────────────────────────────────
import os
RCLONE_REMOTE   = os.environ.get("JEWELRY_RCLONE_REMOTE", "gdrive")
RCLONE_BASE     = os.environ.get("JEWELRY_RCLONE_BASE",   "jewelry-db")
KEEP_LOCAL_DAYS = int(os.environ.get("JEWELRY_BACKUP_KEEP_DAYS", "7"))

LOCAL_BACKUP_DIR = DB_DIR / "backups"
STATUS_FILE      = LOG_DIR / "backup_status.json"


# ─── 工具 ───────────────────────────────────────────────────
def run(cmd: list[str], dry_run: bool) -> bool:
    print(f"  $ {' '.join(cmd)}")
    if dry_run:
        return True
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [ERROR] {result.stderr.strip()}")
        return False
    return True


def rclone_available() -> bool:
    return shutil.which("rclone") is not None


def _write_status(data: dict):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


# ─── 本地 DB 快照 ────────────────────────────────────────────
def backup_db_local(dry_run: bool) -> Path | None:
    LOCAL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # SQLite 快照
    sqlite_dst = LOCAL_BACKUP_DIR / f"jewelry_{ts}.sqlite"
    print(f"[DB] SQLite 快照 → {sqlite_dst.name}")
    if not dry_run:
        if not SQLITE_PATH.exists():
            print("  [WARN] SQLite 檔案不存在，跳過")
        else:
            shutil.copy2(SQLITE_PATH, sqlite_dst)

    # 清理過期本地快照
    _prune_local(dry_run)
    return sqlite_dst


def _prune_local(dry_run: bool):
    """保留最近 KEEP_LOCAL_DAYS 天的快照"""
    cutoff = datetime.now().timestamp() - KEEP_LOCAL_DAYS * 86400
    for f in sorted(LOCAL_BACKUP_DIR.glob("jewelry_*.sqlite")):
        if f.stat().st_mtime < cutoff:
            print(f"  [PRUNE] 刪除過期快照：{f.name}")
            if not dry_run:
                f.unlink()


# ─── rclone 同步 ─────────────────────────────────────────────
def backup_photos_rclone(dry_run: bool) -> bool:
    if not rclone_available():
        print("[PHOTOS] rclone 未安裝，跳過（brew install rclone）")
        return False

    remote_path = f"{RCLONE_REMOTE}:{RCLONE_BASE}/originals"
    print(f"[PHOTOS] rclone sync → {remote_path}")
    ok = run([
        "rclone", "sync",
        str(ORIGINAL_DIR), remote_path,
        "--transfers", "8",
        "--progress",
        "--log-level", "ERROR",
    ], dry_run)
    return ok


def backup_db_rclone(sqlite_snapshot: Path, dry_run: bool) -> bool:
    if not rclone_available():
        print("[DB] rclone 未安裝，跳過")
        return False

    remote_path = f"{RCLONE_REMOTE}:{RCLONE_BASE}/db"
    print(f"[DB] rclone copy → {remote_path}")
    ok = run([
        "rclone", "copy",
        str(sqlite_snapshot), remote_path,
        "--log-level", "ERROR",
    ], dry_run)
    return ok


# ─── 主流程 ─────────────────────────────────────────────────
def main():
    db_only = "--db-only" in sys.argv
    dry_run = "--dry-run" in sys.argv

    started_at = datetime.now()
    print(f"=== Jewelry DB 備份 {started_at.strftime('%Y-%m-%d %H:%M:%S')} ===")
    if dry_run:
        print("    [DRY-RUN 模式]")

    results = {}

    # 1. 本地 DB 快照
    sqlite_snapshot = backup_db_local(dry_run)
    results["db_local"] = True

    # 2. 照片 rclone（除非 --db-only）
    if not db_only:
        results["photos_rclone"] = backup_photos_rclone(dry_run)
    else:
        print("[PHOTOS] --db-only，跳過照片備份")
        results["photos_rclone"] = None

    # 3. DB rclone
    results["db_rclone"] = backup_db_rclone(sqlite_snapshot, dry_run)

    # 4. 寫狀態檔（供 API 查詢）
    status = {
        "last_backup": started_at.isoformat(),
        "duration_sec": round((datetime.now() - started_at).total_seconds(), 1),
        "dry_run": dry_run,
        "results": results,
    }
    if not dry_run:
        _write_status(status)

    print(f"\n=== 完成（{status['duration_sec']}s）===")
    for k, v in results.items():
        icon = "✓" if v else ("—" if v is None else "✗")
        print(f"  {icon} {k}")


if __name__ == "__main__":
    main()
