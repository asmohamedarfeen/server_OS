"""Durable activity, bounded metrics and narrowly scoped managed-host operations."""
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException
from ..core.db import connection

SERVICES = ('docker', 'containerd', 'tailscaled')
RETENTION_HOURS = 24
_stop = threading.Event()
_threads = []
_actions = queue.Queue()
_request_lock = threading.Lock()
_last_net = None
_last_cpu = None


def now():
    return datetime.now(timezone.utc).isoformat()


def _safe_label(value, fallback='resource'):
    # Never retain arbitrary untrusted strings (URLs, command output, or env values).
    value = str(value or '')[:128]
    return value if re.fullmatch(r'[\w .:@/-]{1,128}', value) and not re.search(r'(?i)(password|secret|token|credential|authorization|://)', value) else fallback


class HostAdapter:
    def __init__(self, root=Path('/host')):
        self.root = Path(root)

    def read(self, path):
        try:
            return (self.root / path.lstrip('/')).read_text().strip()
        except (OSError, UnicodeError):
            return ''

    def available(self):
        return bool((self.root/'proc').is_dir() and self.read('/etc/os-release'))

    def hostname(self):
        # proc/sys/kernel/hostname follows the caller's UTS namespace even through
        # the mounted host procfs. The mounted persistent hostname is host data.
        hostname=self.read('/etc/hostname')
        if not hostname and os.geteuid()==0 and (self.root/'run/systemd/system').is_dir() and (self.root/'usr/bin/hostnamectl').is_file():
            executable=shutil.which('chroot')
            if executable:
                try:
                    result=subprocess.run([executable,str(self.root),'/usr/bin/hostnamectl','--static'],capture_output=True,text=True,timeout=5,check=False,
                                          env={**os.environ,'SYSTEMD_IN_CHROOT':'0','LC_ALL':'C'})
                    if result.returncode==0: hostname=result.stdout.strip()
                except (OSError,subprocess.SubprocessError): pass
        return hostname if re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,252}',hostname or '') else None

    def identity(self):
        release = {}
        for line in self.read('/etc/os-release').splitlines():
            if '=' in line:
                key, value = line.split('=',1); release[key] = value.strip('"')
        return {'hostname': self.hostname(),
                'platform': release.get('PRETTY_NAME'), 'kernel':self.read('/proc/sys/kernel/osrelease') or None,
                'identity_source':'host mount' if self.available() else 'unavailable', 'host_available': self.available()}

    def boot_id(self):
        return self.read('/proc/sys/kernel/random/boot_id')

    def _run(self, args):
        executable = shutil.which('chroot')
        if not executable:
            raise RuntimeError('Host adapter is unavailable')
        return subprocess.run([executable,str(self.root),'/usr/bin/systemctl',*args],capture_output=True,text=True,timeout=15,check=False,
                              env={**os.environ,'SYSTEMD_IN_CHROOT':'0','LC_ALL':'C'})

    def capabilities(self):
        inspection = self.available()
        supported = inspection and bool(self.hostname()) and os.geteuid()==0 and (self.root/'run/systemd/system').is_dir() and (self.root/'usr/bin/systemctl').is_file() and bool(shutil.which('chroot'))
        if supported:
            try:
                probe=self._run(['show','--property=Version','--value'])
                supported=probe.returncode==0 and bool(re.match(r'^\d{2,}',probe.stdout.strip()))
            except (OSError,subprocess.SubprocessError): supported=False
        return {'host_inspection':inspection,'service_restart':bool(supported),'reboot':bool(supported),
                'reason':None if supported else 'Host systemd control is unavailable or lacks permission'}

    def execute(self, action, service=None):
        if action not in {'restart','reboot'} or (action=='restart' and service not in SERVICES):
            raise ValueError('Unsupported host action')
        if not self.capabilities()['reboot' if action=='reboot' else 'service_restart']:
            raise RuntimeError('Host control is unavailable')
        args=['reboot','--no-block'] if action=='reboot' else ['restart',service+'.service']
        result=self._run(args)
        if result.returncode:
            raise RuntimeError('Host action failed')

    def services(self):
        caps=self.capabilities(); items=[]
        for name in SERVICES:
            state='unknown'; enabled=None
            if caps['service_restart']:
                try:
                    result=self._run(['show',name+'.service','--property=ActiveState,LoadState,UnitFileState'])
                    props=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
                    state=props.get('ActiveState','unknown') if props.get('LoadState')!='not-found' else 'not-found'
                    enabled=props.get('UnitFileState')
                except (OSError,subprocess.SubprocessError): pass
            items.append({'name':name,'status':state,'enabled':enabled,'can_restart':caps['service_restart'] and state!='not-found','impact':'May interrupt applications and dashboard connectivity' if name!='tailscaled' else 'May disconnect remote dashboard access'})
        return {'items':items,'available':caps['service_restart'],'reason':caps['reason']}

    def metrics(self):
        global _last_net, _last_cpu
        identity=self.identity()
        result={**identity,'id':'server','timestamp':now(),'cpu_percent':None,'cpu_count':None,'load_average':[],
                'uptime_seconds':None,'memory':None,'disk':None,'network':None,'process_count':None}
        if not identity['host_available']: return result
        try:
            result['uptime_seconds']=int(float(self.read('/proc/uptime').split()[0]))
            result['load_average']=[float(x) for x in self.read('/proc/loadavg').split()[:3]]
            stat=self.read('/proc/stat').splitlines()
            cpu=[int(x) for x in stat[0].split()[1:9]]
            total=sum(cpu); idle=cpu[3]+cpu[4]
            if _last_cpu and total>_last_cpu[0]: result['cpu_percent']=round(100*(1-(idle-_last_cpu[1])/(total-_last_cpu[0])),2)
            _last_cpu=(total,idle)
            result['cpu_count']=sum(bool(re.match(r'cpu\d+ ',line)) for line in stat)
            mem={line.split(':')[0]:int(line.split()[1])*1024 for line in self.read('/proc/meminfo').splitlines() if len(line.split())>=2}
            used=mem['MemTotal']-mem['MemAvailable']; result['memory']={'total':mem['MemTotal'],'used':used,'percent':round(100*used/mem['MemTotal'],2)}
            disk=shutil.disk_usage(self.root); result['disk']={'total':disk.total,'used':disk.used,'free':disk.free,'percent':round(100*disk.used/disk.total,2)}
            counters=[line.split(':',1)[1].split() for line in self.read('/proc/1/net/dev').splitlines() if ':' in line and line.split(':',1)[0].strip()!='lo']
            rx=sum(int(row[0]) for row in counters); tx=sum(int(row[8]) for row in counters); stamp=time.monotonic()
            result['network']={'rx_bytes':rx,'tx_bytes':tx,'rx_bytes_sec':None,'tx_bytes_sec':None}
            if _last_net:
                elapsed=max(stamp-_last_net[0],.001)
                result['network'].update(rx_bytes_sec=max(0,rx-_last_net[1])/elapsed,tx_bytes_sec=max(0,tx-_last_net[2])/elapsed)
            _last_net=(stamp,rx,tx)
            result['process_count']=sum(p.name.isdigit() for p in (self.root/'proc').iterdir())
        except (OSError,ValueError,KeyError,IndexError):
            result['sample_error']='Some host metrics could not be read'
        return result

    def disks(self):
        items=[]; seen=set()
        for line in self.read('/proc/1/mounts').splitlines():
            fields=line.split()
            if len(fields)<3: continue
            device,mount,fstype=fields[:3]
            if not device.startswith('/dev/') or mount in seen: continue
            seen.add(mount)
            # Resolve under the host mount; refuse symlinks which escape it.
            target=(self.root/mount.lstrip('/')).resolve()
            if not target.is_relative_to(self.root.resolve()): continue
            try:
                disk=shutil.disk_usage(target)
                items.append({'device':device,'mountpoint':mount,'filesystem':fstype,'total':disk.total,'used':disk.used,'free':disk.free,'percent':round(100*disk.used/disk.total,2)})
            except OSError: pass
        return {'items':items,'available':self.available(),'reason':None if self.available() else 'Host mount is unavailable'}

    def network(self):
        items=[]
        for line in self.read('/proc/1/net/dev').splitlines():
            if ':' not in line: continue
            name,data=line.split(':',1); values=data.split(); name=name.strip()
            if len(values)<9: continue
            items.append({'name':name,'rx_bytes':int(values[0]),'tx_bytes':int(values[8]),'state':self.read('/sys/class/net/'+name+'/operstate') or None,'mac':self.read('/sys/class/net/'+name+'/address') or None,'addresses':[]})
        # Host procfs avoids accidentally inspecting the backend bridge namespace.
        import ipaddress
        local_addresses=[]; previous=''
        for line in self.read('/proc/1/net/fib_trie').splitlines():
            if 'host LOCAL' in line:
                match=re.search(r'(\d+\.\d+\.\d+\.\d+)',previous)
                if match and match[1] not in local_addresses: local_addresses.append(match[1])
            previous=line
        routes=[]
        for line in self.read('/proc/1/net/route').splitlines()[1:]:
            fields=line.split()
            if len(fields)<8: continue
            try:
                destination=str(ipaddress.IPv4Address(bytes.fromhex(fields[1])[::-1]))
                mask=str(ipaddress.IPv4Address(bytes.fromhex(fields[7])[::-1]))
                network=ipaddress.IPv4Network(destination+'/'+mask,strict=False)
                if network.prefixlen: routes.append((fields[0],network))
            except ValueError: pass
        by_name={item['name']:item for item in items}
        for address in local_addresses:
            ip=ipaddress.IPv4Address(address)
            matching=[(name,network.prefixlen) for name,network in routes if ip in network]
            if ip.is_loopback and 'lo' in by_name: matching=[('lo',32)]
            if matching:
                longest=max(prefix for name,prefix in matching)
                names={name for name,prefix in matching if prefix==longest}
                if len(names)==1:
                    name=names.pop()
                    if name in by_name: by_name[name]['addresses'].append(address)
        for line in self.read('/proc/1/net/if_inet6').splitlines():
            fields=line.split()
            if len(fields)!=6: continue
            try:
                address=str(ipaddress.IPv6Address(bytes.fromhex(fields[0])))
                if address not in local_addresses: local_addresses.append(address)
                if fields[5] in by_name: by_name[fields[5]]['addresses'].append(address)
            except ValueError: pass
        ports=[]
        for protocol in ['tcp','tcp6','udp','udp6']:
            for line in self.read('/proc/1/net/'+protocol).splitlines()[1:]:
                fields=line.split()
                if len(fields)<4 or (protocol.startswith('tcp') and fields[3]!='0A'): continue
                address,port=fields[1].rsplit(':',1)
                try:
                    import socket
                    raw=bytes.fromhex(address)
                    packed=raw[::-1] if len(raw)==4 else b''.join(raw[i:i+4][::-1] for i in range(0,16,4))
                    ports.append({'protocol':protocol,'address':socket.inet_ntop(socket.AF_INET if len(raw)==4 else socket.AF_INET6,packed),'port':int(port,16)})
                except (ValueError,OSError): pass
        return {'items':items,'listening_ports':ports[:500],'available':self.available(),'local_addresses':local_addresses,'address_reason':'Host procfs addresses; IPv4 interface mapping omitted when routes are ambiguous'}

    def processes(self):
        items=[]
        if self.available():
            try:
                for path in (self.root/'proc').iterdir():
                    if not path.name.isdigit(): continue
                    data=self.read('/proc/'+path.name+'/status')
                    fields=dict(line.split(':',1) for line in data.splitlines() if ':' in line)
                    if fields:
                        items.append({'pid':int(path.name),'name':fields.get('Name','').strip(),'state':fields.get('State','').strip(),'memory_bytes':int(fields.get('VmRSS','0').split()[0])*1024})
            except (OSError,ValueError): pass
        return {'items':sorted(items,key=lambda x:x['memory_bytes'],reverse=True)[:200],'available':self.available()}

