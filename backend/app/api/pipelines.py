from fastapi import APIRouter,Depends,File,UploadFile
from ..core.auth import get_current_user
from ..services import pipelines as service
from .deployment_jobs import stage_zip
import shutil
router=APIRouter(prefix='/api/pipelines',tags=['pipelines'],dependencies=[Depends(get_current_user)])
@router.get('')
def list_pipelines(): return service.definitions()
@router.post('',status_code=201)
def create(body:dict): return service.create(body)
@router.get('/runs/{run_id}')
def details(run_id:str,stage:str|None=None): return service.get_run(run_id,stage)
@router.post('/runs/{run_id}/cancel')
def cancel(run_id:str): return service.cancel(run_id)
@router.get('/{pipeline_id}')
def get(pipeline_id:str): return service.get(pipeline_id)
@router.patch('/{pipeline_id}')
def update(pipeline_id:str,body:dict): return service.update(pipeline_id,body)
@router.post('/{pipeline_id}/run',status_code=202)
def run(pipeline_id:str): return service.queue(pipeline_id)
@router.post('/{pipeline_id}/run-zip',status_code=202)
async def run_zip(pipeline_id:str,file:UploadFile=File(...)):
 service.get(pipeline_id)
 directory=await stage_zip(file)
 try: return service.queue(pipeline_id,directory=directory)
 except Exception:
  shutil.rmtree(directory,ignore_errors=True);raise
@router.get('/{pipeline_id}/runs')
def runs(pipeline_id:str): return service.runs(pipeline_id)
