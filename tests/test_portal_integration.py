import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
_runtime = tempfile.TemporaryDirectory()
for variable, suffix in (('DATA_DIR', 'data'), ('WORKSPACE_DIR', 'workspace'), ('STORAGE_DIR', 'storage')):
    os.environ.setdefault(variable, str(Path(_runtime.name) / suffix))

from fastapi.testclient import TestClient
from app.main import app
from app.core import auth
from app.core.db import connection, init_db
from app.services import control, pipelines
from app.api import applications


class PortalIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        init_db(); control.initialize(); pipelines.initialize()
        with connection() as db:
            db.execute("DELETE FROM applications WHERE id='portal-test'")
            db.execute("DELETE FROM control_activity")
            db.execute("INSERT INTO applications(id,name,source,framework,port,status,container_id,created_at) VALUES('portal-test','portal-app','ZIP upload','Dockerfile',8000,'running','fake-container','2026-10-28')")

    def test_new_routes_registered_and_authenticated(self):
        for path in ('/api/control/overview', '/api/control/activity', '/api/pipelines'):
            self.assertEqual(self.client.get(path).status_code, 401, path)

    def test_mutation_activity_has_actual_actor_and_no_raw_error(self):
        with patch.object(auth, 'JWT_SECRET', 'a-test-key-with-at-least-thirty-two-characters'):
            self.client.cookies.set('arfeen_session', auth.token_for('portal-admin'))
            container = SimpleNamespace(restart=Mock(side_effect=RuntimeError('secret-token-value')))
            with patch.object(applications, 'client', return_value=SimpleNamespace(containers=SimpleNamespace(get=lambda _: container))):
                response = self.client.post('/api/apps/portal-test/restart')
            self.assertEqual(response.status_code, 400)
            events = self.client.get('/api/control/activity?resource_id=portal-test').json()['items']
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]['actor'], 'portal-admin')
            self.assertEqual(events[0]['status'], 'failed')
            self.assertNotIn('secret-token-value', str(events))

    def test_additive_initialization_preserves_existing_apps(self):
        control.initialize(); pipelines.initialize()
        with connection() as db:
            self.assertEqual(db.execute("SELECT name FROM applications WHERE id='portal-test'").fetchone()['name'], 'portal-app')


if __name__ == '__main__': unittest.main()
