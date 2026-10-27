import json
import re
import shutil
import subprocess
import uuid
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

router = APIRouter(prefix="/api/apps", tags=["applications"], dependencies=[Depends(get_current_user)])

def now(): return datetime.now(timezone.utc).isoformat()

def detect_framework(root: Path):
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
    slug = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")[:45]
    if not slug: raise HTTPException(400, "Choose a valid application name")
    return slug

def deploy_tree(name: str, source: str, root: Path, domain: str | None, env_json: str = "{}"):
    if domain and (len(domain) > 253 or not re.fullmatch(r"(?=.{1,253}$)([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", domain)):
        raise HTTPException(400, "Enter a valid hostname")
    try:
        env = json.loads(env_json)
        if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()): raise ValueError()
    except (TypeError, ValueError):
        raise HTTPException(400, "Environment variables must be a JSON object of string values")
    framework, port, kind = detect_framework(root)
    generated_dockerfile(root, kind, framework, port)
    app_id = str(uuid.uuid4())
    safe = safe_name(name)
    with connection() as db:
        if db.execute("SELECT 1 FROM applications WHERE name=?",(safe,)).fetchone():
            raise HTTPException(409,"An application with this name already exists")
        if domain and db.execute("SELECT 1 FROM applications WHERE domain=?",(domain,)).fetchone():
            raise HTTPException(409,"This domain is already assigned to an application")
    image_tag = f"arfeen/{safe}:{app_id[:8]}"
    docker = client()
    try:
        image, _ = docker.images.build(path=str(root), tag=image_tag, rm=True, pull=True)
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
    networks = ["arfeen_internal", "arfeen_proxy"]
    kwargs = {"image": image.id, "name": f"arfeen-{safe}-{app_id[:8]}", "detach": True, "environment": env, "labels": labels, "ports": {f"{port}/tcp": host_port} if host_port else None, "network": "arfeen_internal"}
    if domain:
        kwargs["labels"].update({"traefik.enable": "true", "traefik.http.routers." + safe + ".rule": f"Host(`{domain}`)", "traefik.http.routers." + safe + ".entrypoints": "web", "traefik.http.services." + safe + ".loadbalancer.server.port": str(port)})
        kwargs["ports"] = None
    container = docker.containers.run(**kwargs)
    for network_name in networks:
        try: docker.networks.get(network_name).connect(container)
        except docker.errors.NotFound: pass
    with connection() as db:
        db.execute("INSERT INTO applications(id,name,source,framework,port,host_port,status,container_id,image,domain,created_at,env_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (app_id, safe, source, framework, port, host_port, "running", container.id, image_tag, domain, now(), env_json))
        db.execute("INSERT INTO deployments(id,app_id,status,message,created_at,image) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), app_id, "success", "Build and deployment completed", now(), image_tag))
    return {"id": app_id, "name": safe, "source": source, "framework": framework, "port": port, "host_port": host_port, "status": "running", "container_id": container.short_id, "image": image_tag, "domain": domain, "url": f"http://{domain}" if domain else f"http://SERVER-IP:{host_port}"}

@router.get("")
def list_apps():
    with connection() as db:
        rows = db.execute("SELECT * FROM applications ORDER BY created_at DESC").fetchall()
    result = []
    for row in rows:
        value = dict(row)
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
    url = body.get("url", "")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise HTTPException(400, "Only HTTPS GitHub repository URLs are supported")
    name = safe_name(body.get("name") or Path(parsed.path.rstrip("/")).stem)
    source_dir = WORKSPACE_DIR / str(uuid.uuid4())
    source_dir.mkdir(parents=True)
    result = subprocess.run(["git", "clone", "--depth", "1", "--", url.removesuffix(".git"), str(source_dir)], capture_output=True, text=True, timeout=180)
    if result.returncode:
        shutil.rmtree(source_dir, ignore_errors=True)
        raise HTTPException(400, f"Git clone failed: {result.stderr[-1500:]}")
    try:
        return deploy_tree(name, url, source_dir, body.get("domain"), json.dumps(body.get("environment", {})))
    finally: shutil.rmtree(source_dir, ignore_errors=True)

@router.post("/zip")
async def deploy_zip(file: UploadFile = File(...), name: str = Form(...), domain: str = Form(""), environment: str = Form("{}")):
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
        return deploy_tree(name, "ZIP upload", root, domain or None, environment)
    finally: shutil.rmtree(source_dir, ignore_errors=True)

def redeploy_tree(app_id: str, root: Path, source: str):
    with connection() as db: row=db.execute("SELECT * FROM applications WHERE id=?",(app_id,)).fetchone()
    if not row: raise HTTPException(404,"Application not found")
    framework,port,kind=detect_framework(root)
    generated_dockerfile(root,kind,framework,port)
    build_id=str(uuid.uuid4()); image_tag=f"arfeen/{row['name']}:{build_id[:8]}"; docker=client()
    try: image,_=docker.images.build(path=str(root),tag=image_tag,rm=True,pull=True)
    except BuildError as exc:
        detail="\n".join(x.get("stream","") for x in exc.build_log if x.get("stream"))[-6000:]
        raise HTTPException(400,f"Image build failed: {detail}")
    try: old=docker.containers.get(row["container_id"]); old_labels=dict(old.attrs.get("Config",{}).get("Labels") or {}); old_state=old.status
    except Exception: old=None; old_labels={"com.arfeen.managed":"true","com.arfeen.app-id":app_id}; old_state="missing"
    labels=old_labels | {"com.arfeen.managed":"true","com.arfeen.app-id":app_id}
    if row["domain"]:
        labels.update({"traefik.enable":"true",f"traefik.http.routers.{row['name']}.rule":f"Host(`{row['domain']}`)",f"traefik.http.routers.{row['name']}.entrypoints":"web",f"traefik.http.services.{row['name']}.loadbalancer.server.port":str(port)})
    previous_image=row["image"]
    try:
        if old:
            if old.status=="running": old.stop(timeout=10)
            old.remove()
        replacement=docker.containers.run(image.id,name=f"arfeen-{row['name']}-{build_id[:8]}",detach=True,environment=json.loads(row["env_json"] or "{}"),labels=labels,ports=({f"{port}/tcp":row["host_port"]} if row["host_port"] else None),network="arfeen_internal")
        if row["domain"]:
            try: docker.networks.get("arfeen_proxy").connect(replacement)
            except docker.errors.NotFound: pass
    except Exception as exc:
        if old and old_state=="running":
            try: old.start()
            except Exception: pass
        raise HTTPException(400,f"Could not start the new deployment: {exc}")
    with connection() as db:
        db.execute("UPDATE applications SET source=?,framework=?,port=?,container_id=?,image=?,status='running' WHERE id=?",(source,framework,port,replacement.id,image_tag,app_id))
        db.execute("INSERT INTO deployments(id,app_id,status,message,created_at,image) VALUES(?,?,?,?,?,?)",(build_id,app_id,"success",f"Redeployed {framework}",now(),image_tag))
    return {"id":app_id,"name":row["name"],"framework":framework,"image":image_tag,"status":"running","previous_image":previous_image}

@router.post("/{app_id}/redeploy/github")
def redeploy_github(app_id: str):
    with connection() as db: row=db.execute("SELECT source FROM applications WHERE id=?",(app_id,)).fetchone()
    if not row: raise HTTPException(404,"Application not found")
    parsed=urlparse(row["source"])
    if parsed.scheme!="https" or parsed.hostname not in {"github.com","www.github.com"}:
        raise HTTPException(409,"This application was not deployed from a public GitHub URL")
    source_dir=WORKSPACE_DIR/str(uuid.uuid4());source_dir.mkdir(parents=True)
    try:
        result=subprocess.run(["git","clone","--depth","1","--",row["source"].removesuffix(".git"),str(source_dir)],capture_output=True,text=True,timeout=180)
        if result.returncode: raise HTTPException(400,f"Git clone failed: {result.stderr[-1500:]}")
        return redeploy_tree(app_id,source_dir,row["source"])
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
        return [dict(r) for r in db.execute("SELECT * FROM deployments WHERE app_id=? ORDER BY created_at DESC", (app_id,)).fetchall()]

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
