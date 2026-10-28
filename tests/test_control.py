"""Control APIs use a temporary database and fake host; never mutate the host."""
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
_runtime = tempfile.TemporaryDirectory()
for key, suffix in [('DATA_DIR','data'),('WORKSPACE_DIR','workspace'),('STORAGE_DIR','storage')]:
    os.environ.setdefault(key, str(Path(_runtime.name) / suffix))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.core import db
from app.core.auth import get_current_user
try:
    from app.services import control
    from app.api import control as control_api
except ImportError:
    control = control_api = None

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(control, 'control service must exist')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_patch = patch.object(db, 'APP_DB', Path(self.temp.name) / 'test.db')
        self.db_patch.start(); self.addCleanup(self.db_patch.stop)
        db.init_db(); control.initialize()
        app=FastAPI(); app.include_router(control_api.router)
        self.app=app; self.client=TestClient(app)

    def auth(self):
        self.app.dependency_overrides[get_current_user]=lambda:'alice'

    def test_all_control_routes_require_auth(self):
        for path in ['overview','disks','network','services','processes','activity','metrics','operations','operations/missing']:
            self.assertEqual(self.client.get('/api/control/'+path).status_code,401,path)
        self.assertEqual(self.client.post('/api/control/reboot',json={'hostname':'host','confirm_impact':True}).status_code,401)
        self.assertEqual(self.client.post('/api/control/services/docker/restart',json={'hostname':'host','confirm_impact':True}).status_code,401)

    def test_activity_is_persisted_filterable_and_never_stores_arbitrary_messages(self):
        control.record_activity('configuration.update','app1','example','succeeded',actor='alice',message='PASSWORD=hunter2 token=secret https://user:pass@host',correlation_id='run1')
        control.record_activity('restart','server','host','failed',message='safe summary')
        self.auth()
        result=self.client.get('/api/control/activity?resource_id=app1').json()['items']
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['actor'],'alice')
        self.assertEqual(result[0]['correlation_id'],'run1')
        self.assertNotIn('hunter2',str(result)); self.assertNotIn('secret',str(result)); self.assertNotIn('user:pass',str(result))
        control.initialize()
        self.assertEqual(len(control.activity('app1')['items']),1)

    def test_metric_history_prunes_old_samples_and_filters_resource(self):
        control.record_metric('server',{'cpu_percent':10},timestamp='2000-01-01T00:00:00+00:00')
        control.record_metric('server',{'cpu_percent':21})
        control.record_metric('app1',{'cpu_percent':99})
        self.auth(); result=self.client.get('/api/control/metrics?resource_id=server').json()
        self.assertEqual(result['retention_hours'],24)
        self.assertEqual([x['cpu_percent'] for x in result['items']],[21])

    def test_host_adapter_fail_closed_and_only_accepts_allowlisted_argv(self):
        adapter=control.HostAdapter(root=Path(self.temp.name)/'absent')
        self.assertFalse(adapter.capabilities()['reboot'])
        with self.assertRaises(ValueError): adapter.execute('restart','ssh; reboot')
        with self.assertRaises(ValueError): adapter.execute('shutdown')
        with self.assertRaises(RuntimeError): adapter.execute('reboot')

    def test_action_requires_host_and_impact_and_capability(self):
        self.auth()
        fake=SimpleNamespace(capabilities=lambda:{'reboot':True,'service_restart':True,'reason':None},identity=lambda:{'hostname':'ubuntu'},boot_id=lambda:'boot-a')
        with patch.object(control,'host',fake):
            self.assertEqual(self.client.post('/api/control/reboot',json={'hostname':'wrong','confirm_impact':True}).status_code,400)
            self.assertEqual(self.client.post('/api/control/reboot',json={'hostname':'ubuntu','confirm_impact':False}).status_code,400)
            self.assertEqual(self.client.post('/api/control/services/ssh/restart',json={'hostname':'ubuntu','confirm_impact':True}).status_code,404)
            response=self.client.post('/api/control/reboot',json={'hostname':'ubuntu','confirm_impact':True})
            self.assertEqual(response.status_code,202)
            op=response.json(); self.assertEqual(op['status'],'requested'); self.assertEqual(op['actor'],'alice')
            self.assertEqual(self.client.get('/api/control/operations/'+op['id']).json()['id'],op['id'])
            self.assertEqual(self.client.post('/api/control/reboot',json={'hostname':'ubuntu','confirm_impact':True}).status_code,409)
        with patch.object(control,'host',SimpleNamespace(capabilities=lambda:{'reboot':False,'service_restart':False,'reason':'unavailable'})):
            self.assertEqual(self.client.post('/api/control/reboot',json={'hostname':'ubuntu','confirm_impact':True}).status_code,409)

    def test_reboot_recovery_requires_a_changed_boot_id(self):
        fake=SimpleNamespace(capabilities=lambda:{'reboot':True,'service_restart':True},identity=lambda:{'hostname':'ubuntu'},boot_id=lambda:'boot-a')
        with patch.object(control,'host',fake):
            op=control.request_operation('reboot',None,'ubuntu',True,'alice')
            with db.connection() as conn: conn.execute("UPDATE control_operations SET status='reconnecting' WHERE id=?",(op['id'],))
            control.initialize()
            self.assertEqual(control.operation(op['id'])['status'],'unknown-after-disconnect')
        with patch.object(control,'host',SimpleNamespace(boot_id=lambda:'boot-b')):
            control.initialize()
            self.assertEqual(control.operation(op['id'])['status'],'succeeded')

    def test_worker_dispatches_fixed_adapter_and_records_failure_without_raw_error(self):
        fake=SimpleNamespace(capabilities=lambda:{'reboot':True,'service_restart':True},identity=lambda:{'hostname':'ubuntu'},boot_id=lambda:'boot-a',execute=lambda action,service: (_ for _ in ()).throw(RuntimeError('password=secret')))
        with patch.object(control,'host',fake):
            op=control.request_operation('restart','docker','ubuntu',True,'alice')
            control.dispatch(op['id'])
        result=control.operation(op['id']); self.assertEqual(result['status'],'failed'); self.assertNotIn('secret',str(result))


    def test_adapter_uses_fixed_argv_and_timeout_without_shell(self):
        adapter=control.HostAdapter(root=Path(self.temp.name))
        recorded=[]
        def run(argv, **kwargs):
            recorded.append((argv,kwargs))
            return SimpleNamespace(returncode=0,stdout='')
        with patch.object(adapter,'capabilities',return_value={'reboot':True,'service_restart':True}), patch.object(control.shutil,'which',return_value='/usr/sbin/chroot'), patch.object(control.subprocess,'run',side_effect=run):
            adapter.execute('restart','docker')
            adapter.execute('reboot')
        self.assertEqual(recorded[0][0],['/usr/sbin/chroot',self.temp.name,'/usr/bin/systemctl','restart','docker.service'])
        self.assertEqual(recorded[1][0][-2:],['reboot','--no-block'])
        self.assertEqual(recorded[0][1]['timeout'],15)
        self.assertNotIn('shell',recorded[0][1])

    def test_metrics_and_identity_read_actual_host_fixture_not_backend(self):
        root=Path(self.temp.name)
        fixture={'etc/hostname':'managed-ubuntu','proc/sys/kernel/hostname':'backend-container','etc/os-release':'PRETTY_NAME="Ubuntu test"','proc/sys/kernel/osrelease':'6.8-test','proc/uptime':'900.5 0','proc/loadavg':'1.0 2.0 3.0 1/200 2','proc/stat':'cpu  10 0 10 80 0 0 0 0\ncpu0 10 0 10 80 0 0 0 0','proc/meminfo':'MemTotal: 1000 kB\nMemAvailable: 400 kB','proc/1/net/dev':'Inter-| Receive\n eth0: 1000 0 0 0 0 0 0 0 2000 0 0 0 0 0 0 0'}
        for name,value in fixture.items():
            target=root/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(value)
        adapter=control.HostAdapter(root=root)
        result=adapter.metrics()
        self.assertEqual(result['hostname'],'managed-ubuntu')
        self.assertEqual(result['memory'],{'total':1024000,'used':614400,'percent':60.0})
        self.assertEqual(result['network']['rx_bytes'],1000)
        self.assertEqual(result['uptime_seconds'],900)
        self.assertTrue(result['host_available'])
        absent=control.HostAdapter(root=root/'absent').metrics()
        self.assertIsNone(absent['hostname']); self.assertIsNone(absent['memory'])

    def test_successful_reboot_waits_for_boot_change_and_pending_request_is_not_replayed(self):
        fake=SimpleNamespace(capabilities=lambda:{'reboot':True,'service_restart':True},identity=lambda:{'hostname':'ubuntu'},boot_id=lambda:'boot-a',execute=lambda action,service:None)
        with patch.object(control,'host',fake):
            op=control.request_operation('reboot',None,'ubuntu',True,'alice')
            control.dispatch(op['id'])
            self.assertEqual(control.operation(op['id'])['status'],'reconnecting')
        with db.connection() as conn: conn.execute('DELETE FROM control_operations')
        with patch.object(control,'host',fake):
            pending=control.request_operation('reboot',None,'ubuntu',True,'alice')
        with patch.object(control,'host',SimpleNamespace(boot_id=lambda:'boot-b')):
            control.initialize()
        self.assertEqual(control.operation(pending['id'])['status'],'failed')


    def test_container_lifecycle_records_actor_and_blocks_platform_mutation(self):
        from app.api import containers
        from unittest.mock import Mock
        self.app.include_router(containers.router); self.auth()
        container=SimpleNamespace(id='container1',name='web',labels={},restart=Mock())
        docker=SimpleNamespace(containers=SimpleNamespace(get=lambda id:container))
        with patch.object(containers,'client',return_value=docker), patch.object(containers,'serialize',return_value={'id':'container1'}):
            response=self.client.post('/api/containers/container1/restart')
            self.assertEqual(response.status_code,200)
            events=control.activity('container1')['items']
            self.assertEqual(len(events),1); self.assertEqual(events[0]['actor'],'alice')
            container.labels={'com.arfeen.system':'true'}
            self.assertEqual(self.client.post('/api/containers/container1/restart').status_code,409)
            self.assertEqual(container.restart.call_count,1)

    def test_platform_images_cannot_be_removed(self):
        from app.api import resources
        from unittest.mock import Mock
        self.app.include_router(resources.router); self.auth()
        remove=Mock()
        docker=SimpleNamespace(images=SimpleNamespace(remove=remove),containers=SimpleNamespace(list=lambda **kwargs:[SimpleNamespace(labels={'com.arfeen.system':'true'})]))
        with patch.object(resources,'client',return_value=docker):
            self.assertEqual(self.client.delete('/api/docker/images/platform').status_code,409)
        remove.assert_not_called()


    def test_network_reads_host_namespace_addresses_and_disks_use_pid1_mounts(self):
        root=Path(self.temp.name)
        fixture={'proc/sys/kernel/hostname':'host','etc/os-release':'PRETTY_NAME=Ubuntu','proc/1/net/dev':'eth0: 10 0 0 0 0 0 0 0 20 0 0 0 0 0 0 0','proc/1/net/fib_trie':' |-- 192.168.1.10\n    /32 host LOCAL','proc/1/net/route':'Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\neth0 0001A8C0 00000000 0001 0 0 0 00FFFFFF 0 0 0','proc/1/mounts':'/dev/root / ext4 rw 0 0','proc/mounts':'/dev/backend /backend ext4 rw 0 0'}
        for name,value in fixture.items():
            path=root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(value)
        adapter=control.HostAdapter(root=root)
        self.assertEqual(adapter.network()['items'][0]['addresses'],['192.168.1.10'])
        self.assertEqual(adapter.disks()['items'][0]['device'],'/dev/root')


    def test_single_sampler_persists_real_current_application_stats(self):
        with db.connection() as conn:
            conn.execute("INSERT INTO applications(id,name,source,framework,port,status,container_id,created_at) VALUES('app','web','ZIP upload','Dockerfile',8000,'running','current','today')")
        values={'cpu_stats':{'cpu_usage':{'total_usage':300},'system_cpu_usage':1000,'online_cpus':2},'precpu_stats':{'cpu_usage':{'total_usage':200},'system_cpu_usage':600},'memory_stats':{'usage':512,'limit':2048},'networks':{'eth0':{'rx_bytes':7,'tx_bytes':9}}}
        from app.services import docker_engine
        stop=threading.Event()
        docker=SimpleNamespace(containers=SimpleNamespace(get=lambda id:SimpleNamespace(stats=lambda **kwargs:values)))
        with patch.object(control,'_stop',stop),patch.object(stop,'wait',side_effect=lambda timeout:stop.set()),patch.object(control,'host',SimpleNamespace(metrics=lambda:{'cpu_percent':3},boot_id=lambda:'boot-a')),patch.object(docker_engine,'client',return_value=docker):
            control._sample()
        sample=control.metrics('app')['items'][0]
        self.assertEqual(sample['cpu_percent'],50.0)
        self.assertEqual(sample['memory'],{'used':512,'total':2048})
        self.assertEqual(sample['network'],{'rx_bytes':7,'tx_bytes':9})
        self.assertEqual(sample['container_id'],'current')


    def test_capability_probe_requires_positive_systemd_evidence(self):
        root=Path(self.temp.name)
        for folder in ['run/systemd/system','usr/bin']: (root/folder).mkdir(parents=True,exist_ok=True)
        (root/'usr/bin/systemctl').touch()
        (root/'etc').mkdir(exist_ok=True); (root/'etc/hostname').write_text('managed-host')
        adapter=control.HostAdapter(root=root)
        with patch.object(adapter,'available',return_value=True),patch.object(control.os,'geteuid',return_value=0),patch.object(control.shutil,'which',return_value='/usr/sbin/chroot'),patch.object(adapter,'_run',return_value=SimpleNamespace(returncode=0,stdout='')):
            self.assertFalse(adapter.capabilities()['reboot'])


    def test_default_activity_actor_resolves_configured_administrator(self):
        with db.connection() as conn: conn.execute("INSERT INTO settings(key,value) VALUES('admin_username','owner')")
        control.record_activity('deploy','app','web','succeeded')
        control.record_activity('restart','app','web','succeeded',actor='alice')
        self.assertEqual([item['actor'] for item in control.activity('app')['items']],['alice','owner'])


    def test_persistent_host_identity_wins_over_backend_uts_and_confirmation(self):
        root=Path(self.temp.name)
        for name,value in {'etc/hostname':'actual-ubuntu\n','etc/os-release':'PRETTY_NAME=Ubuntu','proc/sys/kernel/hostname':'backend-container'}.items():
            path=root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(value)
        adapter=control.HostAdapter(root=root)
        self.assertEqual(adapter.identity()['hostname'],'actual-ubuntu')
        self.auth()
        with patch.object(control,'host',adapter),patch.object(adapter,'capabilities',return_value={'reboot':True,'service_restart':True}):
            wrong=self.client.post('/api/control/reboot',json={'hostname':'backend-container','confirm_impact':True})
            self.assertEqual(wrong.status_code,400)
            accepted=self.client.post('/api/control/reboot',json={'hostname':'actual-ubuntu','confirm_impact':True})
            self.assertEqual(accepted.status_code,202)
            self.assertEqual(accepted.json()['hostname'],'actual-ubuntu')
        (root/'etc/hostname').unlink()
        self.assertIsNone(adapter.identity()['hostname'])


    def test_hostname_fallback_uses_fixed_read_only_systemd_command(self):
        root=Path(self.temp.name)
        for folder in ['run/systemd/system','usr/bin']: (root/folder).mkdir(parents=True,exist_ok=True)
        (root/'usr/bin/hostnamectl').touch()
        adapter=control.HostAdapter(root=root)
        with patch.object(control.os,'geteuid',return_value=0),patch.object(control.shutil,'which',return_value='/usr/sbin/chroot'),patch.object(control.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='systemd-host\n')) as run:
            self.assertEqual(adapter.hostname(),'systemd-host')
            self.assertEqual(run.call_args.args[0],['/usr/sbin/chroot',str(root),'/usr/bin/hostnamectl','--static'])
            self.assertEqual(run.call_args.kwargs['timeout'],5)
            self.assertNotIn('shell',run.call_args.kwargs)
        with patch.object(control.os,'geteuid',return_value=0),patch.object(control.shutil,'which',return_value='/usr/sbin/chroot'),patch.object(control.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='backend-container')):
            self.assertIsNone(adapter.hostname())

if __name__=='__main__': unittest.main()