host=HostAdapter()


def initialize():
    with connection() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS control_activity(id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, resource_id TEXT NOT NULL, resource_name TEXT NOT NULL, status TEXT NOT NULL, actor TEXT NOT NULL, message TEXT NOT NULL, correlation_id TEXT, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS control_activity_resource ON control_activity(resource_id,id);
        CREATE TABLE IF NOT EXISTS control_metrics(id INTEGER PRIMARY KEY AUTOINCREMENT,resource_id TEXT NOT NULL,timestamp TEXT NOT NULL,sample_json TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS control_metrics_resource ON control_metrics(resource_id,timestamp);
        CREATE TABLE IF NOT EXISTS control_operations(id TEXT PRIMARY KEY,action TEXT NOT NULL,service TEXT,status TEXT NOT NULL,actor TEXT NOT NULL,hostname TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,boot_id TEXT,message TEXT NOT NULL);
        ''')
        boot=host.boot_id()
        rows=conn.execute("SELECT * FROM control_operations WHERE status IN ('requested','dispatched','reconnecting','unknown-after-disconnect')").fetchall()
        for row in rows:
            if row['status']=='requested':
                status='failed'; message='Backend restarted before the queued host action was dispatched'
            elif row['action']=='reboot' and row['boot_id'] and boot and row['boot_id']!=boot:
                status='succeeded'; message='Host boot changed after the recorded reboot request'
            else:
                status='unknown-after-disconnect'; message='Backend restarted; the host action outcome could not be confirmed'
            conn.execute('UPDATE control_operations SET status=?,message=?,updated_at=? WHERE id=?',(status,message,now(),row['id']))
        _prune(conn)


def _prune(conn):
    cutoff=(datetime.now(timezone.utc)-timedelta(hours=RETENTION_HOURS)).isoformat()
    conn.execute('DELETE FROM control_metrics WHERE timestamp < ?',(cutoff,))
    conn.execute('DELETE FROM control_activity WHERE id NOT IN (SELECT id FROM control_activity ORDER BY id DESC LIMIT 10000)')
    conn.execute("DELETE FROM control_operations WHERE id NOT IN (SELECT id FROM control_operations ORDER BY created_at DESC LIMIT 1000) AND status NOT IN ('requested','dispatched','reconnecting')")


def record_activity(action,resource_id,resource_name,status,actor='administrator',message='',correlation_id=None):
    # Free-form errors and request bodies are deliberately never retained. Status is the summary.
    summary={'failed':'Operation failed; inspect private runtime or build logs for details','succeeded':'Operation completed','requested':'Operation requested','running':'Operation running'}.get(status,'Operation status updated')
    with connection() as conn:
        if actor == 'administrator':
            configured_actor = conn.execute("SELECT value FROM settings WHERE key='admin_username'").fetchone()
            if configured_actor: actor = configured_actor['value']
        conn.execute('INSERT INTO control_activity(action,resource_id,resource_name,status,actor,message,correlation_id,created_at) VALUES(?,?,?,?,?,?,?,?)',
                     (_safe_label(action,'operation'),_safe_label(resource_id),_safe_label(resource_name),_safe_label(status,'unknown'),_safe_label(actor,'administrator'),summary,_safe_label(correlation_id) if correlation_id else None,now()))
        _prune(conn)


def activity(resource_id=None,limit=100,before=None):
    clauses=[]; values=[]
    if resource_id: clauses.append('resource_id=?'); values.append(resource_id)
    if before: clauses.append('id<?'); values.append(before)
    query='SELECT * FROM control_activity'+(' WHERE '+' AND '.join(clauses) if clauses else '')+' ORDER BY id DESC LIMIT ?'
    with connection() as conn: rows=conn.execute(query,(*values,max(1,min(limit,500)))).fetchall()
    items=[dict(row) for row in rows]
    return {'items':items,'next_cursor':items[-1]['id'] if len(items)==max(1,min(limit,500)) else None}


def record_metric(resource_id,sample,timestamp=None):
    with connection() as conn:
        conn.execute('INSERT INTO control_metrics(resource_id,timestamp,sample_json) VALUES(?,?,?)',(resource_id,timestamp or now(),json.dumps(sample,allow_nan=False)))
        _prune(conn)


def metrics(resource_id='server',limit=1440):
    with connection() as conn:
        _prune(conn)
        rows=conn.execute('SELECT timestamp,sample_json FROM control_metrics WHERE resource_id=? ORDER BY timestamp DESC LIMIT ?',(resource_id,max(1,min(limit,8640)))).fetchall()
    return {'resource_id':resource_id,'retention_hours':24,'items':[{**json.loads(row['sample_json']),'timestamp':row['timestamp']} for row in reversed(rows)]}


def overview():
    result=host.metrics(); result['capabilities']=host.capabilities()
    from .docker_engine import client
    try:
        version=client().version(); result['docker']={'available':True,'version':version.get('Version')}
    except Exception: result['docker']={'available':False,'version':None}
    with connection() as conn:
        result['affected_apps']=[dict(row) for row in conn.execute('SELECT id,name,status FROM applications').fetchall()]
    return result


def operation(operation_id):
    with connection() as conn: row=conn.execute('SELECT * FROM control_operations WHERE id=?',(operation_id,)).fetchone()
    if not row: raise HTTPException(404,'Operation not found')
    item=dict(row); item.pop('boot_id',None)
    return item


def operations():
    with connection() as conn: ids=[row['id'] for row in conn.execute('SELECT id FROM control_operations ORDER BY created_at DESC LIMIT 100').fetchall()]
    return {'items':[operation(id) for id in ids]}


def request_operation(action,service,hostname,confirm_impact,actor):
    if action not in {'reboot','restart'} or (action=='restart' and service not in SERVICES): raise HTTPException(404,'Unsupported host action')
    caps=host.capabilities()
    if not caps.get('reboot' if action=='reboot' else 'service_restart'): raise HTTPException(409,caps.get('reason') or 'Host control is unavailable')
    actual=host.identity().get('hostname')
    if not actual or hostname!=actual: raise HTTPException(400,'Enter the exact managed hostname')
    if not confirm_impact: raise HTTPException(400,'Confirm application and dashboard connectivity impact')
    id=uuid.uuid4().hex; stamp=now()
    with _request_lock:
        with connection() as conn:
            if conn.execute("SELECT 1 FROM control_operations WHERE status IN ('requested','dispatched','reconnecting')").fetchone(): raise HTTPException(409,'A host operation is already active')
            conn.execute('INSERT INTO control_operations VALUES(?,?,?,?,?,?,?,?,?,?)',(id,action,service,'requested',actor,actual,stamp,stamp,host.boot_id(),'Host action queued; connectivity may be interrupted'))
        record_activity('host.'+action,'server',actual,'requested',actor,correlation_id=id)
        _actions.put(id)
    return operation(id)


def _state(id,status,message):
    with connection() as conn: conn.execute('UPDATE control_operations SET status=?,message=?,updated_at=? WHERE id=?',(status,message,now(),id))


def dispatch(id):
    op=operation(id)
    if op['status']!='requested': return
    _state(id,'dispatched','Host action dispatched')
    try:
        host.execute(op['action'],op['service'])
        if op['action']=='reboot':
            _state(id,'reconnecting','Waiting for a changed host boot ID; response alone does not confirm reboot')
        else:
            _state(id,'succeeded','Host service restart completed')
            record_activity('host.restart','server',op['hostname'],'succeeded',op['actor'],correlation_id=id)
    except Exception:
        _state(id,'failed','Host action failed or timed out; outcome may require inspection')
        record_activity('host.'+op['action'],'server',op['hostname'],'failed',op['actor'],correlation_id=id)


def _worker():
    while not _stop.is_set():
        try: id=_actions.get(timeout=.5)
        except queue.Empty: continue
        try:
            # Give the accepted HTTP response time to leave before connectivity is interrupted.
            if not _stop.wait(2): dispatch(id)
        except Exception: pass
        finally: _actions.task_done()


def _sample():
    while not _stop.is_set():
        try:
            record_metric('server',host.metrics())
            with connection() as conn:
                boot=host.boot_id()
                rows=conn.execute("SELECT id,boot_id,updated_at FROM control_operations WHERE action='reboot' AND status='reconnecting'").fetchall()
                for row in rows:
                    if boot and row['boot_id'] and boot!=row['boot_id']:
                        conn.execute("UPDATE control_operations SET status='succeeded',message='Host boot changed',updated_at=? WHERE id=?",(now(),row['id']))
                    elif datetime.now(timezone.utc)-datetime.fromisoformat(row['updated_at'])>timedelta(minutes=5):
                        conn.execute("UPDATE control_operations SET status='unknown-after-disconnect',message='No changed host boot ID observed',updated_at=? WHERE id=?",(now(),row['id']))
            # One backend sampler owns application history, rather than browser pollers.
            from .docker_engine import client
            with connection() as conn: apps=conn.execute('SELECT id,container_id FROM applications WHERE container_id IS NOT NULL').fetchall()
            if apps:
                docker=client()
                for app in apps:
                    if _stop.is_set(): break
                    try:
                        stats=docker.containers.get(app['container_id']).stats(stream=False)
                        cpu=stats.get('cpu_stats',{}); previous=stats.get('precpu_stats',{})
                        delta=cpu.get('cpu_usage',{}).get('total_usage',0)-previous.get('cpu_usage',{}).get('total_usage',0)
                        system=cpu.get('system_cpu_usage',0)-previous.get('system_cpu_usage',0)
                        cpus=cpu.get('online_cpus') or len(cpu.get('cpu_usage',{}).get('percpu_usage',[])) or 1
                        mem=stats.get('memory_stats',{}); networks=stats.get('networks',{})
                        record_metric(app['id'],{'cpu_percent':round(delta/system*cpus*100,2) if system>0 else None,'memory':{'used':mem.get('usage'),'total':mem.get('limit')},'network':{'rx_bytes':sum(x.get('rx_bytes',0) for x in networks.values()),'tx_bytes':sum(x.get('tx_bytes',0) for x in networks.values())},'container_id':app['container_id']})
                    except Exception: continue
        except Exception: pass
        _stop.wait(60)


def start():
    if any(thread.is_alive() for thread in _threads): return
    _stop.clear(); _threads.clear()
    for target,name in [(_worker,'host-control'),(_sample,'host-metrics')]:
        thread=threading.Thread(target=target,name=name,daemon=True); _threads.append(thread); thread.start()


def stop():
    _stop.set()
    for thread in _threads: thread.join(timeout=2)
