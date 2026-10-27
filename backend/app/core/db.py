import sqlite3
from contextlib import contextmanager
from .config import APP_DB

def init_db():
    with sqlite3.connect(APP_DB) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL, framework TEXT NOT NULL, port INTEGER NOT NULL, status TEXT NOT NULL, container_id TEXT, image TEXT, domain TEXT, created_at TEXT NOT NULL, env_json TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS deployments (id TEXT PRIMARY KEY, app_id TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL, image TEXT);
        CREATE TABLE IF NOT EXISTS databases (id TEXT PRIMARY KEY, name TEXT NOT NULL, engine TEXT NOT NULL, container_id TEXT, username TEXT, password TEXT, port INTEGER, created_at TEXT NOT NULL);
        """)

@contextmanager
def connection():
    conn = sqlite3.connect(APP_DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
