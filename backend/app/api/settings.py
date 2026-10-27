from fastapi import APIRouter, Depends
from ..core.auth import get_current_user
from ..services.system import server_metrics

router=APIRouter(prefix="/api/settings",tags=["settings"],dependencies=[Depends(get_current_user)])

@router.get("")
def settings(user: str = Depends(get_current_user)):
    metrics=server_metrics()
    return {"administrator":user,"hostname":metrics["hostname"],"platform":metrics["platform"],"uptime_seconds":metrics["uptime_seconds"],"storage_root":"/data/files","terminal":"enabled","public_access":"Set up HTTPS and a domain before exposing this service to the internet."}
