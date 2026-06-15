"""02_add_users.py - Migration: add users table and default admin user"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
"""


def run():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    # Check if table already exists
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()

    if not existing:
        print("[migration] 建立 users 資料表...")
        conn.executescript(USERS_TABLE_SQL)
        conn.commit()
        print("[migration] users 資料表已建立")
    else:
        print("[migration] users 資料表已存在，略過建立")

    # Insert default admin if not present
    admin_row = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if not admin_row:
        # Hash password using passlib
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        hashed = pwd_context.hash("admin1234")
        conn.execute(
            "INSERT INTO users (name, username, password_hash, role) VALUES (?,?,?,?)",
            ("管理員", "admin", hashed, "admin"),
        )
        conn.commit()
        print("[migration] 預設管理員帳號已建立 (username: admin, password: admin1234)")
    else:
        print("[migration] 管理員帳號已存在，略過建立")

    conn.close()
    print("[migration] 完成")


if __name__ == "__main__":
    run()
