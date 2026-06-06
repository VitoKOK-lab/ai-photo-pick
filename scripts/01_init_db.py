"""01_init_db.py - 初始化 SQLite + chromadb"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH, CHROMA_PATH
from scripts._schema import SCHEMA

import chromadb


def init_sqlite():
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"[OK] SQLite initialized at {SQLITE_PATH}")


def init_chromadb():
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_or_create_collection(
        name="jewelry_embeddings",
        metadata={"hnsw:space": "cosine"}
    )
    print(f"[OK] chromadb collection ready: {collection.name}")


if __name__ == "__main__":
    init_sqlite()
    init_chromadb()
    print("\n[DONE] Database initialized.")
