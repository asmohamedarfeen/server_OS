"""Atomic Traefik file-provider routes with acknowledgement before retirement.

Docker routing labels remain disabled on candidates. Only the verified running
container is published, and the previous route is recoverable until DB commit.
"""
import ipaddress
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from ..core.config import DATA_DIR
from ..core.db import connection
from .docker_engine import client

ROUTES_DIR=DATA_DIR/'proxy-routes'
ACK_TIMEOUT=15


class RouteError(RuntimeError):
    pass


def route_path(app_id):
    if not isinstance(app_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}',app_id):
        raise RouteError('Invalid application route identifier')
    # JSON is a YAML subset; the .yaml suffix is required by Traefik discovery.
    return ROUTES_DIR/f'app-{app_id}.yaml'


def snapshot(app_id):
    path=route_path(app_id)
    try: return path.read_bytes()
    except FileNotFoundError: return None


def _atomic_write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,temporary=tempfile.mkstemp(prefix='.route-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as target:
            target.write(data);target.flush();os.fsync(target.fileno())
        os.replace(temporary,path)
    finally:
        try:os.unlink(temporary)
        except FileNotFoundError:pass


def remove(app_id):
    route_path(app_id).unlink(missing_ok=True)


def restore(app_id,previous):
    if previous is None:remove(app_id)
    else:_atomic_write(route_path(app_id),previous)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None



def _status_ready(status,config):
    return status==config.get('expected_status',200) if config.get('path') else 200<=status<500


def probe_target(target,domain,readiness=None,timeout=ACK_TIMEOUT):
    """Check the exact proxy-network socket before advertising it to Traefik."""
    config=readiness or {};path=config.get('path') or '/'
    parsed=urllib.parse.urlparse(target)
    try:
        ipaddress.ip_address(parsed.hostname)
        valid=parsed.scheme=='http' and parsed.port and not (parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment)
    except (ValueError,TypeError):valid=False
    if not valid:raise RouteError('Invalid managed proxy target')
    if not path.startswith('/') or path.startswith('//') or any(c in path for c in '\r\n?#'):
        raise RouteError('Invalid proxy readiness path')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    deadline=time.monotonic()+min(timeout,config.get('timeout',timeout))
    while True:
        response=None
        try:
            request=urllib.request.Request(target+path,headers={'Host':domain,'Cache-Control':'no-cache'})
            try:response=opener.open(request,timeout=max(.1,min(2,deadline-time.monotonic())))
            except urllib.error.HTTPError as exc:response=exc
            if _status_ready(response.status,config):return
        except (OSError,ValueError):pass
        finally:
            if response is not None:response.close()
        remaining=deadline-time.monotonic()
        if remaining<=0:raise RouteError('Candidate did not become ready on its proxy-network address before the timeout')
        time.sleep(min(.25,remaining))


def wait_applied(domain,deployment_id,readiness=None,timeout=ACK_TIMEOUT,exclude=None):
    config=readiness or {};path=config.get('path') or '/'
    # This path is internal configuration, never an arbitrary probe destination.
    if not path.startswith('/') or path.startswith('//') or any(c in path for c in '\r\n?#'):
        raise RouteError('Invalid route acknowledgement path')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    deadline=time.monotonic()+timeout
    while True:
        response=None
        try:
            request=urllib.request.Request('http://traefik:80'+path,headers={'Host':domain,'Cache-Control':'no-cache'})
            try:response=opener.open(request,timeout=max(.1,min(2,deadline-time.monotonic())))
            except urllib.error.HTTPError as exc:response=exc
            token=response.headers.get('X-Arfeen-Deployment')
            status=response.status
            # Middleware headers alone also appear on proxy-generated failures.
            # Confirm the configured HTTP policy through the actual proxy hop,
            # or accept ordinary app responses (including root 401/404) only.
            status_ready=_status_ready(status,config)
            deployment_ready=(deployment_id is not None and token==deployment_id) or (deployment_id is None and token!=exclude)
            if status_ready and deployment_ready:return
        except (OSError,ValueError):pass
        finally:
            if response is not None:response.close()
        remaining=deadline-time.monotonic()
        if remaining<=0:raise RouteError('Proxy did not acknowledge the application route before the timeout')
        time.sleep(min(.25,remaining))


def _configuration(app_id,domain,container,port):
    if not isinstance(domain,str) or len(domain)>253 or not re.fullmatch(r'(?=.{1,253}$)([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?',domain):
        raise RouteError('Invalid application domain')
    if type(port) is not int or not 1<=port<=65535:raise RouteError('Invalid application port')
    container.reload()
    address=container.attrs.get('NetworkSettings',{}).get('Networks',{}).get('arfeen_proxy',{}).get('IPAddress')
    try:ip=ipaddress.ip_address(address)
    except ValueError:raise RouteError('Application is not attached to the proxy network')
    if not isinstance(container.id,str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}',container.id):raise RouteError('Invalid deployment identifier')
    host=f'[{ip}]' if ip.version==6 else str(ip)
    key='app-'+app_id;middleware=key+'-deployment'
    return {'http':{'routers':{key:{'rule':f'Host(`{domain}`)','entryPoints':['web'],'priority':1000,'service':key,'middlewares':[middleware]}},'services':{key:{'loadBalancer':{'servers':[{'url':f'http://{host}:{port}'}]}}},'middlewares':{middleware:{'headers':{'customResponseHeaders':{'X-Arfeen-Deployment':container.id}}}}}}


def switch(app_id,domain,container,port,readiness=None):
    path=route_path(app_id);value=_configuration(app_id,domain,container,port)
    service=next(iter(value['http']['services'].values()))
    target=service['loadBalancer']['servers'][0]['url']
    probe_target(target,domain,readiness)
    previous=snapshot(app_id)
    _atomic_write(path,json.dumps(value,separators=(',',':')).encode())
    try:
        wait_applied(domain,container.id,readiness)
    except Exception as exc:
        restore(app_id,previous)
        # Let the watcher acknowledge rollback before the caller removes candidate.
        try:
            previous_token=None
            if previous:
                config=json.loads(previous)
                previous_token=next(iter(config['http']['middlewares'].values()))['headers']['customResponseHeaders']['X-Arfeen-Deployment']
            wait_applied(domain,previous_token,readiness,timeout=5,exclude=container.id)
        except Exception:pass
        if isinstance(exc,RouteError):raise
        raise RouteError('Proxy route switch failed') from exc
    return previous


def regenerate():
    """Rebuild route files from durable current app/container IDs at startup."""
    result={'available':True,'restored':0,'failed':0}
    try:
        engine=client()
        with connection() as db:apps=[dict(r) for r in db.execute("SELECT id,domain,port,container_id FROM applications WHERE domain IS NOT NULL AND domain<>''")]
    except Exception:
        return {'available':False,'restored':0,'failed':0}
    ROUTES_DIR.mkdir(parents=True,exist_ok=True)
    active=set()
    for app in apps:
        try:
            path=route_path(app['id']);active.add(path.name)
            container=engine.containers.get(app['container_id'])
            value=_configuration(app['id'],app['domain'],container,app['port'])
            _atomic_write(path,json.dumps(value,separators=(',',':')).encode());result['restored']+=1
        except Exception:result['failed']+=1
    for path in ROUTES_DIR.glob('app-*.yaml'):
        if path.name not in active:path.unlink(missing_ok=True)
    return result
