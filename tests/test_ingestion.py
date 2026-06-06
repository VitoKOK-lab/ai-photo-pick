"""test_ingestion.py - Ingestion pipeline 測試（不需 CLIP，mock 分類）"""
import shutil
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image


# ─── Fixtures ────────────────────────────────────────────────

@pytest.fixture()
def sample_image(tmp_path) -> Path:
    """建一張 200×150 的測試小圖"""
    img_path = tmp_path / "sample.jpg"
    img = Image.new("RGB", (200, 150), color=(180, 100, 50))
    img.save(img_path, "JPEG")
    return img_path


@pytest.fixture()
def fake_classification() -> dict:
    return {
        "color":         {"label": "紅", "confidence": 0.82},
        "category":      {"label": "戒指", "confidence": 0.91},
        "material":      {"label": "18k黃金", "confidence": 0.75},
        "diamond_status":{"label": "副鑽鑲嵌", "confidence": 0.60},
        "gemstone":      {"label": "紅寶石", "confidence": 0.88},
        "style":         {"label": "經典", "confidence": 0.70},
    }


@pytest.fixture()
def fake_embedding() -> list:
    return [0.1] * 512


# ─── process_image ───────────────────────────────────────────

class TestProcessImage:
    def test_basic(self, tmp_path, sample_image, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "ORIGINAL_DIR", tmp_path / "orig")
        monkeypatch.setattr(settings, "FULL_DIR",     tmp_path / "full")
        monkeypatch.setattr(settings, "THUMB_DIR",    tmp_path / "thumb")
        monkeypatch.setattr(settings, "MICRO_DIR",    tmp_path / "micro")

        import importlib
        import scripts.process_image as pm
        importlib.reload(pm)

        meta = pm.process_one(sample_image)

        assert Path(meta["full_path"]).exists()
        assert Path(meta["thumb_path"]).exists()
        assert Path(meta["micro_path"]).exists()
        assert Path(meta["original_path"]).exists()
        assert meta["width"] == 200
        assert meta["height"] == 150
        assert len(meta["file_hash"]) == 64

    def test_square_crop(self, tmp_path, monkeypatch):
        """非正方形圖應被裁成正方形"""
        from config import settings
        for attr, name in [("ORIGINAL_DIR","orig"),("FULL_DIR","full"),
                           ("THUMB_DIR","thumb"),("MICRO_DIR","micro")]:
            monkeypatch.setattr(settings, attr, tmp_path / name)

        import importlib
        import scripts.process_image as pm
        importlib.reload(pm)

        img_path = tmp_path / "wide.jpg"
        Image.new("RGB", (400, 200), color=(0, 128, 0)).save(img_path, "JPEG")

        meta = pm.process_one(img_path)
        full = Image.open(meta["full_path"])
        w, h = full.size
        assert w == h, "結果應為正方形"

    def test_precomputed_hash(self, tmp_path, sample_image, monkeypatch):
        """傳入 precomputed_hash 應直接使用，不重算"""
        from config import settings
        for attr, name in [("ORIGINAL_DIR","orig"),("FULL_DIR","full"),
                           ("THUMB_DIR","thumb"),("MICRO_DIR","micro")]:
            monkeypatch.setattr(settings, attr, tmp_path / name)

        import importlib
        import scripts.process_image as pm
        importlib.reload(pm)

        h = pm.file_hash(sample_image)

        call_count = {"n": 0}
        original_hash = pm.file_hash
        def counting_hash(p):
            call_count["n"] += 1
            return original_hash(p)

        with patch.object(pm, "file_hash", side_effect=counting_hash):
            meta = pm.process_one(sample_image, precomputed_hash=h)

        # precomputed_hash 傳入後，process_one 內部不應再呼叫 file_hash
        assert call_count["n"] == 0
        assert meta["file_hash"] == h

    def test_dirs_created_automatically(self, tmp_path, sample_image, monkeypatch):
        """目錄不存在時應自動建立"""
        from config import settings
        for attr, name in [("ORIGINAL_DIR","orig"),("FULL_DIR","full"),
                           ("THUMB_DIR","thumb"),("MICRO_DIR","micro")]:
            monkeypatch.setattr(settings, attr, tmp_path / "new" / name)

        import importlib
        import scripts.process_image as pm
        importlib.reload(pm)

        meta = pm.process_one(sample_image)
        assert Path(meta["full_path"]).exists()


# ─── file_hash ───────────────────────────────────────────────

class TestFileHash:
    def test_consistent(self, sample_image):
        from scripts.process_image import file_hash
        assert file_hash(sample_image) == file_hash(sample_image)

    def test_different_files(self, tmp_path):
        from scripts.process_image import file_hash
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        Image.new("RGB", (10, 10), (255, 0, 0)).save(a, "JPEG")
        Image.new("RGB", (10, 10), (0, 255, 0)).save(b, "JPEG")
        assert file_hash(a) != file_hash(b)


# ─── db_writer ───────────────────────────────────────────────

