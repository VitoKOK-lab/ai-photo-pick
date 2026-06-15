"""db_writer.py - 把處理 + 分類結果寫入 SQLite + chromadb"""
import logging
import sqlite3
import sys
from pathlib import Path
import chromadb

log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, CHROMA_PATH

_chroma_client = None
_collection = None


def get_chroma_collection():
    global _chroma_client, _collection
    if _collection is None:
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _collection = _chroma_client.get_or_create_collection(
            name="jewelry_embeddings",
            metadata={"hnsw:space": "cosine"}
        )
    return _collection


def insert_photo(metadata: dict, classification: dict, embedding: list) -> int:
    """
    寫入 SQLite + chromadb，兩邊保持一致：
    - SQLite insert 成功但 chromadb 失敗 → rollback SQLite（刪除剛插入的行）
    - 回傳 SQLite photo_id
    """
    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO photos (
            filename, original_filename, original_path,
            full_path, thumb_path, micro_path,
            color, color_confidence,
            category, category_confidence,
            material, material_confidence,
            gemstone, gemstone_confidence,
            stone_shape, stone_shape_confidence,
            stone_size, stone_size_confidence,
            metal_color,
            style, style_confidence,
            setting_amount, craft_complexity,
            price_band,
            file_hash, file_size, width, height
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        metadata["filename"], metadata["original_filename"], metadata["original_path"],
        metadata["full_path"], metadata["thumb_path"], metadata["micro_path"],
        classification["color"]["label"],           classification["color"]["confidence"],
        classification["category"]["label"],        classification["category"]["confidence"],
        classification["material"]["label"],        classification["material"]["confidence"],
        classification["gemstone"]["label"],        classification["gemstone"]["confidence"],
        classification["stone_shape"]["label"],     classification["stone_shape"]["confidence"],
        classification["stone_size"]["label"],      classification["stone_size"]["confidence"],
        classification.get("metal_color", {}).get("label"),
        classification.get("style", {}).get("label"),
        classification.get("style", {}).get("confidence"),
        classification.get("setting_amount", {}).get("label"),
        classification.get("craft_complexity", {}).get("label"),
        classification.get("price_band", {}).get("label"),
        metadata["file_hash"], metadata["file_size"],
        metadata["width"], metadata["height"],
    ))

    photo_id = cur.lastrowid
    # 不在這裡 commit — 等 chromadb 寫入成功後才 commit，失敗直接 rollback

    try:
        collection = get_chroma_collection()
        collection.add(
            ids=[f"photo_{photo_id}"],
            embeddings=[embedding],
            metadatas=[{
                "photo_id": photo_id,
                "filename": metadata["filename"],
                "color": classification["color"]["label"],
                "category": classification["category"]["label"],
                "material": classification["material"]["label"],
                "gemstone": classification["gemstone"]["label"],
            }]
        )
        conn.commit()
    except Exception as chroma_err:
        try:
            conn.rollback()
        except Exception as rb_err:
            log.error("SQLite rollback failed after chromadb error: %s", rb_err)
        conn.close()
        raise RuntimeError(f"chromadb write failed (SQLite rolled back): {chroma_err}") from chroma_err

    conn.close()
    return photo_id


def hash_exists(file_hash: str) -> bool:
    """檢查 hash 是否已存在（防重複匯入）"""
    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM photos WHERE file_hash = ?", (file_hash,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists
