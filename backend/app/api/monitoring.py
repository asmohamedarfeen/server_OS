from fastapi import APIRouter, Depends
from ..core.auth import get_current_user
from ..services.system import server_metrics
from ..services.docker_engine import client

router = APIRouter(prefix="/api", tags=["monitoring"], dependencies=[Depends(get_current_user)])

@router.get("/server")
def server():
    data = server_metrics()
    try:
        engine = client().version()
        data["docker"] = {"available": True, "version": engine.get("Version"), "api_version": engine.get("ApiVersion"), "containers": engine.get("Containers", 0)}
    except Exception as exc:
        data["docker"] = {"available": False, "error": str(exc)}
    return data

@router.get("/processes")
def processes():
    items = []
    for proc in __import__("psutil").process_iter(["pid", "name", "username", "cpu_percent", "memory_percent", "status"]):
        try:
            items.append(proc.info)
        except Exception:
            pass
    return sorted(items, key=lambda p: p.get("memory_percent") or 0, reverse=True)[:50]
