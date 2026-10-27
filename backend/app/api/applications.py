import json
import os
import re
import signal
import selectors
import time
import codecs
import shutil
import subprocess
import uuid
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import docker
from docker.errors import BuildError
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from ..core.auth import get_current_user
from ..core.config import WORKSPACE_DIR
from ..core.db import connection
from ..services.docker_engine import client
from ..services.github import GitHubError, github_token
from ..services import deployment_jobs as jobs

router = APIRouter(prefix="/api/apps", tags=["applications"], dependencies=[Depends(get_current_user)])

def now(): return datetime.now(timezone.utc).isoformat()

def record_deployment_attempt(attempt_id: str, source: str, source_ref: str, status: str, stage: str, message: str, app_id: str | None = None, image: str | None = None):
    with connection() as db:
        db.execute(
            "INSERT INTO deployment_attempts(id,app_id,source,source_ref,status,stage,message,created_at,image) VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET app_id=excluded.app_id,source=excluded.source,source_ref=excluded.source_ref,status=excluded.status,stage=excluded.stage,message=excluded.message,image=excluded.image",
            (attempt_id, app_id, source, source_ref, status, stage, message[:2000], now(), image),
        )

def mark_attempt(attempt: dict, status: str, stage: str, message: str, app_id: str | None = None, image: str | None = None):
    jobs.stage(stage, message)
    attempt["stage"] = stage
    if app_id is not None:
        attempt["app_id"] = app_id
    if image is not None:
        attempt["image"] = image
    record_deployment_attempt(attempt["id"], attempt["source"], attempt["ref"], status, stage, message, attempt.get("app_id"), attempt.get("image"))

def safe_deployment_error(exc: Exception, token: str | None = None, environment: dict | None = None) -> str:
    message = exc.detail if isinstance(exc, HTTPException) else str(exc)
    message = message if isinstance(message, str) else "Deployment failed"
    secrets_to_hide = [token] if token else []
    if isinstance(environment, dict):
        secrets_to_hide.extend(value for value in environment.values() if isinstance(value, str) and value)
    for secret in secrets_to_hide:
        if secret:
            message = message.replace(secret, "[redacted]")
    return message[:2000]

def dockerfile_tcp_port(path: Path) -> int:
    lines = path.read_text(errors="ignore").splitlines()
    final_stage_start = None
    for index, line in enumerate(lines):
        if re.match(r"^\s*FROM(?:\s+|$)", line, re.IGNORECASE):
            final_stage_start = index + 1

    ports = set()
    for line in lines[final_stage_start:] if final_stage_start is not None else []:
        instruction = line.split("#", 1)[0].strip()
        match = re.match(r"^EXPOSE\s+(.+)$", instruction, re.IGNORECASE)
        if not match:
            continue
        for value in match.group(1).split():
            port_value, separator, protocol = value.rpartition("/")
            if separator:
                if protocol.lower() != "tcp":
                    continue
                value = port_value
            if value.isdigit() and 1 <= int(value) <= 65535:
                ports.add(int(value))

    if not ports:
        raise HTTPException(422, "Dockerfile applications must declare one literal TCP port with EXPOSE <port> in the final build stage.")
    if len(ports) > 1:
        raise HTTPException(422, "Dockerfile applications must declare only one TCP port with EXPOSE <port> in the final build stage.")
    return ports.pop()


def detect_framework(root: Path):
    dockerfile = root / "Dockerfile"
    if dockerfile.exists():
        return "Dockerfile", dockerfile_tcp_port(dockerfile), "dockerfile"
    names = {p.name for p in root.iterdir()}
    if "manage.py" in names: return "Django", 8000, "python"
    if "requirements.txt" in names or "pyproject.toml" in names:
        text = " ".join((root / f).read_text(errors="ignore") for f in ("requirements.txt", "pyproject.toml") if (root / f).exists()).lower()
        if "fastapi" in text: return "FastAPI", 8000, "python"
        if "flask" in text: return "Flask", 5000, "python"
        return "Python", 8000, "python"
    package = root / "package.json"
    if package.exists():
        try: data = json.loads(package.read_text())
        except Exception: data = {}
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        if "next" in deps: return "Next.js", int(data.get("arfeen", {}).get("port", 3000)), "node"
        if "@angular/cli" in deps: return "Angular", 80, "static"
        if "vue" in deps: return "Vue", 80, "static"
        if "react-scripts" in deps: return "React", 80, "static"
        if "vite" in deps: return "React / SPA", 80, "static"
        return "Node.js", int(data.get("arfeen", {}).get("port", 3000)), "node"
    if "index.html" in names: return "Static site", 80, "static"
    if "pom.xml" in names: return "Spring Boot", 8080, "java"
    if "go.mod" in names: return "Go", 8080, "go"
    raise HTTPException(422, "Could not detect a supported framework. Add package.json, requirements.txt, pyproject.toml, pom.xml, go.mod, or index.html.")

