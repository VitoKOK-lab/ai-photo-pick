"""conftest.py - 共用測試 fixtures"""
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _init_test_db(db_path: Path):
    from scripts._schema import SCHEMA
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def _insert_photo(db_path: Path, **kwargs) -> int:
    """測試用：快速插入一張照片，回傳 id"""
    defaults = dict(
        filename="test_001.jpg",
        original_filename="test_001.jpg",
        original_path="/tmp/test_001.jpg",
        full_path="/tmp/full/test_001.jpg",
        thumb_path="/tmp/thumb/test_001.jpg",
        micro_path="/tmp/micro/test_001.jpg",
        file_hash="abc123",
        file_size=100000,
        category="戒指",
        color="紅",
        material="18k黃金",
        gemstone="紅寶石",
        price_band="6-10萬",
    )
    defaults.update(kwargs)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join("?" * len(defaults))
    cur.execute(f"INSERT INTO photos ({cols}) VALUES ({placeholders})", list(defaults.values()))
    photo_id = cur.lastrowid
    conn.commit()
    conn.close()
    return photo_id


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """提供一個乾淨的測試 SQLite DB，並 patch 所有 api 模組的 SQLITE_PATH"""
    db_path = tmp_path / "test.sqlite"
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    _init_test_db(db_path)

    # patch config
    import config.settings as settings
    monkeypatch.setattr(settings, "SQLITE_PATH", db_path)
    monkeypatch.setattr(settings, "LOG_DIR", log_dir)
    monkeypatch.setattr(settings, "DB_DIR", tmp_path)

    # patch 各 api 模組的 SQLITE_PATH（已在 import 時複製到 module namespace）
    for mod_name in ["api.photos", "api.events", "api.favorites",
                     "api.locks", "api.stats", "api.quotes", "api.backup"]:
        import importlib
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "SQLITE_PATH"):
            monkeypatch.setattr(mod, "SQLITE_PATH", db_path)
        if hasattr(mod, "LOCAL_BACKUP_DIR"):
            monkeypatch.setattr(mod, "LOCAL_BACKUP_DIR", backup_dir)
        if hasattr(mod, "STATUS_FILE"):
            monkeypatch.setattr(mod, "STATUS_FILE", log_dir / "backup_status.json")

    return db_path


@pytest.fixture()
def client(tmp_db):
    from api.main import app
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def photo_id(tmp_db):
    """插入一筆測試照片，回傳 id"""
    return _insert_photo(tmp_db)


@pytest.fixture()
def photo_id2(tmp_db):
    """插入第二筆測試照片"""
    return _insert_photo(
        tmp_db,
        filename="test_002.jpg",
        original_filename="test_002.jpg",
        original_path="/tmp/test_002.jpg",
        full_path="/tmp/full/test_002.jpg",
        thumb_path="/tmp/thumb/test_002.jpg",
        micro_path="/tmp/micro/test_002.jpg",
        file_hash="def456",
        category="項鍊",
        color="藍",
        material="鉑金",
        gemstone="藍寶石",
        price_band="10-15萬",
    )
