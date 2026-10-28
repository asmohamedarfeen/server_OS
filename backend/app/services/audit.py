"""Record management outcomes without retaining request bodies or exception text."""
import logging
from ..core.auth import get_current_user
from ..core.db import connection
from . import control

logger = logging.getLogger(__name__)


async def audit_mutation(request, call_next):
    response = await call_next(request)
    if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return response
    parts = request.url.path.strip('/').split('/')
    if len(parts) < 2 or parts[0] != 'api' or parts[1] not in {'apps', 'databases', 'files', 'containers', 'docker', 'deployment-jobs'}:
        return response
    try:
        actor = get_current_user(request)
    except Exception:
        return response
    group = parts[1]
    # These endpoints record precise successful events themselves.
    if response.status_code < 400 and (group in {'containers', 'docker'} or (group == 'apps' and parts[-1] in {'source', 'readiness'})):
        return response
    resource_id = parts[2] if len(parts) > 2 else group
    resource_name = resource_id
    action = {'POST': 'create', 'PUT': 'configure', 'PATCH': 'configure', 'DELETE': 'delete'}[request.method]
    if group == 'apps' and len(parts) > 3:
        action = parts[-1]
    if group == 'deployment-jobs':
        action = 'queue'
        if len(parts) > 3 and parts[2] == 'apps':
            resource_id = parts[3]
    try:
        if group in {'apps', 'databases'} or group == 'deployment-jobs' and len(parts) > 3:
            table = 'databases' if group == 'databases' else 'applications'
            with connection() as db:
                row = db.execute(f'SELECT name FROM {table} WHERE id=?', (resource_id,)).fetchone()
            if row:
                resource_name = row['name']
        status = 'failed' if response.status_code >= 400 else 'queued' if response.status_code == 202 else 'success'
        control.record_activity(f'{group}.{action}', resource_id, resource_name, status, actor=actor)
    except Exception:
        # Audit persistence must not turn a completed mutation into a false failure.
        logger.warning('Management operation audit could not be persisted')
    return response