class TestDbWriter:
    def _make_meta(self, tmp_path) -> dict:
        return {
            "filename": "20260606_abcd1234.jpg",
            "original_filename": "orig.jpg",
            "original_path": str(tmp_path / "orig.jpg"),
            "full_path":  str(tmp_path / "full.jpg"),
            "thumb_path": str(tmp_path / "thumb.jpg"),
            "micro_path": str(tmp_path / "micro.jpg"),
            "file_hash":  "a" * 64,
            "file_size":  12345,
            "width":  400,
            "height": 400,
        }

    def test_insert_and_hash_exists(self, tmp_db, fake_classification, fake_embedding, monkeypatch):
        import scripts.db_writer as dw
        monkeypatch.setattr(dw, "SQLITE_PATH", tmp_db)

        meta = self._make_meta(Path(tmp_db).parent)

        # mock chromadb
        mock_col = MagicMock()
        monkeypatch.setattr(dw, "_collection", mock_col)

        photo_id = dw.insert_photo(meta, fake_classification, fake_embedding)
        assert photo_id > 0
        assert dw.hash_exists("a" * 64)
        assert not dw.hash_exists("b" * 64)

    def test_chromadb_fail_rolls_back_sqlite(self, tmp_db, fake_classification, fake_embedding, monkeypatch):
        """chromadb 失敗時應刪除 SQLite 記錄（一致性保護）"""
        import scripts.db_writer as dw
        monkeypatch.setattr(dw, "SQLITE_PATH", tmp_db)

        meta = self._make_meta(Path(tmp_db).parent)

        mock_col = MagicMock()
        mock_col.add.side_effect = Exception("chroma down")
        monkeypatch.setattr(dw, "_collection", mock_col)

        with pytest.raises(RuntimeError, match="chromadb write failed"):
            dw.insert_photo(meta, fake_classification, fake_embedding)

        # SQLite 應已回滾，hash 不存在
        assert not dw.hash_exists("a" * 64)

        # 且 photos 表應為空
        conn = sqlite3.connect(tmp_db)
        count = conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
        conn.close()
        assert count == 0


# ─── ingest_one ──────────────────────────────────────────────

class TestIngestOne:
    def _setup(self, tmp_path, monkeypatch):
        from config import settings
        for attr, name in [("ORIGINAL_DIR","orig"),("FULL_DIR","full"),
                           ("THUMB_DIR","thumb"),("MICRO_DIR","micro"),
                           ("UNSORTED_DIR","unsorted")]:
            monkeypatch.setattr(settings, attr, tmp_path / name)
        monkeypatch.setattr(settings, "SQLITE_PATH", tmp_path / "test.sqlite")
        monkeypatch.setattr(settings, "CHROMA_PATH", tmp_path / "chroma")

        import importlib, scripts.db_writer as dw
        importlib.reload(dw)
        monkeypatch.setattr(dw, "SQLITE_PATH", tmp_path / "test.sqlite")

        # 初始化 DB
        from scripts._schema import SCHEMA
        conn = sqlite3.connect(tmp_path / "test.sqlite")
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()

    def test_ok(self, tmp_path, sample_image, fake_classification, fake_embedding, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        import scripts.ingest as ing  # 先 import，patch 才能附著在正確 namespace

        with patch.object(ing, "classify_one", return_value=(fake_classification, fake_embedding)), \
             patch("scripts.db_writer.get_chroma_collection", return_value=MagicMock()):
            result = ing.ingest_one(sample_image)

        assert result["status"] == "ok", result.get("error")
        assert "photo_id" in result

    def test_skip_duplicate(self, tmp_path, sample_image, fake_classification, fake_embedding, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        import scripts.ingest as ing

        with patch.object(ing, "classify_one", return_value=(fake_classification, fake_embedding)), \
             patch("scripts.db_writer.get_chroma_collection", return_value=MagicMock()):
            r1 = ing.ingest_one(sample_image)
            assert r1["status"] == "ok", r1.get("error")

            # 第二次同一張 → 重複跳過
            r2 = ing.ingest_one(sample_image)
            assert r2["status"] == "skip_duplicate"

    def test_hash_computed_once(self, tmp_path, sample_image, fake_classification, fake_embedding, monkeypatch):
        """ingest_one 只算一次 hash（不在 process_one 重算）"""
        self._setup(tmp_path, monkeypatch)
        import scripts.ingest as ing
        import scripts.process_image as pm

        hash_calls = {"n": 0}
        original_hash = pm.file_hash
        def spy(p):
            hash_calls["n"] += 1
            return original_hash(p)

        with patch.object(ing, "classify_one", return_value=(fake_classification, fake_embedding)), \
             patch("scripts.db_writer.get_chroma_collection", return_value=MagicMock()), \
             patch.object(ing, "file_hash", side_effect=spy), \
             patch.object(pm,  "file_hash", side_effect=spy):
            ing.ingest_one(sample_image)

        # ingest_one 算 1 次，process_one 因有 precomputed_hash 不再算
        assert hash_calls["n"] == 1


# ─── watch_folder 等待穩定 ──────────────────────────────────

class TestWaitForStable:
    def test_stable_file(self, tmp_path):
        from scripts.watch_folder import wait_for_stable
        f = tmp_path / "ok.jpg"
        f.write_bytes(b"x" * 1000)
        assert wait_for_stable(f, timeout=5) is True

    def test_missing_file(self, tmp_path):
        from scripts.watch_folder import wait_for_stable
        assert wait_for_stable(tmp_path / "ghost.jpg", timeout=2) is False
