"""staging.py - 預看 01_unsorted/ 待匯入照片，確認後才正式匯入"""
import io
import sys
import threading
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import UNSORTED_DIR

VALID_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
router = APIRouter(prefix="/api/staging", tags=["staging"])


def _list_files():
    return sorted([
        p for p in UNSORTED_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in VALID_EXT
    ])


@router.get("")
def list_staging():
    files = _list_files()
    return {
        "count": len(files),
        "files": [
            {
                "rel": str(p.relative_to(UNSORTED_DIR)),
                "name": p.name,
                "size": p.stat().st_size,
            }
            for p in files
        ],
    }


@router.get("/thumb/{rel_path:path}")
def staging_thumb(rel_path: str, size: int = 300):
    p = UNSORTED_DIR / rel_path
    if not p.exists() or not p.is_file() or p.suffix.lower() not in VALID_EXT:
        raise HTTPException(status_code=404)
    try:
        from PIL import Image
        img = Image.open(p).convert("RGB")
        img.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=78)
        return Response(content=buf.getvalue(), media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{rel_path:path}")
def delete_staging(rel_path: str):
    p = UNSORTED_DIR / rel_path
    if not p.exists():
        raise HTTPException(status_code=404)
    p.unlink(missing_ok=True)
    # 刪空資料夾
    parent = p.parent
    if parent != UNSORTED_DIR:
        try:
            parent.rmdir()
        except OSError:
            pass
    return {"deleted": rel_path}


# ── 匯入狀態（全域，單次只跑一個）─────────────────────────
_status: dict = {"running": False, "done": False, "step": "", "ok": 0, "err": 0, "log": []}
_lock = threading.Lock()


@router.get("/ingest-status")
def get_ingest_status():
    return dict(_status)


@router.post("/ingest")
def start_ingest():
    with _lock:
        if _status["running"]:
            return {"message": "已在執行中", "status": dict(_status)}
        pending = len(_list_files())
        if pending == 0:
            return {"message": "沒有待匯入照片"}
        _status.update({"running": True, "done": False, "step": "準備中…", "ok": 0, "err": 0, "log": []})

    t = threading.Thread(target=_run_ingest, daemon=True)
    t.start()
    return {"message": f"開始匯入 {pending} 張", "status": dict(_status)}


def _log(msg: str):
    _status["log"].append(msg)
    if len(_status["log"]) > 200:
        _status["log"] = _status["log"][-200:]


def _run_ingest():
    try:
        from scripts.full_ingest import (
            step0_dedup, step1_batch, step2_remove_empty_dirs,
            step3_reclassify, step4_photo_type,
        )

        _status["step"] = "去重複檢查…"
        step0_dedup()

        _status["step"] = "批次匯入 + CLIP 分類…"
        step1_batch()

        _status["step"] = "清除空資料夾…"
        step2_remove_empty_dirs()

        _status["step"] = "補齊缺漏標籤…"
        step3_reclassify()

        _status["step"] = "偵測照片類型…"
        step4_photo_type()

        _status["step"] = "完成"
        _status["done"] = True
    except Exception as e:
        _status["step"] = f"錯誤：{e}"
        _log(f"ERROR: {e}")
    finally:
        _status["running"] = False
