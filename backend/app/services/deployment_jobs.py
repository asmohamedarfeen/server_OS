"""Durable, bounded deployment output with a serialized in-process build worker."""
import json
import re
import sqlite3
import uuid
import threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from datetime import datetime, timezone

from fastapi import HTTPException
from ..core.db import connection

MAX_LOG_BYTES = 8 * 1024 * 1024
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="deployment")
_current = ContextVar("deployment_job", default=None)


_resource_locks={}
_resource_locks_guard=threading.Lock()


@contextmanager
def resource_operation(resource_key):
    # Share a small in-process lock between queue insertion and app mutations.
    # The durable active-job row protects the full worker lifetime thereafter.
    with _resource_locks_guard:
        lock=_resource_locks.setdefault(resource_key,threading.Lock())
    if not lock.acquire(blocking=False):
        raise HTTPException(409,'This application already has an operation in progress')
    try:
        yield
    finally:
        lock.release()


class JobCancelled(Exception):
    pass


def initialize():
    with connection() as db:
        columns={r[1] for r in db.execute('PRAGMA table_info(deployment_jobs)')}
        if 'cancel_requested' not in columns:
            db.execute('ALTER TABLE deployment_jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0')
        db.execute('CREATE TABLE IF NOT EXISTS deployment_job_stages(job_id TEXT NOT NULL,name TEXT NOT NULL,status TEXT NOT NULL,started_at TEXT NOT NULL,finished_at TEXT,duration_seconds REAL,exit_code INTEGER,PRIMARY KEY(job_id,name))')


def check_cancelled():
    if not output(): return
    with connection() as db:
        row=db.execute('SELECT cancel_requested,stage FROM deployment_jobs WHERE id=?',(output().id,)).fetchone()
    if row and row['cancel_requested'] and row['stage'] not in ('deploy','verify','complete'):
        raise JobCancelled('Deployment cancelled before replacing the application')


def finish_stage(status='success'):
    if not output(): return
    stamp=now()
    with connection() as db:
        db.execute("UPDATE deployment_job_stages SET status=?,finished_at=?,duration_seconds=MAX(0,(julianday(?)-julianday(started_at))*86400) WHERE job_id=? AND finished_at IS NULL",(status,stamp,stamp,output().id))


def now():
    return datetime.now(timezone.utc).isoformat()


class JobOutput:
    def __init__(self, job_id, secrets=()):
        self.id = job_id
        self.stage = "queued"
        self.secrets = sorted({s for s in secrets if isinstance(s, str) and s}, key=len, reverse=True)

    def clean(self, message):
        text = str(message)
        for secret in self.secrets:
            text = text.replace(secret, "[redacted]")
        text = re.sub(r"(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+", "[redacted]", text)
        text = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[redacted]@", text)
        text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
        return "".join(c for c in text if c in "\n\t" or ord(c) >= 32)

    def write(self, message, level="info"):
        message = self.clean(message).strip()
        if not message:
            return
        message = message[:8192]
        size = len(message.encode("utf-8"))
        with connection() as db:
            row = db.execute("SELECT log_bytes FROM deployment_jobs WHERE id=?", (self.id,)).fetchone()
            if not row or row["log_bytes"] > MAX_LOG_BYTES:
                return
            if row["log_bytes"] + size > MAX_LOG_BYTES:
                message = "Log limit reached (8 MiB). Build continues; final status will still be recorded."
                size = MAX_LOG_BYTES + 1 - row["log_bytes"]
            db.execute("INSERT INTO deployment_job_logs(job_id,created_at,stage,level,message) VALUES(?,?,?,?,?)",
                       (self.id, now(), self.stage, level, message))
            db.execute("UPDATE deployment_jobs SET log_bytes=log_bytes+? WHERE id=?", (size, self.id))


def output():
    return _current.get()


def log(message, level="info"):
    if output():
        output().write(message, level)


def add_secrets(values):
    if output():
        output().secrets = sorted(set(output().secrets) | {v for v in values if isinstance(v, str) and v}, key=len, reverse=True)


def stage(name, message):
    if not output():
        return
    check_cancelled()
    stamp=now()
    # The cancellation flag and replacement boundary share one SQLite write lock.
    # A cancellation accepted before this transition can never enter deployment.
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT stage,cancel_requested FROM deployment_jobs WHERE id=?',(output().id,)).fetchone()
        if row and row['cancel_requested'] and row['stage'] not in ('deploy','verify','complete'):
            raise JobCancelled('Deployment cancelled before replacing the application')
        if output().stage != name:
            db.execute("UPDATE deployment_job_stages SET status='success',finished_at=?,duration_seconds=MAX(0,(julianday(?)-julianday(started_at))*86400) WHERE job_id=? AND finished_at IS NULL",(stamp,stamp,output().id))
        db.execute("UPDATE deployment_jobs SET stage=?,message=? WHERE id=?",(name,output().clean(message)[:2000],output().id))
        db.execute("INSERT OR IGNORE INTO deployment_job_stages(job_id,name,status,started_at) VALUES(?,?,'running',?)",(output().id,name,stamp))
    output().stage=name
    log(message)


