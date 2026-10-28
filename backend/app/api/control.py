from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from ..core.auth import get_current_user
from ..services import control

router=APIRouter(prefix='/api/control',tags=['server control'],dependencies=[Depends(get_current_user)])

class Confirmation(BaseModel):
    hostname: str = Field(min_length=1,max_length=255)
    confirm_impact: bool = False

@router.get('/overview')
def overview(): return control.overview()

@router.get('/disks')
def disks(): return control.host.disks()

@router.get('/network')
def network(): return control.host.network()

@router.get('/processes')
def processes(): return control.host.processes()

@router.get('/services')
def services(): return control.host.services()

@router.get('/activity')
def activity(resource_id: str|None=None,limit: int=Query(100,ge=1,le=500),before: int|None=Query(None,ge=1)):
    return control.activity(resource_id,limit,before)

@router.get('/metrics')
def metrics(resource_id: str='server',limit: int=Query(1440,ge=1,le=8640)):
    return control.metrics(resource_id,limit)

@router.get('/operations')
def operations(): return control.operations()

@router.get('/operations/{operation_id}')
def operation(operation_id: str): return control.operation(operation_id)

@router.post('/services/{name}/restart',status_code=202)
def restart(name: str,body: Confirmation,actor: str=Depends(get_current_user)):
    return control.request_operation('restart',name,body.hostname,body.confirm_impact,actor)

@router.post('/reboot',status_code=202)
def reboot(body: Confirmation,actor: str=Depends(get_current_user)):
    return control.request_operation('reboot',None,body.hostname,body.confirm_impact,actor)
