import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", "/workspace"))
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/data/files"))
JWT_SECRET = os.getenv("JWT_SECRET", "")
TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "12"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
APP_DB = DATA_DIR / "arfeen.db"
for path in (DATA_DIR, WORKSPACE_DIR, STORAGE_DIR):
    path.mkdir(parents=True, exist_ok=True)