def create_job(name, resource_key, source, ref="", app_id=None):
    with resource_operation(resource_key):
        return _create_job(name,resource_key,source,ref,app_id)


def _create_job(name, resource_key, source, ref="", app_id=None):
    initialize()
    job_id = str(uuid.uuid4())
    try:
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT count(*) FROM deployment_jobs WHERE status IN ('queued','running')").fetchone()[0] >= 20:
                raise HTTPException(429, "The build queue is full. Wait for an existing deployment to finish.")
            db.execute("INSERT INTO deployment_jobs(id,name,resource_key,source,ref,status,stage,message,created_at) VALUES(?,?,?,?,?,'queued','queued','Waiting for build worker',?)",
                       (job_id, name, resource_key, source, ref, now()))
    except sqlite3.IntegrityError as exc:
        with connection() as db:
            active = db.execute("SELECT id FROM deployment_jobs WHERE resource_key=? AND status IN ('queued','running')", (resource_key,)).fetchone()
        raise HTTPException(409, {"message": "This application already has a deployment in progress.", "job_id": active["id"] if active else None}) from exc
    if app_id:
        with connection() as db: db.execute("UPDATE deployment_jobs SET app_id=? WHERE id=?",(app_id,job_id))
    return get_job(job_id)


def run_job(job_id, work, secrets=(), cleanup=None):
    writer = JobOutput(job_id, secrets)
    token = _current.set(writer)
    try:
        check_cancelled()
        with connection() as db:
            db.execute("UPDATE deployment_jobs SET status='running',started_at=? WHERE id=?", (now(), job_id))
        log("Build worker started. Output is saved and can be reopened from Deployments.")
        result = work()
        stage("complete", "Deployment completed successfully")
        finish_stage()
        with connection() as db:
            db.execute("UPDATE deployment_jobs SET status='success',finished_at=?,app_id=?,result_json=? WHERE id=?",
                       (now(), result.get("id"), json.dumps(result), job_id))
    except JobCancelled as exc:
        finish_stage('cancelled')
        with connection() as db:
            db.execute("UPDATE deployment_jobs SET status='cancelled',message=?,finished_at=? WHERE id=?",(str(exc),now(),job_id))
        log(str(exc))
    except Exception as exc:
        finish_stage('failed')
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        detail = writer.clean(detail or "Deployment failed")[:2000]
        log(detail, "error")
        with connection() as db:
            db.execute("UPDATE deployment_jobs SET status='failed',message=?,finished_at=? WHERE id=?", (detail, now(), job_id))
    finally:
        try:
            from .pipelines import activity
            job=get_job(job_id)
            activity('application.deploy',job.get('app_id') or job_id,job['name'],job['status'],job_id)
        except Exception:
            pass
        _current.reset(token)
        if cleanup:
            cleanup()


def submit_job(job, work, secrets=(), cleanup=None):
    _executor.submit(run_job, job["id"], work, secrets, cleanup)


def get_job(job_id):
    with connection() as db:
        row = db.execute("SELECT * FROM deployment_jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Deployment job not found")
    item = dict(row)
    item["result"] = json.loads(item.pop("result_json") or "null")
    item.pop("resource_key", None)
    return item


def recover_interrupted_jobs():
    initialize()
    with connection() as db:
        rows = db.execute("SELECT id,stage FROM deployment_jobs WHERE status IN ('running','queued')").fetchall()
        message = "Deployment interrupted by a backend restart. Check application status before retrying."
        for row in rows:
            db.execute("UPDATE deployment_job_stages SET status='interrupted',finished_at=?,duration_seconds=MAX(0,(julianday(?)-julianday(started_at))*86400) WHERE job_id=? AND finished_at IS NULL",(now(),now(),row['id']))
            db.execute("UPDATE deployment_jobs SET status='interrupted',message=?,finished_at=? WHERE id=?", (message, now(), row["id"]))
            db.execute("INSERT INTO deployment_job_logs(job_id,created_at,stage,level,message) VALUES(?,?,?,?,?)", (row["id"], now(), row["stage"], "error", message))
