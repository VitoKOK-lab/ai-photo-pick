"""auth.py - JWT authentication"""
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import APIRouter, HTTPException, Depends, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import sqlite3
import sys
from pathlib import Path

# ── 登入速率限制（防暴力破解）──────────────────────────
_attempts: dict = defaultdict(int)   # ip -> 失敗累計次數
_MAX_FAILS = 3                        # 超過即永久封鎖

def _get_db():
    import sqlite3 as _sq
    from config.settings import SQLITE_PATH as _SP
    c = _sq.connect(_SP)
    c.row_factory = _sq.Row
    return c

def _is_blocked(ip: str) -> bool:
    try:
        conn = _get_db()
        row = conn.execute("SELECT 1 FROM blocked_ips WHERE ip=?", (ip,)).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False

def _block_ip(ip: str, reason: str):
    try:
        conn = _get_db()
        conn.execute("INSERT OR IGNORE INTO blocked_ips(ip, reason) VALUES(?,?)", (ip, reason))
        conn.commit()
        conn.close()
    except Exception:
        pass

def _check_rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    if _is_blocked(ip):
        raise HTTPException(403, "此 IP 已被封鎖，請聯繫管理員")

def _record_fail(request: Request):
    ip = request.client.host if request.client else "unknown"
    _attempts[ip] += 1
    if _attempts[ip] >= _MAX_FAILS:
        _block_ip(ip, f"連續登入失敗 {_attempts[ip]} 次後自動封鎖")

def _record_success(request: Request):
    ip = request.client.host if request.client else "unknown"
    _attempts[ip] = 0

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SQLITE_PATH

_raw_secret = os.environ.get("JWT_SECRET", "")
if not _raw_secret:
    import warnings
    warnings.warn("JWT_SECRET 未設定，使用預設值。請在 .env 設定 JWT_SECRET=<隨機長字串>", stacklevel=2)
SECRET_KEY = _raw_secret or "jewelry-app-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/api/auth", tags=["auth"])

def get_db():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _ensure_tables():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            username      TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'editor' CHECK(role IN ('admin','editor','viewer')),
            is_active     INTEGER NOT NULL DEFAULT 1,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS blocked_ips (
            ip         TEXT PRIMARY KEY,
            reason     TEXT,
            blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

_ensure_tables()

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def hash_password(password):
    return pwd_context.hash(password)

def create_token(user_id: int, role: str) -> str:
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "role": role, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency: returns current user dict or None if not authenticated"""
    if not credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub", "")
        role = payload.get("role")
        # PIN-login synthetic tokens skip DB lookup
        if sub in ("pin_admin", "pin_staff"):
            return {"id": sub, "role": role, "name": "PIN User", "username": sub}
        user_id = int(sub)
        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE id=? AND is_active=1", (user_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return dict(row)
    except (JWTError, Exception):
        return None

def require_auth(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="請先登入")
    return user

def require_editor(user=Depends(require_auth)):
    if user["role"] not in ("admin", "editor"):
        raise HTTPException(status_code=403, detail="需要編輯者權限")
    return user

def require_admin(user=Depends(require_auth)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理員權限")
    return user

@router.post("/login")
def login(body: dict, request: Request):
    _check_rate_limit(request)
    username = body.get("username", "").strip()
    password = body.get("password", "")
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE username=? AND is_active=1", (username,)).fetchone()
    conn.close()
    if not row or not verify_password(password, row["password_hash"]):
        _record_fail(request)
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    _record_success(request)
    token = create_token(row["id"], row["role"])
    return {"token": token, "user": {"id": row["id"], "name": row["name"], "username": row["username"], "role": row["role"]}}

@router.get("/me")
def me(user=Depends(get_current_user)):
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "user": {"id": user["id"], "name": user["name"], "username": user["username"], "role": user["role"]}}

# ── User management (admin only) ────────────────────────
@router.get("/users")
def list_users(user=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT id, name, username, role, is_active, created_at FROM users ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/users")
def create_user(body: dict, user=Depends(require_admin)):
    name = body.get("name", "").strip()
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    role = body.get("role", "viewer")
    if not name or not username or not password:
        raise HTTPException(status_code=400, detail="姓名、帳號、密碼必填")
    if role not in ("admin", "editor", "viewer"):
        raise HTTPException(status_code=400, detail="角色無效")
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (name, username, password_hash, role) VALUES (?,?,?,?)",
                     (name, username, hash_password(password), role))
        conn.commit()
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return {"id": new_id, "name": name, "username": username, "role": role}
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="帳號已存在（用戶名重複）")
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/users/{user_id}")
def update_user(user_id: int, body: dict, user=Depends(require_admin)):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="找不到使用者")
    updates = {}
    if "name" in body:     updates["name"] = body["name"]
    if "role" in body and body["role"] in ("admin","editor","viewer"): updates["role"] = body["role"]
    if "is_active" in body: updates["is_active"] = int(body["is_active"])
    if "password" in body and body["password"]:
        updates["password_hash"] = hash_password(body["password"])
    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        conn.execute(f"UPDATE users SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     list(updates.values()) + [user_id])
        conn.commit()
    conn.close()
    return {"ok": True}

@router.delete("/users/{user_id}")
def delete_user(user_id: int, user=Depends(require_admin)):
    if user["id"] == user_id:
        raise HTTPException(status_code=400, detail="不能刪除自己")
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/pin-login")
def pin_login(body: dict, request: Request):
    """PIN 碼登入（前端用）：驗證成功回傳 JWT token"""
    _check_rate_limit(request)
    pin = str(body.get("pin", "")).strip()
    admin_pin = os.environ.get("ADMIN_PIN", "666")
    staff_pin = os.environ.get("STAFF_PIN", "")
    if pin == admin_pin:
        sub, role = "pin_admin", "admin"
    elif staff_pin and pin == staff_pin:
        sub, role = "pin_staff", "editor"
    else:
        _record_fail(request)
        raise HTTPException(status_code=401, detail="PIN 錯誤")
    _record_success(request)
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    token = jwt.encode({"sub": sub, "role": role, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)
    return {"token": token, "role": role}


# ── 管理員：封鎖 IP 管理 ────────────────────────────────
@router.get("/blocked-ips")
def list_blocked_ips(_user=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM blocked_ips ORDER BY blocked_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.delete("/blocked-ips/{ip}")
def unblock_ip(ip: str, _user=Depends(require_admin)):
    conn = get_db()
    conn.execute("DELETE FROM blocked_ips WHERE ip=?", (ip,))
    conn.commit()
    conn.close()
    _attempts.pop(ip, None)
    return {"ok": True, "unblocked": ip}
