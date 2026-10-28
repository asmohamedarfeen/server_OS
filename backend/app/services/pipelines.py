"""App-linked pipeline configuration, isolated image tests, and durable poll cursors."""
import json
import sqlite3
import re
import threading
import urllib.parse
import urllib.request
import uuid
from fastapi import HTTPException
from ..core.db import connection
from . import deployment_jobs as jobs

_stop = threading.Event()
_thread = None


def activity(action, resource_id, name, status='success', correlation_id=None):
    try:
        from .control import record_activity
        record_activity(action, resource_id, name, status, correlation_id=correlation_id)
    except (ImportError, RuntimeError, sqlite3.Error):
        pass


def initialize():
    jobs.initialize()
    with connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS pipelines(id TEXT PRIMARY KEY,name TEXT NOT NULL,app_id TEXT NOT NULL UNIQUE,enabled INTEGER NOT NULL DEFAULT 1,test_command TEXT NOT NULL DEFAULT '',test_timeout INTEGER NOT NULL DEFAULT 300,poll_enabled INTEGER NOT NULL DEFAULT 0,last_commit TEXT,last_poll_at TEXT,poll_error TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pipeline_runs(id TEXT PRIMARY KEY,pipeline_id TEXT NOT NULL,job_id TEXT NOT NULL UNIQUE,app_id TEXT NOT NULL,trigger TEXT NOT NULL,commit_sha TEXT,image TEXT);
        CREATE TABLE IF NOT EXISTS app_readiness(app_id TEXT PRIMARY KEY,path TEXT NOT NULL DEFAULT '',expected_status INTEGER NOT NULL DEFAULT 200,timeout INTEGER NOT NULL DEFAULT 90);
        ''')


def application(app_id):
    with connection() as db: row=db.execute('SELECT * FROM applications WHERE id=?',(app_id,)).fetchone()
    if not row: raise HTTPException(404,'Application not found')
    return dict(row)


def definitions():
    with connection() as db:
        rows=db.execute('SELECT p.*,a.name AS app_name,a.source,a.source_type,a.source_ref FROM pipelines p LEFT JOIN applications a ON a.id=p.app_id ORDER BY p.created_at DESC').fetchall()
    result=[]
    for row in rows:
        value=dict(row)
        for key in ('enabled','poll_enabled'): value[key]=bool(value[key])
        result.append(value)
    return result


def get(pipeline_id):
    result=next((x for x in definitions() if x['id']==pipeline_id),None)
    if result is None: raise HTTPException(404,'Pipeline not found')
    return result


def validate(body, current=None):
    allowed={'name','app_id','enabled','test_command','test_timeout','poll_enabled'}
    if not isinstance(body,dict) or set(body)-allowed: raise HTTPException(422,'Unsupported pipeline fields')
    value={k:(current or {}).get(k,v) for k,v in {'name':'','app_id':'','enabled':True,'test_command':'','test_timeout':300,'poll_enabled':False}.items()}
    value.update(body)
    if current and value['app_id']!=current['app_id']: raise HTTPException(422,'Pipeline application cannot be changed')
    if not isinstance(value['name'],str) or not 1<=len(value['name'].strip())<=120: raise HTTPException(422,'Pipeline name must contain 1–120 characters')
    if not isinstance(value['test_command'],str) or len(value['test_command'])>4096 or '\x00' in value['test_command']: raise HTTPException(422,'Invalid test command')
    if type(value['test_timeout']) is not int or not 1<=value['test_timeout']<=3600: raise HTTPException(422,'Test timeout must be 1–3600 seconds')
    if any(type(value[k]) is not bool for k in ('enabled','poll_enabled')): raise HTTPException(422,'Enabled and polling must be booleans')
    app=application(value['app_id'])
    if value['poll_enabled'] and app['source_type'] not in ('github','github-private'): raise HTTPException(422,'Polling requires a GitHub source')
    value['name']=value['name'].strip()
    return value


def create(body):
    value=validate(body);identifier=str(uuid.uuid4());stamp=jobs.now()
    with connection() as db:
        if db.execute('SELECT id FROM pipelines WHERE app_id=?',(value['app_id'],)).fetchone(): raise HTTPException(409,'Application already has a pipeline')
        db.execute('INSERT INTO pipelines(id,name,app_id,enabled,test_command,test_timeout,poll_enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(identifier,value['name'],value['app_id'],value['enabled'],value['test_command'],value['test_timeout'],value['poll_enabled'],stamp,stamp))
    activity('pipeline.create',identifier,value['name'])
    return get(identifier)


def update(identifier,body):
    value=validate(body,get(identifier))
    with connection() as db: db.execute('UPDATE pipelines SET name=?,enabled=?,test_command=?,test_timeout=?,poll_enabled=?,updated_at=? WHERE id=?',(value['name'],value['enabled'],value['test_command'],value['test_timeout'],value['poll_enabled'],jobs.now(),identifier))
    activity('pipeline.configure',identifier,value['name'])
    return get(identifier)


def queue(identifier, trigger='manual', commit=None, directory=None):
    from ..api import applications
    import asyncio,shutil
    from fastapi import UploadFile
    pipeline=get(identifier);app=application(pipeline['app_id'])
    if not pipeline['enabled']: raise HTTPException(409,'Pipeline is disabled')
    if directory is None and app['source_type'] not in ('github','github-private'): raise HTTPException(409,'Upload a ZIP to run this pipeline')
    token=applications.github_token() if app['source_type']=='github-private' else None
    if app['source_type']=='github-private' and not token: raise HTTPException(409,'Reconnect GitHub in Settings')
    job=jobs.create_job(app['name'],'app:'+app['name'],app['source'],app['source_ref'],app_id=app['id'])
    run_id=str(uuid.uuid4())
    with connection() as db: db.execute('INSERT INTO pipeline_runs(id,pipeline_id,job_id,app_id,trigger,commit_sha) VALUES(?,?,?,?,?,?)',(run_id,identifier,job['id'],app['id'],trigger,commit))
    def work():
        if directory is None: return applications.redeploy_github(app['id'])
        with (directory/'source.zip').open('rb') as source: return asyncio.run(applications.redeploy_zip(app['id'],UploadFile(file=source,filename='source.zip')))
    cleanup=(lambda:shutil.rmtree(directory,ignore_errors=True)) if directory else None
    jobs.submit_job(job,work,list(json.loads(app['env_json'] or '{}').values())+[token],cleanup)
    activity('pipeline.run',identifier,pipeline['name'],'queued',run_id)
    return get_run(run_id)


def runs(identifier):
    get(identifier)
    with connection() as db: ids=[r['id'] for r in db.execute('SELECT r.id FROM pipeline_runs r JOIN deployment_jobs j ON j.id=r.job_id WHERE r.pipeline_id=? ORDER BY j.created_at DESC LIMIT 100',(identifier,))]
    return [get_run(i,include_logs=False) for i in ids]


def get_run(identifier,stage=None,include_logs=True):
    with connection() as db: row=db.execute('SELECT * FROM pipeline_runs WHERE id=?',(identifier,)).fetchone()
    if not row: raise HTTPException(404,'Pipeline run not found')
    result=jobs.get_job(row['job_id']);result.update(dict(row));result['commit']=result.pop('commit_sha');result['cancel_requested']=bool(result.get('cancel_requested'))
    if result.get('result'): result['image']=result['result'].get('image') or result['image']
    with connection() as db:
        records=[dict(r) for r in db.execute('SELECT name,status,started_at,finished_at,duration_seconds,exit_code FROM deployment_job_stages WHERE job_id=? ORDER BY rowid',(row['job_id'],))]
        result['stages']=records
        if include_logs:
            sql='SELECT id,created_at,stage,level,message FROM deployment_job_logs WHERE job_id=?';args=[row['job_id']]
            if stage: sql+=' AND stage=?';args.append(stage)
            result['logs']=[dict(r) for r in db.execute(sql+' ORDER BY id DESC LIMIT 1000',args)][::-1]
    return result


def cancel(identifier):
    run=get_run(identifier)
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        job=db.execute('SELECT status,stage FROM deployment_jobs WHERE id=?',(run['job_id'],)).fetchone()
        if job['status'] in ('queued','running'):
            if job['stage'] in ('deploy','verify','complete'):
                raise HTTPException(409,'Deployment has reached replacement; cancellation is no longer safe')
            db.execute('UPDATE deployment_jobs SET cancel_requested=1 WHERE id=?',(run['job_id'],))
    return get_run(identifier)


def test_image(engine,image,command,timeout):
    """Run unprivileged, network-isolated tests before touching the running app."""
    jobs.stage('test','Running image tests')
    container=None
    try:
        container=engine.containers.run(image,command=['/bin/sh','-lc',command],entrypoint=[],detach=True,network_mode='none',mem_limit='512m',nano_cpus=1000000000,pids_limit=256,cap_drop=['ALL'],security_opt=['no-new-privileges:true'],labels={'com.arfeen.pipeline-test':'true'},log_config={'type':'local','config':{'max-size':'8m','max-file':'1'}})
        try: status=container.wait(timeout=timeout)['StatusCode']
        except Exception as exc: raise HTTPException(400,f'Image tests timed out or could not complete within {timeout} seconds') from exc
        jobs.log(container.logs(tail=2000).decode('utf-8',errors='replace'))
        if jobs.output():
            with connection() as db: db.execute("UPDATE deployment_job_stages SET exit_code=? WHERE job_id=? AND name='test'",(status,jobs.output().id))
        if status!=0: raise HTTPException(400,f'Image tests failed with exit code {status}')
    finally:
        if container is not None: container.remove(force=True)


def before_deploy(engine,image,image_tag,app_id=None):
    row=None
    with connection() as db:
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pipeline_runs'").fetchone()
        if exists and jobs.output():
            row=db.execute('SELECT p.test_command,p.test_timeout,r.id FROM pipeline_runs r JOIN pipelines p ON p.id=r.pipeline_id WHERE r.job_id=?',(jobs.output().id,)).fetchone()
            if row: db.execute('UPDATE pipeline_runs SET image=? WHERE id=?',(image_tag,row['id']))
        if exists and row is None and app_id:
            row=db.execute('SELECT test_command,test_timeout FROM pipelines WHERE app_id=? AND enabled=1',(app_id,)).fetchone()
    jobs.check_cancelled()
    if row and row['test_command'].strip(): test_image(engine,image.id,row['test_command'],row['test_timeout'])
    elif jobs.output():
        jobs.stage('test','No test command configured; skipped')
        jobs.finish_stage('skipped')
    jobs.check_cancelled()


def capture_commit(root):
    if not jobs.output(): return
    import subprocess
    result=subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,timeout=10)
    sha=result.stdout.strip()
    if result.returncode==0 and re.fullmatch('[a-f0-9]{40,64}',sha):
        with connection() as db:
            db.execute('UPDATE pipeline_runs SET commit_sha=? WHERE job_id=?',(sha,jobs.output().id))
            # The branch may advance between observation and cloning. Deduplicate
            # the actual source revision that this worker fetched, not the stale poll.
            db.execute("UPDATE pipelines SET last_commit=? WHERE id IN (SELECT pipeline_id FROM pipeline_runs WHERE job_id=? AND trigger='github-poll')",(sha,jobs.output().id))


def remote_commit(pipeline):
    from .github import github_token
    source=pipeline['source'].removesuffix('.git');path=urllib.parse.urlparse(source).path.strip('/')
    ref=urllib.parse.quote(pipeline['source_ref'] or 'HEAD',safe='')
    token=github_token() if pipeline['source_type']=='github-private' else None
    headers={'Accept':'application/vnd.github+json','User-Agent':'Arfeen-Cloud'}
    if token: headers['Authorization']='Bearer '+token
    request=urllib.request.Request(f'https://api.github.com/repos/{path}/commits/{ref}',headers=headers)
    class GitHubRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            parsed=urllib.parse.urlparse(newurl)
            if parsed.scheme!='https' or parsed.hostname!='api.github.com' or parsed.port not in (None,443):
                raise ValueError('Unexpected GitHub redirect')
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    with urllib.request.build_opener(GitHubRedirect()).open(request,timeout=15) as response: value=json.load(response)
    sha=value.get('sha','')
    if not re.fullmatch('[a-f0-9]{40,64}',sha): raise ValueError('Invalid commit response')
    return sha


def poll_once():
    for pipeline in definitions():
        if _stop.is_set(): break
        if not pipeline['enabled'] or not pipeline['poll_enabled']: continue
        error=None
        try:
            sha=remote_commit(pipeline)
            if sha!=pipeline['last_commit']:
                run=queue(pipeline['id'],'github-poll',sha)
                with connection() as db:
                    db.execute('BEGIN IMMEDIATE')
                    actual=db.execute('SELECT commit_sha FROM pipeline_runs WHERE id=?',(run['id'],)).fetchone()
                    # A fast worker may already have reconciled a newer clone SHA.
                    # Serialize this observation with capture_commit so neither can
                    # overwrite the actual revision with the older polled revision.
                    db.execute('UPDATE pipelines SET last_commit=? WHERE id=?',((actual['commit_sha'] if actual else None) or sha,pipeline['id']))
        except HTTPException as exc:
            error='Application deployment already active; polling will retry' if exc.status_code==409 else 'GitHub polling could not queue a deployment'
        except Exception: error='GitHub polling failed; check source and GitHub connection'
        with connection() as db: db.execute('UPDATE pipelines SET last_poll_at=?,poll_error=? WHERE id=?',(jobs.now(),error,pipeline['id']))


def start():
    global _thread
    if _thread and _thread.is_alive(): return
    _stop.clear()
    def work():
        while not _stop.wait(60):
            try: poll_once()
            except Exception: pass
    _thread=threading.Thread(target=work,name='pipeline-poll',daemon=True);_thread.start()


def stop():
    _stop.set()
    if _thread: _thread.join(timeout=16)



def readiness_config(app_id):
    with connection() as db:
        exists=db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_readiness'").fetchone()
        row=db.execute('SELECT path,expected_status,timeout FROM app_readiness WHERE app_id=?',(app_id,)).fetchone() if exists else None
    return dict(row) if row else {'path':'','expected_status':200,'timeout':90}


def attach_job(app_id):
    """Existing deployment entry points share configured pipeline tests and history."""
    if not jobs.output(): return
    with connection() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pipelines'").fetchone(): return
        pipeline=db.execute('SELECT id FROM pipelines WHERE app_id=? AND enabled=1',(app_id,)).fetchone()
        if pipeline:
            db.execute("INSERT OR IGNORE INTO pipeline_runs(id,pipeline_id,job_id,app_id,trigger) VALUES(?,?,?,?,'deployment')",(str(uuid.uuid4()),pipeline['id'],jobs.output().id,app_id))
