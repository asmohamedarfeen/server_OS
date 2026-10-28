import os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
_runtime=tempfile.TemporaryDirectory()
for k,v in [('DATA_DIR','data'),('WORKSPACE_DIR','workspace'),('STORAGE_DIR','storage')]: os.environ.setdefault(k,str(Path(_runtime.name)/v))
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from app.core.db import init_db,connection
from app.core.auth import get_current_user
from app.services import deployment_jobs as jobs
from app.services import pipelines
from app.api import pipelines as api,applications

class PipelineTests(unittest.TestCase):
 def setUp(self):
  init_db();pipelines.initialize()
  with connection() as db:
   for table in ['pipeline_runs','pipelines','deployment_job_stages','deployment_jobs','deployment_job_logs','deployments','app_readiness','applications']: db.execute('DELETE FROM '+table)
   db.execute("INSERT INTO applications(id,name,source,framework,port,status,created_at,container_id,image) VALUES('a','sample','https://github.com/org/repo.git','Node',3000,'running',?,'old-container','old-image')",(jobs.now(),))
  app=FastAPI();app.include_router(api.router);app.include_router(applications.router);self.app=app;self.client=TestClient(app)
 def auth(self): self.app.dependency_overrides[get_current_user]=lambda:'admin'
 def definition(self,**extra): return pipelines.create({'name':'Build sample','app_id':'a',**extra})
 def test_auth_and_validation(self):
  self.assertEqual(self.client.get('/api/pipelines').status_code,401);self.auth()
  self.assertEqual(self.client.post('/api/pipelines',json={'name':'X','app_id':'missing'}).status_code,404)
  self.assertEqual(self.client.post('/api/pipelines',json={'name':'X','app_id':'a','test_timeout':0}).status_code,422)
 def test_run_stage_timing_and_cancellation(self):
  p=self.definition()
  with patch.object(jobs,'submit_job'):
   run=pipelines.queue(p['id'])
  pipelines.cancel(run['id']);jobs.run_job(run['job_id'],lambda:jobs.stage('build','build'))
  result=pipelines.get_run(run['id']);self.assertEqual(result['status'],'cancelled');self.assertTrue(result['finished_at'])
 def test_stage_records_and_redaction(self):
  p=self.definition()
  with patch.object(jobs,'submit_job'):run=pipelines.queue(p['id'])
  def work():
   jobs.stage('build','Building');jobs.log('secret-password');jobs.stage('test','Testing');return {'id':'a','image':'artifact'}
  jobs.run_job(run['job_id'],work,['secret-password'])
  run=pipelines.get_run(run['id']);self.assertEqual(run['image'],'artifact');self.assertEqual(run['status'],'success')
  self.assertTrue(all(x['finished_at'] for x in run['stages']));self.assertNotIn('secret-password',str(run))
 def test_test_failure_removes_test_container(self):
  engine=MagicMock();container=engine.containers.run.return_value;container.wait.return_value={'StatusCode':2};container.logs.return_value=b'test failed'
  with self.assertRaises(HTTPException):pipelines.test_image(engine,'new-image','npm test',12)
  container.remove.assert_called_once_with(force=True)
  self.assertEqual(engine.containers.run.call_args.kwargs['network_mode'],'none')
 def test_readiness_rejects_external_or_traversal_paths(self):
  self.auth()
  for value in ['https://example.com','//example.com','/../admin','/health?x=1','/%2e%2e/admin']:
   self.assertEqual(self.client.patch('/api/apps/a/readiness',json={'path':value}).status_code,422,value)
  self.assertEqual(self.client.patch('/api/apps/a/readiness',json={'path':'/health','expected_status':204,'timeout':10}).status_code,200)
 def test_poll_duplicate_commit_is_not_queued_twice(self):
  p=self.definition(poll_enabled=True)
  with patch.object(pipelines,'remote_commit',return_value='a'*40),patch.object(jobs,'submit_job') as submit:
   pipelines.poll_once();pipelines.poll_once()
  self.assertEqual(submit.call_count,1)

 def test_existing_redeploy_jobs_use_application_pipeline_tests(self):
  self.definition(test_command='npm test')
  job=jobs.create_job('sample','app:sample','ZIP upload')
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'package.json').write_text('{"scripts":{"start":"node app.js"}}')
   engine=MagicMock();engine.api.build.return_value=iter([]);engine.images.get.return_value.id='new-image'
   with patch.object(applications,'client',return_value=engine),patch.object(pipelines,'test_image',side_effect=HTTPException(400,'tests failed')):
    jobs.run_job(job['id'],lambda:applications.redeploy_tree('a',root,'ZIP upload'))
  self.assertEqual(jobs.get_job(job['id'])['status'],'failed')
  engine.containers.get.assert_not_called()
  with connection() as db: self.assertEqual(db.execute("SELECT container_id FROM applications WHERE id='a'").fetchone()[0],'old-container')

 def test_metrics_are_real_container_stats(self):
  self.auth();container=MagicMock();container.status='running';container.stats.return_value={'cpu_stats':{'cpu_usage':{'total_usage':200},'system_cpu_usage':400,'online_cpus':2},'precpu_stats':{'cpu_usage':{'total_usage':100},'system_cpu_usage':200},'memory_stats':{'usage':1000,'limit':2000,'stats':{'inactive_file':100}},'networks':{'eth0':{'rx_bytes':12,'tx_bytes':24}}}
  with patch.object(applications,'client') as docker:
   docker.return_value.containers.get.return_value=container
   data=self.client.get('/api/apps/a/metrics').json()
  self.assertTrue(data['available']);self.assertEqual(data['cpu_percent'],100);self.assertEqual(data['memory_bytes'],900);self.assertEqual(data['network_tx_bytes'],24)

 def test_test_timeout_cleans_up_container(self):
  engine=MagicMock();engine.containers.run.return_value.wait.side_effect=TimeoutError('timeout')
  with self.assertRaises(HTTPException) as error: pipelines.test_image(engine,'image','sleep 99',1)
  self.assertIn('timed out',error.exception.detail);engine.containers.run.return_value.remove.assert_called_once_with(force=True)

 def test_source_rejects_query_and_preserves_single_git_suffix(self):
  self.auth()
  response=self.client.patch('/api/apps/a/source',json={'source':'https://github.com/org/repo.git'})
  self.assertEqual(response.status_code,200);self.assertEqual(response.json()['source'],'https://github.com/org/repo.git')
  self.assertEqual(self.client.patch('/api/apps/a/source',json={'source':'https://github.com/org/repo?token=secret'}).status_code,422)

 def test_running_deployment_cannot_be_cancelled_after_replacement(self):
  p=self.definition()
  with patch.object(jobs,'submit_job'):run=pipelines.queue(p['id'])
  with connection() as db:db.execute("UPDATE deployment_jobs SET stage='deploy',status='running' WHERE id=?",(run['job_id'],))
  with self.assertRaises(HTTPException) as error:pipelines.cancel(run['id'])
  self.assertEqual(error.exception.status_code,409)

 def test_failed_pipeline_job_stays_linked_to_application(self):
  p=self.definition()
  with patch.object(jobs,'submit_job'):run=pipelines.queue(p['id'])
  def fail(): raise RuntimeError('source unavailable')
  with patch.object(pipelines,'activity') as activity:
   jobs.run_job(run['job_id'],fail)
  self.assertEqual(jobs.get_job(run['job_id'])['app_id'],'a')
  self.assertEqual(activity.call_args.args[1],'a')

 def domain_engine(self):
  engine=MagicMock();old=MagicMock();old.status='running';old.attrs={'Config':{'Labels':{'traefik.enable':'true'}}}
  candidate=MagicMock();candidate.id='candidate';candidate.short_id='candidate'
  final=MagicMock();final.id='final';final.short_id='final'
  engine.containers.get.return_value=old;engine.containers.create.side_effect=[candidate,final]
  engine.images.get.return_value.id='new-image';engine.api.build.return_value=iter([]);engine.images.build.return_value=(engine.images.get.return_value,[])
  with connection() as db:db.execute("UPDATE applications SET domain='app.example.com' WHERE id='a'")
  return engine,old,candidate,final

 def test_domain_same_verified_candidate_is_routed_before_old_is_retired(self):
  from app.services import application_routing
  engine,old,candidate,final=self.domain_engine()
  def verify(container,*args):
   self.assertIs(container,candidate);old.stop.assert_not_called();old.remove.assert_not_called()
  def switch(app_id,domain,container,port,readiness):
   self.assertIs(container,candidate);old.stop.assert_not_called();old.remove.assert_not_called()
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'package.json').write_text('{}')
   with patch.object(applications,'client',return_value=engine),patch.object(applications,'verify_container',side_effect=verify) as verification,patch.object(application_routing,'switch',side_effect=switch) as route:
    result=applications.redeploy_tree('a',root,'ZIP upload')
  self.assertEqual(engine.containers.create.call_count,1)
  self.assertEqual(engine.containers.create.call_args.kwargs['labels'].get('traefik.enable'),'false')
  verification.assert_called_once();route.assert_called_once();candidate.remove.assert_not_called()
  old.stop.assert_called_once();old.remove.assert_called_once()
  with connection() as db:self.assertEqual(db.execute("SELECT container_id FROM applications WHERE id='a'").fetchone()[0],'candidate')
  self.assertEqual(result['id'],'a')

 def test_domain_preflight_failure_preserves_old_running_container(self):
  engine,old,candidate,final=self.domain_engine()
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'package.json').write_text('{}')
   with patch.object(applications,'client',return_value=engine),patch.object(applications,'verify_container',side_effect=HTTPException(400,'readiness failed')):
    with self.assertRaises(HTTPException):applications.redeploy_tree('a',root,'ZIP upload')
  old.stop.assert_not_called();old.remove.assert_not_called();old.start.assert_not_called()
  candidate.remove.assert_called_once_with(force=True)

 def test_configuration_and_lifecycle_blocked_by_active_deployment(self):
  self.auth();jobs.create_job('sample','app:sample','ZIP upload',app_id='a')
  with patch.object(applications,'client') as docker:
   for method,path,body in [('post','restart',None),('post','delete',None),('put','environment',{'environment':{}}),('patch','readiness',{'path':'/health'}),('patch','source',{'source_type':'zip'})]:
    response=getattr(self.client,method)('/api/apps/a/'+path,**({'json':body} if body is not None else {}))
    self.assertEqual(response.status_code,409,path)
  docker.assert_not_called()

 def test_cancel_accepted_before_deploy_publication_cannot_enter_replacement(self):
  p=self.definition()
  with patch.object(jobs,'submit_job'):run=pipelines.queue(p['id'])
  with connection() as db:db.execute("UPDATE deployment_jobs SET status='running',stage='build' WHERE id=?",(run['job_id'],))
  token=jobs._current.set(jobs.JobOutput(run['job_id']))
  try:
   with patch.object(jobs,'check_cancelled',side_effect=lambda:pipelines.cancel(run['id'])):
    with self.assertRaises(jobs.JobCancelled):jobs.stage('deploy','Replacing')
  finally:jobs._current.reset(token)
  self.assertNotEqual(jobs.get_job(run['job_id'])['stage'],'deploy')

 def test_poll_cursor_reconciles_actual_cloned_commit(self):
  p=self.definition(poll_enabled=True)
  with patch.object(pipelines,'remote_commit',return_value='a'*40),patch.object(jobs,'submit_job'):
   pipelines.poll_once()
  run=pipelines.runs(p['id'])[0];token=jobs._current.set(jobs.JobOutput(run['job_id']))
  from types import SimpleNamespace
  try:
   with patch('subprocess.run',return_value=SimpleNamespace(stdout='b'*40,returncode=0)):pipelines.capture_commit(Path('/tmp/source'))
  finally:jobs._current.reset(token)
  with connection() as db:db.execute("UPDATE deployment_jobs SET status='success' WHERE id=?",(run['job_id'],))
  with patch.object(pipelines,'remote_commit',return_value='b'*40),patch.object(jobs,'submit_job') as submit:pipelines.poll_once()
  submit.assert_not_called();self.assertEqual(pipelines.get(p['id'])['last_commit'],'b'*40)

 def test_synchronous_redeploy_does_not_bypass_readiness(self):
  container=MagicMock();container.status='running';container.attrs={'State':{}}
  with connection() as db:db.execute("INSERT INTO app_readiness(app_id,path,expected_status,timeout) VALUES('a','/health',200,1)")
  with patch.object(applications,'http_ready',return_value=False) as probe,patch.object(applications.time,'sleep'),patch.object(applications.time,'monotonic',side_effect=[0,2]):
   with self.assertRaises(HTTPException):applications.verify_container(container,'a',3000)
  probe.assert_called_once()

 def test_domain_route_failure_preserves_old_and_removes_candidate(self):
  from app.services import application_routing
  engine,old,candidate,final=self.domain_engine()
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'package.json').write_text('{}')
   with patch.object(applications,'client',return_value=engine),patch.object(applications,'verify_container'),patch.object(application_routing,'switch',side_effect=application_routing.RouteError('not acknowledged')):
    with self.assertRaises(HTTPException):applications.redeploy_tree('a',root,'ZIP upload')
  old.stop.assert_not_called();old.start.assert_not_called();old.remove.assert_not_called()
  candidate.remove.assert_called_once_with(force=True)
  with connection() as db:self.assertEqual(db.execute("SELECT container_id FROM applications WHERE id='a'").fetchone()[0],'old-container')

 def test_queue_cannot_start_during_lifecycle_mutation(self):
  from threading import Event,Thread
  entered=Event();release=Event();finished=Event()
  engine=MagicMock()
  def restart():entered.set();release.wait(2)
  engine.containers.get.return_value.restart.side_effect=restart
  def mutate():
   with patch.object(applications,'client',return_value=engine):applications.app_action('a','restart')
   finished.set()
  thread=Thread(target=mutate);thread.start()
  try:
   self.assertTrue(entered.wait(1))
   with self.assertRaises(HTTPException) as error:jobs.create_job('sample','app:sample','ZIP upload')
   self.assertEqual(error.exception.status_code,409)
  finally:release.set();thread.join(2)
  self.assertTrue(finished.is_set())

 def test_poll_does_not_overwrite_actual_commit_from_fast_worker(self):
  from types import SimpleNamespace
  p=self.definition(poll_enabled=True)
  def work(app_id):pipelines.capture_commit(Path('/tmp/source'));return {'id':app_id}
  def immediate(job,work,secrets,cleanup):jobs.run_job(job['id'],work,secrets,cleanup)
  with patch.object(pipelines,'remote_commit',return_value='a'*40),patch.object(jobs,'submit_job',side_effect=immediate),patch.object(applications,'redeploy_github',side_effect=work),patch('subprocess.run',return_value=SimpleNamespace(stdout='b'*40,returncode=0)):
   pipelines.poll_once()
  self.assertEqual(pipelines.get(p['id'])['last_commit'],'b'*40)

 def test_domain_environment_switches_verified_candidate_without_stale_route(self):
  from app.services import application_routing
  engine,old,candidate,final=self.domain_engine()
  def switch(*args):old.stop.assert_not_called();self.assertIs(args[2],candidate)
  with patch.object(applications,'client',return_value=engine),patch.object(applications,'verify_container') as verify,patch.object(application_routing,'switch',side_effect=switch) as route:
   result=applications.update_environment('a',{'environment':{'MODE':'production'}})
  verify.assert_called_once_with(candidate,'a',3000);route.assert_called_once();old.stop.assert_called_once();old.remove.assert_called_once();candidate.remove.assert_not_called()
  with connection() as db:
   row=db.execute("SELECT container_id,env_json FROM applications WHERE id='a'").fetchone()
  self.assertEqual(row['container_id'],'candidate');self.assertIn('production',row['env_json']);self.assertTrue(result['ok'])

 def test_domain_rollback_routes_actual_verified_candidate(self):
  from app.services import application_routing
  engine,old,candidate,final=self.domain_engine()
  with connection() as db:
   db.execute("INSERT INTO deployments(id,app_id,status,message,created_at,image) VALUES('earlier','a','success','old','2020-01-01','earlier-image')")
   db.execute("INSERT INTO deployments(id,app_id,status,message,created_at,image) VALUES('later','a','success','new','2021-01-01','later-image')")
  def switch(*args):old.stop.assert_not_called();self.assertIs(args[2],candidate)
  with patch.object(applications,'client',return_value=engine),patch.object(applications,'verify_container'),patch.object(application_routing,'switch',side_effect=switch) as route:
   applications.app_action('a','rollback')
  route.assert_called_once();old.remove.assert_called_once();candidate.remove.assert_not_called()
  with connection() as db:self.assertEqual(db.execute("SELECT container_id FROM applications WHERE id='a'").fetchone()[0],'candidate')

 def test_domain_delete_removes_route_and_restores_it_when_delete_fails(self):
  from app.services import application_routing
  engine,old,candidate,final=self.domain_engine()
  with tempfile.TemporaryDirectory() as directory,patch.object(application_routing,'ROUTES_DIR',Path(directory)),patch.object(applications,'client',return_value=engine):
   path=application_routing.route_path('a');path.write_text('{"old":"route"}')
   old.remove.side_effect=RuntimeError('cannot delete')
   with self.assertRaises(HTTPException):applications.app_action('a','delete')
   self.assertTrue(path.exists());old.remove.side_effect=None
   applications.app_action('a','delete');self.assertFalse(path.exists())

 def test_inventory_distinguishes_missing_container_from_unavailable_engine(self):
  from docker.errors import NotFound
  for error,status in [(NotFound('container absent'),'missing'),(RuntimeError('sensitive engine details'),'unknown')]:
   with patch.object(applications,'client',side_effect=error):result=applications.list_apps()
   self.assertEqual(result[0]['status'],status);self.assertEqual(result[0]['health'],'unknown');self.assertNotIn('sensitive engine details',str(result))

 def test_initial_domain_deployment_publishes_verified_current_container(self):
  from app.services import application_routing
  engine=MagicMock();container=engine.containers.run.return_value;container.id='initialcandidate';container.short_id='initial'
  image=MagicMock();image.id='initialimage';engine.images.build.return_value=(image,[])
  def switch(app_id,domain,current,port):
   self.assertIs(current,container)
   with connection() as db:self.assertIsNone(db.execute('SELECT id FROM applications WHERE id=?',(app_id,)).fetchone())
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'package.json').write_text('{}')
   with patch.object(applications,'client',return_value=engine),patch.object(applications,'verify_container') as verify,patch.object(application_routing,'switch',side_effect=switch) as route:
    result=applications.deploy_tree('initial-domain','ZIP upload',root,'initial.example.com')
  self.assertEqual(engine.containers.run.call_args.kwargs['labels']['traefik.enable'],'false')
  verify.assert_called_once_with(container,result['id'],3000);route.assert_called_once();container.remove.assert_not_called()
  with connection() as db:self.assertEqual(db.execute('SELECT container_id FROM applications WHERE id=?',(result['id'],)).fetchone()[0],'initialcandidate')
