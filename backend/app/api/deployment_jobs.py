"""Short authenticated requests for background deployment jobs and saved output."""
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse

from ..core.auth import get_current_user
from ..core.config import WORKSPACE_DIR
from ..core.db import connection
from ..services import deployment_jobs as jobs
from ..services.github import GitHubError, github_token
from . import applications

router = APIRouter(prefix="/api/deployment-jobs", tags=["deployment jobs"], dependencies=[Depends(get_current_user)])


def environment_values(environment):
    if not isinstance(environment, dict) or len(environment) > 100 or not all(
        isinstance(k, str) and applications.re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", k)
        and isinstance(v, str) and len(v) <= 8192 for k, v in environment.items()
    ):
        raise HTTPException(422, "Environment must contain up to 100 valid KEY=VALUE entries")
    return list(environment.values())


def credential():
    try:
        return github_token()
    except GitHubError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("")
def list_jobs():
    with connection() as db:
        rows = db.execute("SELECT id,name,source,ref,status,stage,message,created_at,started_at,finished_at,app_id FROM deployment_jobs ORDER BY created_at DESC LIMIT 100").fetchall()
    return [dict(row) for row in rows]


@router.post("/github", status_code=202)
def queue_github(body: dict):
    secrets = environment_values(body.get("environment", {}))
    owner, repo = body.get("owner"), body.get("repo")
    if owner is not None or repo is not None:
        if not all(isinstance(v, str) and applications.re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", v) for v in (owner, repo)):
            raise HTTPException(422, "Choose a valid repository")
        source = f"https://github.com/{owner}/{repo}.git"
        token = credential()
        if not token:
            raise HTTPException(409, "Connect GitHub in Settings first")
        secrets.append(token)
    else:
        source = applications.canonical_github_url(body.get("url"))
        if not source:
            raise HTTPException(422, "Enter a plain HTTPS GitHub repository URL")
    ref = body.get("ref") or ""
    if ref and not applications.valid_branch_ref(ref):
        raise HTTPException(422, "Choose a valid branch")
    name = applications.safe_name(body.get("name") or Path(source).stem)
    with connection() as db:
        if db.execute("SELECT 1 FROM applications WHERE name=?", (name,)).fetchone():
            raise HTTPException(409, "An application with this name already exists. Use Redeploy instead.")
    job = jobs.create_job(name, "app:" + name, source, ref)
    jobs.submit_job(job, lambda: applications.deploy_github(body), secrets)
    return job


def application(app_id):
    with connection() as db:
        row = db.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Application not found")
    return dict(row)


@router.post("/apps/{app_id}/github", status_code=202)
def queue_redeploy_github(app_id: str):
    app = application(app_id)
    if app["source_type"] not in ("github", "github-private"):
        raise HTTPException(409, "This application was not deployed from GitHub")
    secrets = environment_values(json.loads(app["env_json"] or "{}"))
    token = credential() if app["source_type"] == "github-private" else None
    if app["source_type"] == "github-private" and not token:
        raise HTTPException(409, "Reconnect GitHub in Settings")
    secrets.append(token)
    job = jobs.create_job(app["name"], "app:" + app["name"], app["source"], app["source_ref"], app_id=app_id)
    jobs.submit_job(job, lambda: applications.redeploy_github(app_id), secrets)
    return job


async def stage_zip(file):
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(422, "Upload a .zip archive")
    directory = Path(tempfile.mkdtemp(prefix="upload-", dir=WORKSPACE_DIR))
    try:
        total = 0
        with (directory / "source.zip").open("wb") as target:
            while data := await file.read(1024 * 1024):
                total += len(data)
                if total > 200 * 1024 * 1024:
                    raise HTTPException(413, "ZIP uploads are limited to 200 MB")
                target.write(data)
        return directory
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise


@router.post("/zip", status_code=202)
async def queue_zip(file: UploadFile = File(...), name: str = Form(...), domain: str = Form(""), environment: str = Form("{}")):
    try:
        secrets = environment_values(json.loads(environment))
    except ValueError as exc:
        raise HTTPException(422, "Environment must be a JSON object") from exc
    name = applications.safe_name(name)
    directory = await stage_zip(file)
    try:
        job = jobs.create_job(name, "app:" + name, "ZIP upload")
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    def work():
        with (directory / "source.zip").open("rb") as source:
            return asyncio.run(applications.deploy_zip(UploadFile(file=source, filename="source.zip"), name, domain, environment))
    jobs.submit_job(job, work, secrets, lambda: shutil.rmtree(directory, ignore_errors=True))
    return job


@router.post("/apps/{app_id}/zip", status_code=202)
async def queue_redeploy_zip(app_id: str, file: UploadFile = File(...)):
    app = application(app_id)
    secrets = environment_values(json.loads(app["env_json"] or "{}"))
    directory = await stage_zip(file)
    try:
        job = jobs.create_job(app["name"], "app:" + app["name"], "ZIP upload", app_id=app_id)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    def work():
        with (directory / "source.zip").open("rb") as source:
            return asyncio.run(applications.redeploy_zip(app_id, UploadFile(file=source, filename="source.zip")))
    jobs.submit_job(job, work, secrets, lambda: shutil.rmtree(directory, ignore_errors=True))
    return job


@router.get("/{job_id}")
def job_details(job_id: str, after: int = Query(0, ge=0), stage: str | None = None):
    job = jobs.get_job(job_id)
    with connection() as db:
        rows = db.execute("SELECT id,created_at,stage,level,message FROM deployment_job_logs WHERE job_id=? AND id>? AND (? IS NULL OR stage=?) ORDER BY id LIMIT 501", (job_id, after, stage, stage)).fetchall()
        job["stages"] = [dict(r) for r in db.execute("SELECT name,status,started_at,finished_at,duration_seconds,exit_code FROM deployment_job_stages WHERE job_id=? ORDER BY rowid",(job_id,))]
    job["logs"] = [dict(row) for row in rows[:500]]
    job["next_cursor"] = rows[min(499, len(rows) - 1)]["id"] if rows else after
    job["has_more"] = len(rows) > 500
    return job


@router.get("/{job_id}/logs", response_class=PlainTextResponse)
def download_logs(job_id: str):
    jobs.get_job(job_id)
    with connection() as db:
        rows = db.execute("SELECT created_at,stage,level,message FROM deployment_job_logs WHERE job_id=? ORDER BY id", (job_id,)).fetchall()
    return PlainTextResponse("\n".join(f"{r['created_at']} [{r['stage']}] {r['level'].upper()} {r['message']}" for r in rows),
                             headers={"Content-Disposition": f'attachment; filename="deployment-{job_id}.log"'})
