"""db_writer.py - 把處理 + 分類結果寫入 SQLite + chromadb"""
import sqlite3
import sys
from pathlib import Path
import chromadb

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
            diamond_status, diamond_confidence,
            gemstone, gemstone_confidence,
            style, style_confidence,
            file_hash, file_size, width, height
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        metadata["filename"], metadata["original_filename"], metadata["original_path"],
        metadata["full_path"], metadata["thumb_path"], metadata["micro_path"],
        classification["color"]["label"],        classification["color"]["confidence"],
        classification["category"]["label"],     classification["category"]["confidence"],
        classification["material"]["label"],     classification["material"]["confidence"],
        classification["diamond_status"]["label"], classification["diamond_status"]["confidence"],
        classification["gemstone"]["label"],     classification["gemstone"]["confidence"],
        classification.get("style", {}).get("label"),
        classification.get("style", {}).get("confidence"),
        metadata["file_hash"], metadata["file_size"],
        metadata["width"], metadata["height"],
    ))

    photo_id = cur.lastrowid
    conn.commit()

    # chromadb 寫入；失敗時刪除剛才的 SQLite 記錄保持一致
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
    except Exception as chroma_err:
        # rollback：刪除剛插入的 SQLite 行
        try:
            conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
            conn.commit()
        except Exception:
            pass
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
