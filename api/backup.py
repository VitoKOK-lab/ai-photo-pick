"""backup.py - 備份狀態查詢 + 手動觸發"""
import json
import subprocess
import sys
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from api.auth import require_admin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import DB_DIR, LOG_DIR

router = APIRouter(prefix="/api/backup", tags=["backup"])

STATUS_FILE      = LOG_DIR / "backup_status.json"
LOCAL_BACKUP_DIR = DB_DIR / "backups"

_backup_running = False


@router.get("/status")
def backup_status():
    """查詢上次備份時間與結果"""
    snapshots = sorted(LOCAL_BACKUP_DIR.glob("jewelry_*.sqlite"), reverse=True) \
                if LOCAL_BACKUP_DIR.exists() else []

    last_status = None
    if STATUS_FILE.exists():
        try:
            last_status = json.loads(STATUS_FILE.read_text())
        except Exception:
            pass

    return {
        "running": _backup_running,
        "last_backup": last_status.get("last_backup") if last_status else None,
        "last_results": last_status.get("results") if last_status else None,
        "local_snapshots": [
            {
                "filename": s.name,
                "size_mb": round(s.stat().st_size / 1024 / 1024, 1),
            }
            for s in snapshots[:5]
        ],
    }


def _run_backup(db_only: bool):
    global _backup_running
    _backup_running = True
    try:
        cmd = [sys.executable, "-m", "scripts.backup"]
        if db_only:
            cmd.append("--db-only")
        subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    finally:
        _backup_running = False


@router.post("/trigger")
def trigger_backup(
    background_tasks: BackgroundTasks,
    db_only: bool = False,
    _user=Depends(require_admin),
):
    """手動觸發備份（背景執行）"""
    global _backup_running
    if _backup_running:
        raise HTTPException(status_code=409, detail="備份正在執行中")
    background_tasks.add_task(_run_backup, db_only)
    return {"message": "備份已在背景啟動", "db_only": db_only}
