from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import logging
from .core.db import init_db
from .api import auth, monitoring, containers, files, applications, databases, terminal, settings, resources, github
from .api import deployment_jobs
from .api import control as control_api, pipelines as pipelines_api
from .services import control, pipelines, application_routing
from .services.audit import audit_mutation
from .services.deployment_jobs import recover_interrupted_jobs

init_db()
control.initialize()
pipelines.initialize()
recover_interrupted_jobs()

@asynccontextmanager
async def lifespan(app):
    routing = await asyncio.to_thread(application_routing.regenerate)
    if not routing.get('available') or routing.get('failed'):
        logging.getLogger(__name__).warning('Some application routes could not be restored; check Docker and application state')
    control.start()
    pipelines.start()
    try:
        yield
    finally:
        pipelines.stop()
        control.stop()

app=FastAPI(title="Arfeen Cloud API",version="0.2.0",docs_url="/api/docs",redoc_url=None,lifespan=lifespan)
app.middleware('http')(audit_mutation)
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:3000","http://127.0.0.1:3000"],allow_credentials=True,allow_methods=["GET","POST","PUT","PATCH","DELETE"],allow_headers=["Content-Type","X-Setup-Token"])
for router in (auth.router,monitoring.router,containers.router,files.router,applications.router,databases.router,settings.router,resources.router): app.include_router(router)
app.include_router(terminal.router)
app.include_router(github.router)
app.include_router(deployment_jobs.router)
app.include_router(control_api.router)
app.include_router(pipelines_api.router)

@app.get("/api/health")
def health(): return {"status":"ok","service":"arfeen-cloud-api"}
