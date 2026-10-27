from fastapi import APIRouter, Depends, HTTPException
from ..core.auth import get_current_user
from ..services.docker_engine import client

router=APIRouter(prefix="/api/docker",tags=["docker resources"],dependencies=[Depends(get_current_user)])

@router.get("/images")
def images():
    try:
        return [{"id":i.short_id,"full_id":i.id,"tags":i.tags,"size":i.attrs.get("Size",0),"created":i.attrs.get("Created"),"managed":(i.labels or {}).get("com.arfeen.managed")=="true"} for i in client().images.list()]
    except Exception as exc: raise HTTPException(503,str(exc))

@router.delete("/images/{image_id}")
def delete_image(image_id: str):
    try: client().images.remove(image_id,force=False); return {"ok":True}
    except Exception as exc: raise HTTPException(400,str(exc))

@router.get("/volumes")
def volumes():
    try: return [{"name":v.name,"driver":v.attrs.get("Driver"),"mountpoint":v.attrs.get("Mountpoint"),"created":v.attrs.get("CreatedAt"),"managed":(v.attrs.get("Labels") or {}).get("com.arfeen.managed")=="true","system":(v.attrs.get("Labels") or {}).get("com.arfeen.system")=="true"} for v in client().volumes.list()]
    except Exception as exc: raise HTTPException(503,str(exc))

@router.delete("/volumes/{name}")
def delete_volume(name: str):
    try:
        volume=client().volumes.get(name)
        if (volume.attrs.get("Labels") or {}).get("com.arfeen.system")=="true": raise HTTPException(409,"Platform data volumes cannot be removed here")
        volume.remove(force=False); return {"ok":True}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(400,str(exc))

@router.get("/networks")
def networks():
    try: return [{"id":n.short_id,"name":n.name,"driver":n.attrs.get("Driver"),"scope":n.attrs.get("Scope"),"containers":len(n.attrs.get("Containers") or {}),"managed":(n.attrs.get("Labels") or {}).get("com.arfeen.managed")=="true"} for n in client().networks.list()]
    except Exception as exc: raise HTTPException(503,str(exc))
