import secrets
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..core.auth import get_current_user
from ..core.db import connection
from ..services.docker_engine import client

router = APIRouter(prefix="/api/databases", tags=["databases"], dependencies=[Depends(get_current_user)])
ENGINES = {"postgresql": ("postgres:16-alpine", 5432), "mysql": ("mysql:8.4", 3306), "redis": ("redis:7-alpine", 6379)}
def now(): return datetime.now(timezone.utc).isoformat()

class DatabaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=48, pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")
    engine: str

@router.get("")
def list_databases():
    with connection() as db: rows = db.execute("SELECT id,name,engine,container_id,username,port,created_at FROM databases ORDER BY created_at DESC").fetchall()
    result=[]
    for row in rows:
        item=dict(row)
        try:
            container=client().containers.get(item["container_id"])
            item["status"] = container.status
            item["connection_host"] = container.name
        except Exception: item["status"] = "missing"
        result.append(item)
    return result

@router.post("")
def create_database(body: DatabaseCreate):
    engine=body.engine.lower()
    if engine not in ENGINES: raise HTTPException(400,"Choose PostgreSQL, MySQL, or Redis")
    id=str(uuid.uuid4()); password=secrets.token_urlsafe(24); image,port=ENGINES[engine]
    environment={}
    if engine=="postgresql": environment={"POSTGRES_DB":body.name,"POSTGRES_USER":"admin","POSTGRES_PASSWORD":password}
    elif engine=="mysql": environment={"MYSQL_DATABASE":body.name,"MYSQL_USER":"admin","MYSQL_PASSWORD":password,"MYSQL_ROOT_PASSWORD":secrets.token_urlsafe(32)}
    try:
        docker=client()
        volume=docker.volumes.create(name=f"arfeen-db-{id[:8]}",labels={"com.arfeen.managed":"true","com.arfeen.database-id":id})
        data_path={"postgresql":"/var/lib/postgresql/data","mysql":"/var/lib/mysql","redis":"/data"}[engine]
        container=docker.containers.run(image, name=f"arfeen-db-{body.name}-{id[:8]}",detach=True,environment=environment,command="redis-server --requirepass " + password if engine=="redis" else None,volumes={volume.name:data_path},labels={"com.arfeen.managed":"true","com.arfeen.database-id":id},network="arfeen_internal")
    except Exception as exc: raise HTTPException(400,f"Could not create database: {exc}")
    username="admin" if engine!="redis" else "default"
    with connection() as db: db.execute("INSERT INTO databases(id,name,engine,container_id,username,password,port,created_at) VALUES(?,?,?,?,?,?,?,?)",(id,body.name,engine,container.id,username,password,port,now()))
    return {"id":id,"name":body.name,"engine":engine,"username":username,"password":password,"port":port,"status":"running","container_id":container.short_id,"connection_host":container.name}

@router.post("/{database_id}/{action}")
def database_action(database_id: str, action: str):
    with connection() as db: row=db.execute("SELECT * FROM databases WHERE id=?",(database_id,)).fetchone()
    if not row: raise HTTPException(404,"Database not found")
    if action not in {"start","stop","restart","delete"}: raise HTTPException(404,"Unsupported action")
    try:
        container=client().containers.get(row["container_id"])
        if action=="delete":
            container.remove(force=True)
            with connection() as db: db.execute("DELETE FROM databases WHERE id=?",(database_id,))
            return {"ok":True}
        getattr(container,action)()
        return {"ok":True,"status":action}
    except Exception as exc: raise HTTPException(400,str(exc))

@router.get("/{database_id}/logs")
def database_logs(database_id: str):
    with connection() as db: row=db.execute("SELECT container_id FROM databases WHERE id=?",(database_id,)).fetchone()
    if not row: raise HTTPException(404,"Database not found")
    try: return {"logs":client().containers.get(row["container_id"]).logs(tail=300,timestamps=True).decode("utf-8",errors="replace")}
    except Exception as exc: raise HTTPException(400,str(exc))
