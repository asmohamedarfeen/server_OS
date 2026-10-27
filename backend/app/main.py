from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.db import init_db
from .api import auth, monitoring, containers, files, applications, databases, terminal, settings, resources, github

init_db()
app=FastAPI(title="Arfeen Cloud API",version="0.1.0",docs_url="/api/docs",redoc_url=None)
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:3000","http://127.0.0.1:3000"],allow_credentials=True,allow_methods=["GET","POST","PUT","PATCH","DELETE"],allow_headers=["Content-Type","X-Setup-Token"])
for router in (auth.router,monitoring.router,containers.router,files.router,applications.router,databases.router,settings.router,resources.router): app.include_router(router)
app.include_router(terminal.router)
app.include_router(github.router)

@app.get("/api/health")
def health(): return {"status":"ok","service":"arfeen-cloud-api"}
