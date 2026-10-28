from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..core.auth import get_current_user
from ..services.docker_engine import client, serialize

router = APIRouter(prefix="/api/containers", tags=["containers"], dependencies=[Depends(get_current_user)])

def _activity(action, resource_id, resource_name, status, actor):
    from ..services.control import record_activity
    try: record_activity(action, resource_id, resource_name, status, actor=actor)
    except Exception: pass  # Resource mutations remain usable if the audit store is unavailable.

class ContainerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=63, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    image: str = Field(min_length=1, max_length=255)
    ports: dict[str, int] = {}
    environment: dict[str, str] = {}

@router.get("")
def list_containers():
    try:
        return [serialize(c) for c in client().containers.list(all=True)]
    except Exception as exc:
        raise HTTPException(503, str(exc))

@router.post("")
def create_container(body: ContainerCreate, actor: str = Depends(get_current_user)):
    try:
        docker = client()
        result = serialize(docker.containers.run(body.image, name=body.name, detach=True, ports=body.ports or None, environment=body.environment or None, labels={"com.arfeen.managed": "true"}))
        _activity('container.create', result['id'], body.name, 'succeeded', actor)
        return result
    except Exception as exc:
        raise HTTPException(400, str(exc))

@router.post("/{container_id}/{action}")
def container_action(container_id: str, action: str, actor: str = Depends(get_current_user)):
    if action not in {"start", "stop", "restart", "pause", "unpause"}:
        raise HTTPException(404, "Unsupported container action")
    try:
        container = client().containers.get(container_id)
        if (container.labels or {}).get("com.arfeen.system")=="true":
            raise HTTPException(409,"Platform containers cannot be controlled from their own dashboard")
        getattr(container, action)()
        _activity('container.'+action, container_id, container.name, 'succeeded', actor)
        return serialize(container)
    except HTTPException: raise
    except Exception as exc:
        raise HTTPException(400, str(exc))

@router.delete("/{container_id}")
def delete_container(container_id: str, actor: str = Depends(get_current_user)):
    try:
        container=client().containers.get(container_id)
        if (container.labels or {}).get("com.arfeen.system")=="true":
            raise HTTPException(409,"Platform containers cannot be deleted from their own dashboard")
        container.remove(force=True)
        _activity('container.delete', container_id, container.name, 'succeeded', actor)
        return {"ok": True}
    except HTTPException: raise
    except Exception as exc:
        raise HTTPException(400, str(exc))

@router.get("/{container_id}/logs")
def container_logs(container_id: str, tail: int = 200):
    try:
        value = client().containers.get(container_id).logs(tail=max(1, min(tail, 2000)), timestamps=True).decode("utf-8", errors="replace")
        return {"logs": value}
    except Exception as exc:
        raise HTTPException(400, str(exc))
