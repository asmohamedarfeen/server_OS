from datetime import datetime, timedelta, timezone
import jwt
from fastapi import HTTPException, Request, WebSocket
from pwdlib import PasswordHash
from .config import JWT_SECRET, TOKEN_TTL_HOURS
from .db import connection

password_hash = PasswordHash.recommended()
ALGORITHM = "HS256"

def configured():
    with connection() as db:
        return db.execute("SELECT value FROM settings WHERE key='admin_hash'").fetchone() is not None

def setup_admin(username: str, password: str):
    with connection() as db:
        if db.execute("SELECT 1 FROM settings WHERE key='admin_hash'").fetchone():
            raise HTTPException(409, "Administrator is already configured")
        db.execute("INSERT INTO settings(key,value) VALUES('admin_username',?)", (username,))
        db.execute("INSERT INTO settings(key,value) VALUES('admin_hash',?)", (password_hash.hash(password),))

def check_login(username: str, password: str):
    with connection() as db:
        row = db.execute("SELECT value FROM settings WHERE key='admin_username'").fetchone()
        hashed = db.execute("SELECT value FROM settings WHERE key='admin_hash'").fetchone()
    return bool(row and hashed and row['value'] == username and password_hash.verify(password, hashed['value']))

def token_for(username: str):
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET must be configured")
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": username, "iat": now, "exp": now + timedelta(hours=TOKEN_TTL_HOURS)}, JWT_SECRET, algorithm=ALGORITHM)

def decode_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        if not payload.get("sub"):
            raise ValueError()
        return payload
    except Exception as exc:
        raise HTTPException(401, "Authentication required") from exc

def get_token(request: Request):
    token = request.cookies.get("arfeen_session")
    if not token:
        raise HTTPException(401, "Authentication required")
    return decode_token(token)

def get_current_user(request: Request):
    return get_token(request)["sub"]

def websocket_user(websocket: WebSocket):
    token = websocket.cookies.get("arfeen_session")
    if not token:
        raise ValueError("Authentication required")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload["sub"]
    except Exception as exc:
        raise ValueError("Authentication required") from exc