def generated_dockerfile(root: Path, kind: str, framework: str, port: int):
    if (root / "Dockerfile").exists(): return
    if kind == "python":
        install = "pip install -r requirements.txt" if (root / "requirements.txt").exists() else "pip install ."
        if framework == "FastAPI": cmd = f"uvicorn main:app --host 0.0.0.0 --port {port}"
        elif framework == "Flask": cmd = f"gunicorn -b 0.0.0.0:{port} app:app"
        elif framework == "Django": cmd = f"python manage.py runserver 0.0.0.0:{port}"
        else: cmd = f"python main.py"
        root.joinpath("Dockerfile").write_text(f"FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\nRUN {install} && pip install uvicorn gunicorn\nEXPOSE {port}\nCMD [\"sh\", \"-lc\", \"{cmd}\"]\n")
    elif kind == "static":
        if (root / "package.json").exists():
            package=json.loads((root/"package.json").read_text())
            deps={**package.get("dependencies",{}),**package.get("devDependencies",{})}
            output="/app/build" if "react-scripts" in deps else "/app/dist"
            if "@angular/cli" in deps:
                output=f"/app/dist/{package.get('name','app')}/browser"
            root.joinpath("Dockerfile").write_text(f"FROM node:22-alpine AS build\nWORKDIR /app\nCOPY package*.json ./\nRUN npm install\nCOPY . .\nRUN npm run build\nFROM nginx:alpine\nCOPY --from=build {output} /usr/share/nginx/html\nEXPOSE 80\n")
        else: root.joinpath("Dockerfile").write_text("FROM nginx:alpine\nCOPY . /usr/share/nginx/html\nEXPOSE 80\n")
    elif kind == "node":
        root.joinpath("Dockerfile").write_text(f"FROM node:22-alpine\nWORKDIR /app\nCOPY package*.json ./\nRUN npm install\nCOPY . .\nRUN npm run build --if-present\nEXPOSE {port}\nCMD [\"npm\", \"start\"]\n")
    elif kind == "java":
        root.joinpath("Dockerfile").write_text("FROM maven:3.9-eclipse-temurin-21 AS build\nWORKDIR /src\nCOPY . .\nRUN mvn package -DskipTests\nFROM eclipse-temurin:21-jre\nCOPY --from=build /src/target/*.jar /app.jar\nEXPOSE 8080\nENTRYPOINT [\"java\",\"-jar\",\"/app.jar\"]\n")
    else:
        root.joinpath("Dockerfile").write_text("FROM golang:1.24-alpine AS build\nWORKDIR /src\nCOPY . .\nRUN go build -o /app .\nFROM alpine:3.21\nCOPY --from=build /app /app\nEXPOSE 8080\nCMD [\"/app\"]\n")

def safe_name(value):
    if not isinstance(value, str):
        raise HTTPException(400, "Choose a valid application name")
    slug = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")[:45]
    if not slug: raise HTTPException(400, "Choose a valid application name")
    return slug

def valid_branch_ref(value):
    if not isinstance(value, str) or not value or len(value) > 255 or value.startswith("-") or value.endswith(("/", ".")) or ".." in value or "@{" in value or value == "@":
        return False
    if any(ord(char) < 32 or ord(char) == 127 or char in " ~^:?*[" or char == "\\" for char in value):
        return False
    return all(part and not part.startswith(".") and not part.endswith(".lock") for part in value.split("/"))

