"""Runtime log API: auth, application lookup, bounded output and replacements."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
_runtime = tempfile.TemporaryDirectory()
for variable, suffix in (("DATA_DIR", "data"), ("WORKSPACE_DIR", "workspace"), ("STORAGE_DIR", "storage")):
    os.environ.setdefault(variable, str(Path(_runtime.name) / suffix))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from docker.errors import NotFound
from app.core.auth import get_current_user
from app.core.db import connection, init_db
from app.api import applications


class ApplicationRuntimeTests(unittest.TestCase):
    def setUp(self):
        init_db()
        with connection() as db:
            db.execute("DELETE FROM applications")
            db.execute("INSERT INTO applications(id,name,source,framework,port,status,container_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                       ("runtime-app", "sample", "ZIP upload", "Dockerfile", 8000, "running", "old-container", "2026-10-28"))
        app = FastAPI()
        app.include_router(applications.router)
        self.app = app
        self.client = TestClient(app)

    def authenticate(self):
        self.app.dependency_overrides[get_current_user] = lambda: "test-admin"

    def test_runtime_logs_require_authentication(self):
        self.assertEqual(self.client.get("/api/apps/runtime-app/logs").status_code, 401)

    def test_logs_follow_current_container_and_bound_tail(self):
        self.authenticate()
        old = SimpleNamespace(status="running", logs=Mock(return_value=b"old output\n"))
        new = SimpleNamespace(status="exited", logs=Mock(return_value=b"new output\xff\n"))
        containers = SimpleNamespace(get=lambda container_id: {"old-container": old, "new-container": new}[container_id])
        with patch.object(applications, "client", return_value=SimpleNamespace(containers=containers)):
            response = self.client.get("/api/apps/runtime-app/logs?tail=99999")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["logs"], "old output\n")
            old.logs.assert_called_once_with(tail=2000, timestamps=True)
            with connection() as db:
                db.execute("UPDATE applications SET container_id='new-container' WHERE id='runtime-app'")
            response = self.client.get("/api/apps/runtime-app/logs?tail=0")
            self.assertEqual(response.json()["logs"], "new output\ufffd\n")
            self.assertEqual(response.json()["status"], "exited")
            self.assertEqual(response.json()["container_id"], "new-container")
            new.logs.assert_called_once_with(tail=1, timestamps=True)
            self.assertIn("no-store", response.headers["cache-control"])

    def test_unknown_app_and_missing_container_have_clear_errors(self):
        self.authenticate()
        self.assertEqual(self.client.get("/api/apps/missing/logs").status_code, 404)
        with patch.object(applications, "client") as docker:
            docker.return_value.containers.get.side_effect = NotFound("missing")
            response = self.client.get("/api/apps/runtime-app/logs")
        self.assertEqual(response.status_code, 404)
        self.assertIn("container", response.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
