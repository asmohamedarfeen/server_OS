import json, os,sys,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
_runtime=tempfile.TemporaryDirectory()
for key,name in [('DATA_DIR','data'),('WORKSPACE_DIR','workspace'),('STORAGE_DIR','storage')]:os.environ.setdefault(key,str(Path(_runtime.name)/name))
from app.services import application_routing as routing

class RoutingTests(unittest.TestCase):
 def setUp(self):
  self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
  self.patch=patch.object(routing,'ROUTES_DIR',Path(self.directory.name));self.patch.start();self.addCleanup(self.patch.stop)
  self.probe_patch=patch.object(routing,'probe_target');self.probe=self.probe_patch.start();self.addCleanup(self.probe_patch.stop)
  self.container=MagicMock();self.container.id='candidate';self.container.attrs={'NetworkSettings':{'Networks':{'arfeen_proxy':{'IPAddress':'172.20.0.7'}}}}
 def test_switch_publishes_atomic_dynamic_route_and_waits_for_same_candidate(self):
  with patch.object(routing,'wait_applied') as wait:routing.switch('app-id','app.example.com',self.container,3000)
  value=json.loads(routing.route_path('app-id').read_text());router=next(iter(value['http']['routers'].values()))
  self.assertEqual(router['priority'],1000);self.assertEqual(router['rule'],'Host(`app.example.com`)')
  self.assertIn('http://172.20.0.7:3000',str(value));self.assertIn('X-Arfeen-Deployment',str(value));self.assertIn('candidate',str(value))
  wait.assert_called_once();self.assertEqual(wait.call_args.args[:2],('app.example.com','candidate'))
  self.assertEqual(len(list(Path(self.directory.name).iterdir())),1)
 def test_failed_route_ack_restores_previous_route_exactly(self):
  old=b'{"previous":"old-route"}';routing.route_path('app-id').write_bytes(old)
  with patch.object(routing,'wait_applied',side_effect=routing.RouteError('timeout')):
   with self.assertRaises(routing.RouteError):routing.switch('app-id','app.example.com',self.container,3000)
  self.assertEqual(routing.route_path('app-id').read_bytes(),old)
 def test_failed_first_route_ack_removes_new_route_to_restore_legacy_labels(self):
  with patch.object(routing,'wait_applied',side_effect=routing.RouteError('timeout')):
   with self.assertRaises(routing.RouteError):routing.switch('app-id','app.example.com',self.container,3000)
  self.assertFalse(routing.route_path('app-id').exists())
 def test_route_path_rejects_traversal_and_domain_injection(self):
  for identifier in ('../x','/etc/passwd','a/b',''):
   with self.assertRaises(routing.RouteError):routing.route_path(identifier)
  with self.assertRaises(routing.RouteError):routing.switch('app','app.example.com`) || Path(`/`)',self.container,3000)
 def test_ack_accepts_expected_header_on_http_error_without_following_redirects(self):
  opener=MagicMock();opener.open.side_effect=urllib.error.HTTPError('http://traefik',404,'Not Found',{'X-Arfeen-Deployment':'candidate'},None)
  with patch.object(routing.urllib.request,'build_opener',return_value=opener):routing.wait_applied('app.example.com','candidate',{'path':'','timeout':1})
  request=opener.open.call_args.args[0];self.assertEqual(request.get_header('Host'),'app.example.com');self.assertEqual(request.full_url,'http://traefik:80/')
 def test_regeneration_tolerates_unavailable_docker(self):
  with patch.object(routing,'client',side_effect=RuntimeError('not available')):result=routing.regenerate()
  self.assertFalse(result['available'])

 def test_regenerate_reconstructs_current_container_target(self):
  from app.core.db import init_db,connection
  init_db()
  with connection() as db:
   db.execute("INSERT OR REPLACE INTO applications(id,name,source,framework,port,status,created_at,container_id,domain) VALUES('routing-regen-app','route-regen','ZIP upload','Node',3000,'running','2020','candidate','app.example.com')")
  try:
   with patch.object(routing,'client') as engine:
    engine.return_value.containers.get.return_value=self.container
    result=routing.regenerate()
   self.assertTrue(result['available']);self.assertGreaterEqual(result['restored'],1)
   self.assertIn('172.20.0.7:3000',routing.route_path('routing-regen-app').read_text())
  finally:
   with connection() as db:db.execute("DELETE FROM applications WHERE id='routing-regen-app'")

 def test_proxy_502_header_does_not_acknowledge_and_preserves_serving_app(self):
  from app.api import applications
  opener=MagicMock();opener.open.side_effect=urllib.error.HTTPError('http://traefik',502,'Bad Gateway',{'X-Arfeen-Deployment':'candidate'},None)
  engine=MagicMock();old=engine.containers.get.return_value;old.status='running';old.attrs={'Config':{'Labels':{}}};engine.containers.create.return_value=self.container
  previous=b'{"previous":"old-route"}';routing.route_path('app-id').write_bytes(previous)
  row={'id':'app-id','name':'sample','container_id':'old','domain':'app.example.com','host_port':None}
  published=[]
  with patch.object(applications,'verify_container'),patch.object(routing.urllib.request,'build_opener',return_value=opener),patch.object(routing.time,'monotonic',side_effect=[0,1,16]):
   with self.assertRaises(applications.HTTPException):
    with applications.replacement_runtime(row,'image',{},3000,engine):published.append(True)
  self.assertEqual(published,[])
  self.assertEqual(routing.route_path('app-id').read_bytes(),previous)
  old.stop.assert_not_called();old.remove.assert_not_called();old.start.assert_not_called();self.container.remove.assert_called_once_with(force=True)

 def test_proxy_502_retries_until_non_5xx_candidate_response(self):
  opener=MagicMock();response=MagicMock();response.status=200;response.headers={'X-Arfeen-Deployment':'candidate'}
  opener.open.side_effect=[urllib.error.HTTPError('http://traefik',502,'Bad Gateway',{'X-Arfeen-Deployment':'candidate'},None),response]
  with patch.object(routing.urllib.request,'build_opener',return_value=opener),patch.object(routing.time,'sleep'):
   routing.wait_applied('app.example.com','candidate')
  self.assertEqual(opener.open.call_count,2)

 def test_configured_proxy_readiness_requires_exact_status_and_header(self):
  opener=MagicMock();wrong=MagicMock();wrong.status=204;wrong.headers={'X-Arfeen-Deployment':'candidate'}
  correct=MagicMock();correct.status=201;correct.headers={'X-Arfeen-Deployment':'candidate'}
  opener.open.side_effect=[wrong,correct]
  with patch.object(routing.urllib.request,'build_opener',return_value=opener),patch.object(routing.time,'sleep'):
   routing.wait_applied('app.example.com','candidate',{'path':'/ready','expected_status':201})
  self.assertEqual(opener.open.call_count,2)

 def test_explicitly_configured_503_status_can_acknowledge_proxy_readiness(self):
  opener=MagicMock();opener.open.side_effect=urllib.error.HTTPError('http://traefik',503,'App-specific maintenance response',{'X-Arfeen-Deployment':'candidate'},None)
  with patch.object(routing.urllib.request,'build_opener',return_value=opener):routing.wait_applied('app.example.com','candidate',{'path':'/maintenance','expected_status':503})
  self.assertEqual(opener.open.call_count,1)


 def test_internal_only_listener_cannot_publish_route_or_retire_old(self):
  from app.api import applications
  engine=MagicMock();old=engine.containers.get.return_value;old.status='running';old.attrs={'Config':{'Labels':{}}};engine.containers.create.return_value=self.container
  previous=b'{"previous":"old-route"}';routing.route_path('app-id').write_bytes(previous)
  row={'id':'app-id','name':'sample','container_id':'old','domain':'app.example.com','host_port':None}
  self.probe.side_effect=routing.RouteError('Candidate is unreachable on its proxy-network address')
  with patch.object(applications,'verify_container'),patch.object(routing,'wait_applied') as ack:
   with self.assertRaises(applications.HTTPException):
    with applications.replacement_runtime(row,'image',{},3000,engine):pass
  self.assertEqual(routing.route_path('app-id').read_bytes(),previous);ack.assert_not_called()
  self.assertEqual(self.probe.call_args.args[:2],('http://172.20.0.7:3000','app.example.com'))
  old.stop.assert_not_called();old.remove.assert_not_called();self.container.remove.assert_called_once_with(force=True)

 def test_exact_proxy_endpoint_probe_rejects_default_503(self):
  self.probe_patch.stop()
  opener=MagicMock();opener.open.side_effect=urllib.error.HTTPError('http://172.20.0.7',503,'Unavailable',{},None)
  with patch.object(routing.urllib.request,'build_opener',return_value=opener),patch.object(routing.time,'monotonic',side_effect=[0,1,16]):
   with self.assertRaises(routing.RouteError):routing.probe_target('http://172.20.0.7:3000','app.example.com')

 def test_exact_proxy_endpoint_probe_allows_explicit_app_503_and_host_header(self):
  self.probe_patch.stop()
  opener=MagicMock();opener.open.side_effect=urllib.error.HTTPError('http://172.20.0.7',503,'Maintenance',{},None)
  with patch.object(routing.urllib.request,'build_opener',return_value=opener):routing.probe_target('http://172.20.0.7:3000','app.example.com',{'path':'/maintenance','expected_status':503})
  request=opener.open.call_args.args[0];self.assertEqual(request.full_url,'http://172.20.0.7:3000/maintenance');self.assertEqual(request.get_header('Host'),'app.example.com')