def canonical_github_url(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"} or parsed.username or parsed.password or port:
        return None
    match = re.fullmatch(r"/([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100})(?:\.git)?/?", parsed.path)
    if not match:
        return None
    return f"https://github.com/{match.group(1)}/{match.group(2)}.git"

def build_image(engine, root: Path, image_tag: str):
    if not jobs.output():
        image, _ = engine.images.build(path=str(root), tag=image_tag, rm=True, pull=True, timeout=1800)
        return image
    pending = ""
    stream = engine.api.build(path=str(root), tag=image_tag, rm=True, pull=True, timeout=1800, decode=True)
    try:
        for event in stream:
            if event.get("error") or event.get("errorDetail"):
                error = event.get("error") or event["errorDetail"].get("message", "Docker build failed")
                raise HTTPException(400, f"Image build failed: {error}")
            if "stream" in event:
                pending += event["stream"]
                lines = re.split(r"[\r\n]", pending)
                pending = lines.pop()
                for line in lines:
                    jobs.log(line)
                # Bound pathological output without storing incomplete secret-bearing lines.
                if len(pending) > 1024 * 1024:
                    pending = "[Oversized build output line omitted]"
            elif event.get("status"):
                progress = event.get("progress", "")
                jobs.log(f"{event.get('id', '')} {event['status']} {progress}".strip())
        jobs.log(pending)
    finally:
        if hasattr(stream, "close"):
            stream.close()
    return engine.images.get(image_tag)


def verify_container(container):
    if not jobs.output():
        return
    jobs.stage("verify", "Checking container startup and health")
    deadline = time.monotonic() + 90
    time.sleep(2)
    while True:
        container.reload()
        state = container.attrs.get("State", {})
        health = state.get("Health", {}).get("Status")
        if container.status != "running" or health == "unhealthy":
            jobs.log(container.logs(tail=50).decode("utf-8", errors="replace"), "error")
            raise HTTPException(400, f"Container startup failed: status={container.status}, health={health or 'not configured'}")
        if health != "starting":
            jobs.log("Container health check passed" if health == "healthy" else "Container is running (no Docker health check is configured)")
            return
        if time.monotonic() >= deadline:
            jobs.log(container.logs(tail=50).decode("utf-8", errors="replace"), "error")
            raise HTTPException(400, "Container health check did not become ready within 90 seconds")
        time.sleep(2)


def deploy_tree(name: str, source: str, root: Path, domain: str | None, env_json: str = "{}", source_type: str = "github", source_ref: str = "", attempt: dict | None = None):
    if domain and (len(domain) > 253 or not re.fullmatch(r"(?=.{1,253}$)([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", domain)):
        raise HTTPException(400, "Enter a valid hostname")
    try:
        env = json.loads(env_json)
        if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()): raise ValueError()
    except (TypeError, ValueError):
        raise HTTPException(400, "Environment variables must be a JSON object of string values")
    jobs.add_secrets(env.values())
    if attempt:
        mark_attempt(attempt, "running", "detect", "Detecting application framework")
    else:
        jobs.stage("detect", "Detecting application framework")
    framework, port, kind = detect_framework(root)
    jobs.log(f"Detected {framework}; container port {port}; build context {root}")
    generated_dockerfile(root, kind, framework, port)
    app_id = str(uuid.uuid4())
    if attempt:
        mark_attempt(attempt, "running", "build", "Building the application image", app_id)
    else:
        jobs.stage("build", "Building the application image")
    safe = safe_name(name)
    with connection() as db:
        if db.execute("SELECT 1 FROM applications WHERE name=?",(safe,)).fetchone():
            raise HTTPException(409,"An application with this name already exists")
        if domain and db.execute("SELECT 1 FROM applications WHERE domain=?",(domain,)).fetchone():
            raise HTTPException(409,"This domain is already assigned to an application")
    image_tag = f"arfeen/{safe}:{app_id[:8]}"
    docker = client()
    try:
        image = build_image(docker, root, image_tag)
    except BuildError as exc:
        detail = "\n".join(x.get("stream", "") for x in exc.build_log if x.get("stream"))[-6000:]
        raise HTTPException(400, f"Image build failed: {detail}")
    host_port = None
    if not domain:
        occupied = set()
        for existing in docker.containers.list(all=True):
            for bindings in (existing.attrs.get("NetworkSettings", {}).get("Ports", {}) or {}).values():
                for binding in bindings or []:
                    try: occupied.add(int(binding.get("HostPort", 0)))
                    except (TypeError, ValueError): pass
        start = 45000 + (int(uuid.UUID(app_id)) % 10000)
        host_port = next((45000 + ((start - 45000 + offset) % 10000) for offset in range(10000) if 45000 + ((start - 45000 + offset) % 10000) not in occupied), None)
        if host_port is None:
            raise HTTPException(503, "No free application ports are available")
    labels = {"com.arfeen.managed": "true", "com.arfeen.app-id": app_id}
    kwargs = {"image": image.id, "name": f"arfeen-{safe}-{app_id[:8]}", "detach": True, "environment": env, "labels": labels, "ports": {f"{port}/tcp": host_port} if host_port else None, "network": "arfeen_internal"}
    if domain:
        kwargs["labels"].update({"traefik.enable": "true", "traefik.http.routers." + safe + ".rule": f"Host(`{domain}`)", "traefik.http.routers." + safe + ".entrypoints": "web", "traefik.http.services." + safe + ".loadbalancer.server.port": str(port)})
        kwargs["ports"] = None
    if attempt:
        mark_attempt(attempt, "running", "deploy", "Starting the application container", app_id, image_tag)
    else:
        jobs.stage("deploy", "Starting the application container")
    container = docker.containers.run(**kwargs)
    try:
        docker.networks.get("arfeen_proxy").connect(container)
        jobs.log(f"Started container {container.short_id}; image {image_tag}")
        verify_container(container)
    except Exception:
        try:
            container.remove(force=True)
        except Exception as cleanup_error:
            jobs.log(f"Could not remove failed container {container.short_id}: {cleanup_error}", "error")
        raise
    with connection() as db:
        db.execute("INSERT INTO applications(id,name,source,framework,port,host_port,status,container_id,image,domain,created_at,env_json,source_type,source_ref) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (app_id, safe, source, framework, port, host_port, "running", container.id, image_tag, domain, now(), env_json, source_type, source_ref))
        db.execute("INSERT INTO deployments(id,app_id,status,message,created_at,image) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), app_id, "success", "Build and deployment completed", now(), image_tag))
    if attempt:
        mark_attempt(attempt, "success", "complete", "Build and deployment completed", app_id, image_tag)
    return {"id": app_id, "name": safe, "source": source, "source_type": source_type, "source_ref": source_ref, "framework": framework, "port": port, "host_port": host_port, "status": "running", "container_id": container.short_id, "image": image_tag, "domain": domain, "url": f"http://{domain}" if domain else f"http://SERVER-IP:{host_port}"}

@router.get("")
def list_apps():
    with connection() as db:
        rows = db.execute("SELECT * FROM applications ORDER BY created_at DESC").fetchall()
    result = []
    for row in rows:
        value = dict(row)
        if value.get("source_type", "github").startswith("github"):
            value["source"] = canonical_github_url(value.get("source")) or "GitHub repository"
        try:
            container=client().containers.get(value["container_id"])
            value["status"] = container.status
            value["health"] = container.attrs.get("State",{}).get("Health",{}).get("Status",container.status)
        except Exception: value["status"] = "exited"
        value.pop("env_json", None)
        result.append(value)
    return result

@router.post("/github")
def deploy_github(body: dict):
    owner, repo, ref = body.get("owner"), body.get("repo"), body.get("ref", "")
    if ref is None:
        ref = ""
    source_type = "github"
    token = None
    if owner is not None or repo is not None:
        segment = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
        if not isinstance(owner, str) or not segment.fullmatch(owner) or not isinstance(repo, str) or not segment.fullmatch(repo):
            raise HTTPException(400, "Choose a valid GitHub owner and repository")
        if not valid_branch_ref(ref):
            raise HTTPException(400, "Choose a valid branch")
        try:
            token = github_token()
        except GitHubError as exc:
            raise HTTPException(503, str(exc)) from exc
        if not token:
            raise HTTPException(409, "Connect a GitHub token in Settings before deploying a private repository")
        url = f"https://github.com/{owner}/{repo}.git"
        source_type = "github-private"
    else:
        url = body.get("url", "")
        if not isinstance(url, str):
            raise HTTPException(400, "Enter a GitHub repository URL")
        try:
            parsed = urlparse(url)
            port = parsed.port
        except ValueError as exc:
            raise HTTPException(400, "Enter a valid GitHub repository URL") from exc
        if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"} or parsed.username or parsed.password or port or parsed.query or parsed.fragment:
            raise HTTPException(400, "Only plain HTTPS GitHub repository URLs are supported")
        match = re.fullmatch(r"/([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100})(?:\.git)?/?", parsed.path)
        if not match:
            raise HTTPException(400, "Enter a GitHub repository URL in owner/repository format")
        if ref and not valid_branch_ref(ref):
            raise HTTPException(400, "Choose a valid branch")
        url = f"https://github.com/{match.group(1)}/{match.group(2)}.git"
    app_name = body.get("name") or Path(urlparse(url).path.rstrip("/")).stem.removesuffix(".git")
    if not isinstance(app_name, str):
        raise HTTPException(400, "Enter a valid application name")
    domain = body.get("domain") or None
    if domain is not None and not isinstance(domain, str):
        raise HTTPException(400, "Enter a valid hostname")
    name = safe_name(app_name)
    source_dir = WORKSPACE_DIR / str(uuid.uuid4())
    source_dir.mkdir(parents=True)
    attempt = {"id": str(uuid.uuid4()), "source": url, "ref": ref, "stage": "clone"}
    mark_attempt(attempt, "running", "clone", "Fetching repository source")
    environment = body.get("environment", {})
    try:
        clone_github_repository(url, ref, source_dir, token)
        return deploy_tree(name, url, source_dir, domain, json.dumps(environment), source_type, ref, attempt)
    except Exception as exc:
        detail = safe_deployment_error(exc, token, environment)
        mark_attempt(attempt, "failed", attempt["stage"], detail or "Deployment failed")
        if isinstance(exc, GitHubError):
            raise HTTPException(400, detail) from exc
        if isinstance(exc, HTTPException):
            if detail == exc.detail:
                raise
            raise HTTPException(exc.status_code, detail) from exc
        raise HTTPException(500, f"Deployment failed during {attempt['stage']}. Check deployment history.") from exc
    finally: shutil.rmtree(source_dir, ignore_errors=True)


def stream_clone(process):
    deadline = time.monotonic() + 900
    pending = ""
    tail = ""
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired("git clone", 900)
            if not selector.select(timeout=1):
                continue
            data = os.read(process.stdout.fileno(), 4096)
            if not data:
                pending += decoder.decode(b"", final=True)
                jobs.log(pending)
                tail = (tail + pending)[-2000:]
                break
            pending += decoder.decode(data)
            lines = re.split(r"[\r\n]", pending)
            pending = lines.pop()
            for line in lines:
                jobs.log(line)
                tail = (tail + line + "\n")[-2000:]
            if len(pending) > 1024 * 1024:
                pending = "[Oversized Git output line omitted]"
    process.wait(timeout=max(1, deadline - time.monotonic()))
    return tail


def clone_github_repository(url: str, ref: str, destination: Path, token: str | None = None):
    jobs.add_secrets([token])
    jobs.stage("clone", f"Fetching {url} ({ref or 'default branch'})")
    command = ["git", "clone", "--depth", "1", "--single-branch", "--progress"]
    if ref:
        command.append(f"--branch={ref}")
    command.extend(["--", url, str(destination)])
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    helper_dir = None
    try:
        if token:
            helper_dir = tempfile.TemporaryDirectory(prefix="arfeen-git-askpass-")
            helper = Path(helper_dir.name) / "askpass"
            helper.write_text("#!/bin/sh\ncase \"$1\" in\n  *'https://github.com:'*|*'https://github.com/'*|*'https://www.github.com:'*|*'https://www.github.com/'*) ;;\n  *) exit 1 ;;\nesac\ncase \"$1\" in\n  *sername*) printf '%s\\n' x-access-token ;;\n  *assword*) printf '%s\\n' \"$ARFEEN_GITHUB_TOKEN\" ;;\n  *) exit 1 ;;\nesac\n")
            helper.chmod(0o700)
            environment["GIT_ASKPASS"] = str(helper)
            environment["GIT_TERMINAL_PROMPT"] = "0"
            environment["ARFEEN_GITHUB_TOKEN"] = token
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT if jobs.output() else subprocess.PIPE,
                                   text=not bool(jobs.output()), env=environment, start_new_session=True)
        try:
            if jobs.output():
                stderr = stream_clone(process)
            else:
                _, stderr = process.communicate(timeout=900)
        except BaseException as exc:
            # Git launches transport/index-pack children; stop the entire clone.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            if isinstance(exc, subprocess.TimeoutExpired):
                raise GitHubError("GitHub clone timed out after 900 seconds.") from exc
            raise
        if process.returncode:
            detail = stderr.replace(token, "[redacted]") if token else stderr
            raise GitHubError(f"GitHub clone failed: {detail[-1200:].strip() or 'check repository access and branch name'}")
    finally:
        if helper_dir:
            helper_dir.cleanup()

@router.post("/zip")
async def deploy_zip(file: UploadFile = File(...), name: str = Form(...), domain: str = Form(""), environment: str = Form("{}")):
    jobs.stage("clone", "Unpacking uploaded ZIP archive")
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(400, "Upload a .zip archive")
    source_dir = WORKSPACE_DIR / str(uuid.uuid4())
    source_dir.mkdir(parents=True)
    archive = source_dir / "source.zip"
    total = 0
    with archive.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk: break
            total += len(chunk)
            if total > 200 * 1024 * 1024:
                shutil.rmtree(source_dir, ignore_errors=True)
                raise HTTPException(413, "ZIP uploads are limited to 200 MB")
            out.write(chunk)
    import zipfile
    extracted = source_dir / "src"
    extracted.mkdir()
    try:
        with zipfile.ZipFile(archive) as zf:
            if len(zf.infolist()) > 20000 or sum(item.file_size for item in zf.infolist()) > 500 * 1024 * 1024:
                raise HTTPException(413, "Expanded ZIP archives are limited to 500 MB and 20,000 files")
            for member in zf.infolist():
                target = (extracted / member.filename).resolve()
                if extracted.resolve() not in target.parents and target != extracted.resolve():
                    raise HTTPException(400, "Archive contains an unsafe path")
            zf.extractall(extracted)
    except zipfile.BadZipFile:
        shutil.rmtree(source_dir, ignore_errors=True)
        raise HTTPException(400, "Could not read ZIP archive")
    except HTTPException:
        shutil.rmtree(source_dir, ignore_errors=True)
        raise
    archive.unlink(missing_ok=True)
    children = list(extracted.iterdir())
    root = children[0] if len(children) == 1 and children[0].is_dir() else extracted
    try:
        return deploy_tree(name, "ZIP upload", root, domain or None, environment, "zip", "")
    finally: shutil.rmtree(source_dir, ignore_errors=True)

def redeploy_tree(app_id: str, root: Path, source: str, attempt: dict | None = None):
    with connection() as db: row=db.execute("SELECT * FROM applications WHERE id=?",(app_id,)).fetchone()
    if not row: raise HTTPException(404,"Application not found")
    jobs.add_secrets(json.loads(row["env_json"] or "{}").values())
    if attempt: mark_attempt(attempt,"running","detect","Detecting application framework",app_id)
    else: jobs.stage("detect", "Detecting application framework")
    framework,port,kind=detect_framework(root)
    jobs.log(f"Detected {framework}; container port {port}; build context {root}")
    generated_dockerfile(root,kind,framework,port)
    build_id=str(uuid.uuid4()); image_tag=f"arfeen/{row['name']}:{build_id[:8]}"; docker=client()
    if attempt: mark_attempt(attempt,"running","build","Building the replacement image",app_id)
    else: jobs.stage("build", "Building the replacement image")
    try: image=build_image(docker,root,image_tag)
    except BuildError as exc:
        detail="\n".join(x.get("stream","") for x in exc.build_log if x.get("stream"))[-6000:]
        raise HTTPException(400,f"Image build failed: {detail}")
    try: old=docker.containers.get(row["container_id"]); old_labels=dict(old.attrs.get("Config",{}).get("Labels") or {}); old_state=old.status
    except Exception: old=None; old_labels={"com.arfeen.managed":"true","com.arfeen.app-id":app_id}; old_state="missing"
    labels=old_labels | {"com.arfeen.managed":"true","com.arfeen.app-id":app_id}
    if row["domain"]:
        labels.update({"traefik.enable":"true",f"traefik.http.routers.{row['name']}.rule":f"Host(`{row['domain']}`)",f"traefik.http.routers.{row['name']}.entrypoints":"web",f"traefik.http.services.{row['name']}.loadbalancer.server.port":str(port)})
    previous_image=row["image"]
    replacement=None
    if attempt: mark_attempt(attempt,"running","deploy","Starting the replacement container",app_id,image_tag)
    else: jobs.stage("deploy", "Starting the replacement container")
    try:
        if old and old.status=="running": old.stop(timeout=10)
        replacement=docker.containers.create(image.id,name=f"arfeen-{row['name']}-{build_id[:8]}",environment=json.loads(row["env_json"] or "{}"),labels=labels,ports=({f"{port}/tcp":row["host_port"]} if row["host_port"] else None),network="arfeen_internal")
        if row["domain"]:
            docker.networks.get("arfeen_proxy").connect(replacement)
        replacement.start()
        verify_container(replacement)
    except Exception as exc:
        if replacement:
            try: replacement.remove(force=True)
            except Exception: pass
        if old and old_state=="running":
            try: old.start()
            except Exception: pass
        raise HTTPException(400,f"Could not start the new deployment: {exc}")
    if old:
        try: old.remove()
        except Exception: pass
    with connection() as db:
        db.execute("UPDATE applications SET source=?,framework=?,port=?,container_id=?,image=?,status='running' WHERE id=?",(source,framework,port,replacement.id,image_tag,app_id))
        db.execute("INSERT INTO deployments(id,app_id,status,message,created_at,image) VALUES(?,?,?,?,?,?)",(build_id,app_id,"success",f"Redeployed {framework}",now(),image_tag))
    if attempt: mark_attempt(attempt,"success","complete",f"Redeployed {framework}",app_id,image_tag)
    return {"id":app_id,"name":row["name"],"framework":framework,"image":image_tag,"status":"running","previous_image":previous_image}

@router.post("/{app_id}/redeploy/github")
def redeploy_github(app_id: str):
    with connection() as db: row=db.execute("SELECT source,source_type,source_ref,name FROM applications WHERE id=?",(app_id,)).fetchone()
    if not row: raise HTTPException(404,"Application not found")
    safe_source=canonical_github_url(row["source"])
    if row["source_type"] not in ("github", "github-private") or not safe_source:
        raise HTTPException(409,"This application was not deployed from a GitHub repository")
    source_dir=WORKSPACE_DIR/str(uuid.uuid4());source_dir.mkdir(parents=True)
    attempt={"id":str(uuid.uuid4()),"source":safe_source,"ref":row["source_ref"] or "","stage":"clone","app_id":app_id}
    mark_attempt(attempt,"running","clone","Fetching repository source",app_id)
    try:
        token = None
        if row["source_type"] == "github-private":
            try: token=github_token()
            except GitHubError as exc: raise HTTPException(503,str(exc)) from exc
            if not token: raise HTTPException(409,"Reconnect GitHub in Settings before redeploying this private repository")
        try: clone_github_repository(safe_source,row["source_ref"] or "",source_dir,token)
        except GitHubError as exc: raise HTTPException(400,str(exc)) from exc
        return redeploy_tree(app_id,source_dir,safe_source,attempt)
    except Exception as exc:
        try: environment=json.loads(row["env_json"] or "{}")
        except Exception: environment={}
        detail=safe_deployment_error(exc,token if "token" in locals() else None,environment)
        mark_attempt(attempt,"failed",attempt["stage"],detail or "Redeploy failed",app_id)
        if isinstance(exc,HTTPException):
            if detail == exc.detail: raise
            raise HTTPException(exc.status_code,detail) from exc
        if isinstance(exc,GitHubError): raise HTTPException(400,detail) from exc
        raise HTTPException(500,f"Redeploy failed during {attempt['stage']}. Check deployment history.") from exc
    finally: shutil.rmtree(source_dir,ignore_errors=True)

@router.post("/{app_id}/redeploy/zip")
async def redeploy_zip(app_id: str,file: UploadFile=File(...)):
    if not (file.filename or "").lower().endswith(".zip"): raise HTTPException(400,"Upload a .zip archive")
    source_dir=WORKSPACE_DIR/str(uuid.uuid4());source_dir.mkdir(parents=True);archive=source_dir/"source.zip";total=0
    try:
        with archive.open("wb") as out:
            while True:
                chunk=await file.read(1024*1024)
                if not chunk: break
                total+=len(chunk)
                if total>200*1024*1024: raise HTTPException(413,"ZIP uploads are limited to 200 MB")
                out.write(chunk)
        import zipfile
        extracted=source_dir/"src";extracted.mkdir()
        try:
            with zipfile.ZipFile(archive) as zf:
                if len(zf.infolist())>20000 or sum(x.file_size for x in zf.infolist())>500*1024*1024: raise HTTPException(413,"Expanded ZIP archives are limited to 500 MB and 20,000 files")
                for member in zf.infolist():
                    target=(extracted/member.filename).resolve()
                    if extracted.resolve() not in target.parents and target!=extracted.resolve(): raise HTTPException(400,"Archive contains an unsafe path")
                zf.extractall(extracted)
        except zipfile.BadZipFile: raise HTTPException(400,"Could not read ZIP archive")
        children=list(extracted.iterdir());root=children[0] if len(children)==1 and children[0].is_dir() else extracted
        return redeploy_tree(app_id,root,"ZIP upload")
    finally: shutil.rmtree(source_dir,ignore_errors=True)

@router.get("/{app_id}/deployments")
def deployment_history(app_id: str):
    with connection() as db:
        successful = [dict(r) for r in db.execute("SELECT * FROM deployments WHERE app_id=?", (app_id,)).fetchall()]
        failed = [dict(r) for r in db.execute("SELECT id,app_id,status,message,created_at,image,stage FROM deployment_attempts WHERE app_id=? AND status='failed'", (app_id,)).fetchall()]
    return sorted(successful + failed, key=lambda item: item["created_at"], reverse=True)

@router.get("/deployment-attempts")
def failed_deployment_attempts():
    with connection() as db:
        return [dict(row) for row in db.execute("SELECT a.id,a.app_id,a.source,a.source_ref,a.status,a.stage,a.message,a.created_at,a.image,ap.name AS app_name FROM deployment_attempts a LEFT JOIN applications ap ON ap.id=a.app_id WHERE a.status='failed' AND ap.id IS NULL ORDER BY a.created_at DESC LIMIT 200").fetchall()]

@router.get("/{app_id}/environment")
def get_environment(app_id: str):
    with connection() as db: row = db.execute("SELECT env_json FROM applications WHERE id=?", (app_id,)).fetchone()
    if not row: raise HTTPException(404, "Application not found")
    return {"environment": json.loads(row["env_json"] or "{}")}

@router.put("/{app_id}/environment")
def update_environment(app_id: str, body: dict):
    environment = body.get("environment")
    if not isinstance(environment, dict) or len(environment) > 100 or not all(isinstance(k,str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}",k) and isinstance(v,str) and len(v)<=8192 for k,v in environment.items()):
        raise HTTPException(422, "Environment must contain up to 100 valid key and string value pairs")
    with connection() as db: row = db.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    if not row: raise HTTPException(404, "Application not found")
    docker=client(); old_env=json.loads(row["env_json"] or "{}"); old= docker.containers.get(row["container_id"]); labels=dict(old.attrs.get("Config",{}).get("Labels") or {})
    try:
        old.stop(timeout=10); old.remove()
        replacement=docker.containers.run(row["image"],name=f"arfeen-{row['name']}-{uuid.uuid4().hex[:8]}",detach=True,environment=environment,labels=labels,ports=({f"{row['port']}/tcp":row["host_port"]} if row["host_port"] else None),network="arfeen_internal")
        if row["domain"]:
            try: docker.networks.get("arfeen_proxy").connect(replacement)
            except docker.errors.NotFound: pass
        with connection() as db:
            db.execute("UPDATE applications SET container_id=?,env_json=?,status='running' WHERE id=?",(replacement.id,json.dumps(environment),app_id))
            db.execute("INSERT INTO deployments(id,app_id,status,message,created_at,image) VALUES(?,?,?,?,?,?)",(str(uuid.uuid4()),app_id,"success","Application restarted with updated environment variables",now(),row["image"]))
        return {"ok":True,"status":"running"}
    except Exception as exc:
        try:
            restored=docker.containers.run(row["image"],name=f"arfeen-{row['name']}-{uuid.uuid4().hex[:8]}",detach=True,environment=old_env,labels=labels,ports=({f"{row['port']}/tcp":row["host_port"]} if row["host_port"] else None),network="arfeen_internal")
            if row["domain"]:
                try: docker.networks.get("arfeen_proxy").connect(restored)
                except docker.errors.NotFound: pass
            with connection() as db: db.execute("UPDATE applications SET container_id=? WHERE id=?",(restored.id,app_id))
        except Exception: pass
        raise HTTPException(400,f"Could not update environment and restart the app: {exc}")

@router.post("/{app_id}/{action}")
def app_action(app_id: str, action: str):
    with connection() as db:
        row = db.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    if not row: raise HTTPException(404, "Application not found")
    try:
        container = client().containers.get(row["container_id"])
        if action == "restart": container.restart()
        elif action == "start": container.start()
        elif action == "stop": container.stop()
        elif action == "rollback":
            with connection() as db:
                prev = db.execute("SELECT image FROM deployments WHERE app_id=? AND status='success' ORDER BY created_at DESC LIMIT 1 OFFSET 1", (app_id,)).fetchone()
            if not prev: raise HTTPException(409, "There is no earlier successful deployment to roll back to")
            image = client().images.get(prev["image"])
            container.stop(); container.remove()
            ports = {f"{row['port']}/tcp": row["host_port"]} if row["host_port"] else None
            old_labels=dict(container.attrs.get("Config",{}).get("Labels") or {})
            replacement = client().containers.run(image.id, name=f"arfeen-{row['name']}-{uuid.uuid4().hex[:8]}", detach=True, environment=json.loads(row["env_json"] or "{}"), labels=old_labels, ports=ports, network="arfeen_internal")
            if row["domain"]:
                try: client().networks.get("arfeen_proxy").connect(replacement)
                except docker.errors.NotFound: pass
            with connection() as db:
                db.execute("UPDATE applications SET container_id=?,image=?,status='running' WHERE id=?", (replacement.id, prev["image"], app_id))
                db.execute("INSERT INTO deployments(id,app_id,status,message,created_at,image) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()),app_id,"success","Rolled back to previous image",now(),prev["image"]))
        elif action == "delete":
            container.remove(force=True)
            with connection() as db: db.execute("DELETE FROM applications WHERE id=?", (app_id,)); db.execute("DELETE FROM deployments WHERE app_id=?", (app_id,))
            return {"ok": True}
        else: raise HTTPException(404, "Unsupported action")
        with connection() as db: db.execute("UPDATE applications SET status=? WHERE id=?", ("running" if action in ("start","restart","rollback") else "stopped",app_id))
        return {"ok": True, "status": action}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(400, str(exc))
