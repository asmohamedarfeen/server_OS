import sqlite3
from contextlib import contextmanager
from .config import APP_DB

def init_db():
    with sqlite3.connect(APP_DB) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL, framework TEXT NOT NULL, port INTEGER NOT NULL, host_port INTEGER, status TEXT NOT NULL, container_id TEXT, image TEXT, domain TEXT, created_at TEXT NOT NULL, env_json TEXT NOT NULL DEFAULT '{}', source_type TEXT NOT NULL DEFAULT 'github', source_ref TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS deployments (id TEXT PRIMARY KEY, app_id TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL, image TEXT);
        CREATE TABLE IF NOT EXISTS deployment_attempts (id TEXT PRIMARY KEY, app_id TEXT, source TEXT NOT NULL, source_ref TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, stage TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL, image TEXT);
        CREATE TABLE IF NOT EXISTS databases (id TEXT PRIMARY KEY, name TEXT NOT NULL, engine TEXT NOT NULL, container_id TEXT, username TEXT, password TEXT, port INTEGER, created_at TEXT NOT NULL);
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(applications)").fetchall()}
        if "host_port" not in columns:
            conn.execute("ALTER TABLE applications ADD COLUMN host_port INTEGER")
        if "source_type" not in columns:
            conn.execute("ALTER TABLE applications ADD COLUMN source_type TEXT NOT NULL DEFAULT 'github'")
        if "source_ref" not in columns:
            conn.execute("ALTER TABLE applications ADD COLUMN source_ref TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE applications SET source_type='zip',source_ref='' WHERE source='ZIP upload' AND source_type='github'")

@contextmanager
def connection():
    conn = sqlite3.connect(APP_DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
