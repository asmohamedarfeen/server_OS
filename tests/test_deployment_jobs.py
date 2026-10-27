import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
_runtime = tempfile.TemporaryDirectory()
for variable, suffix in (("DATA_DIR", "data"), ("WORKSPACE_DIR", "workspace"), ("STORAGE_DIR", "storage")):
    os.environ.setdefault(variable, str(Path(_runtime.name) / suffix))

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.core.db import connection, init_db
from app.core.auth import get_current_user
from app.services import deployment_jobs as jobs
from app.api import applications, deployment_jobs as api


class DeploymentJobTests(unittest.TestCase):
    def setUp(self):
        init_db()
        with connection() as db:
            db.execute("DELETE FROM deployment_job_logs")
            db.execute("DELETE FROM deployment_jobs")
        app = FastAPI()
        app.include_router(api.router)
        self.client = TestClient(app)
        self.app = app

    def authenticate(self):
        self.app.dependency_overrides[get_current_user] = lambda: "test-admin"

    def job(self):
        return jobs.create_job("sample", "app:sample", "https://github.com/example/sample.git", "main")

    def test_jobs_and_log_download_require_authentication(self):
        job = self.job()
        for url in ("/api/deployment-jobs", f"/api/deployment-jobs/{job['id']}", f"/api/deployment-jobs/{job['id']}/logs"):
            self.assertEqual(self.client.get(url).status_code, 401)

    def test_submit_returns_202_without_waiting_for_clone_or_build(self):
        self.authenticate()
        with patch.object(api.jobs, "submit_job") as submit:
            response = self.client.post("/api/deployment-jobs/github", json={"name": "queued-test", "url": "https://github.com/example/sample", "ref": "main"})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "queued")
        self.assertEqual(submit.call_count, 1)
        self.assertNotIn("environment", response.json())

    def test_duplicate_submission_returns_existing_job_id(self):
        job = self.job()
        with self.assertRaises(HTTPException) as error:
            self.job()
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(error.exception.detail["job_id"], job["id"])

    def test_success_persists_stage_logs_and_result(self):
        job = self.job()
        def work():
            jobs.stage("build", "Building image")
            jobs.log("Step 1/2 : FROM nginx")
            return {"id": "application-id", "status": "running"}
        jobs.run_job(job["id"], work)
        self.authenticate()
        result = self.client.get(f"/api/deployment-jobs/{job['id']}").json()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"]["id"], "application-id")
        self.assertTrue(result["finished_at"])
        self.assertTrue(any("Step 1/2" in line["message"] for line in result["logs"]))

    def test_failure_retains_stage_and_redacts_secrets_before_storage(self):
        job = self.job()
        def work():
            jobs.stage("build", "Installing dependencies")
            jobs.log("token=github_pat_abcdef password=database-secret")
            raise RuntimeError("Build failed: database-secret")
        jobs.run_job(job["id"], work, ["database-secret"])
        self.authenticate()
        details = self.client.get(f"/api/deployment-jobs/{job['id']}").json()
        downloaded = self.client.get(f"/api/deployment-jobs/{job['id']}/logs").text
        self.assertEqual(details["status"], "failed")
        self.assertEqual(details["stage"], "build")
        self.assertNotIn("database-secret", str(details) + downloaded)
        self.assertNotIn("github_pat_abcdef", str(details) + downloaded)
        self.assertIn("[redacted]", downloaded)
        with connection() as db:
            self.assertNotIn("database-secret", str(db.execute("SELECT message FROM deployment_job_logs").fetchall()))

    def test_restart_marks_unfinished_jobs_interrupted(self):
        job = self.job()
        jobs.recover_interrupted_jobs()
        details = jobs.get_job(job["id"])
        self.assertEqual(details["status"], "interrupted")
        self.assertIn("restart", details["message"])
        replacement = self.job()
        self.assertNotEqual(replacement["id"], job["id"])

    def test_log_pagination_has_no_missing_or_repeated_entries(self):
        job = self.job()
        with connection() as db:
            db.executemany("INSERT INTO deployment_job_logs(job_id,created_at,stage,level,message) VALUES(?,?,?,?,?)",
                           [(job["id"], jobs.now(), "build", "info", f"line {i}") for i in range(505)])
        self.authenticate()
        first = self.client.get(f"/api/deployment-jobs/{job['id']}").json()
        second = self.client.get(f"/api/deployment-jobs/{job['id']}?after={first['next_cursor']}").json()
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        self.assertEqual(len(first["logs"]) + len(second["logs"]), 505)
        self.assertEqual(second["logs"][0]["message"], "line 500")

    def test_log_limit_does_not_prevent_final_result(self):
        job = self.job()
        with connection() as db:
            db.execute("UPDATE deployment_jobs SET log_bytes=? WHERE id=?", (jobs.MAX_LOG_BYTES - 1, job["id"]))
        def work():
            jobs.log("large output")
            jobs.log("more output")
            return {"id": "app"}
        jobs.run_job(job["id"], work)
        self.authenticate()
        data = self.client.get(f"/api/deployment-jobs/{job['id']}").json()
        self.assertEqual(data["status"], "success")
        self.assertTrue(any("Log limit reached" in line["message"] for line in data["logs"]))

    def test_build_stream_redacts_secret_split_across_docker_chunks(self):
        job = self.job()
        events = [{"stream": "RUN secret=database-"}, {"stream": "secret\n"}, {"error": "npm build exited 1"}]
        engine = SimpleNamespace(api=SimpleNamespace(build=lambda **kw: iter(events)))
        def work():
            jobs.stage("build", "Building")
            applications.build_image(engine, Path("/tmp"), "example:test")
        jobs.run_job(job["id"], work, ["database-secret"])
        self.authenticate()
        data = self.client.get(f"/api/deployment-jobs/{job['id']}").json()
        self.assertEqual(data["status"], "failed")
        self.assertIn("npm build exited 1", data["message"])
        self.assertNotIn("database-secret", str(data))
        self.assertTrue(any("[redacted]" in line["message"] for line in data["logs"]))

    def test_zip_upload_is_staged_before_request_file_is_closed(self):
        self.authenticate()
        submitted = []
        def capture(job, work, secrets, cleanup):
            submitted.append((work, cleanup))
        with patch.object(jobs, "submit_job", side_effect=capture):
            response = self.client.post("/api/deployment-jobs/zip", data={"name": "zip-test"}, files={"file": ("app.zip", b"not a valid zip", "application/zip")})
        self.assertEqual(response.status_code, 202)
        jobs.run_job(response.json()["id"], submitted[0][0], cleanup=submitted[0][1])
        self.assertEqual(jobs.get_job(response.json()["id"])["status"], "failed")
        self.assertIn("ZIP", jobs.get_job(response.json()["id"])["message"])

    def test_redeploy_redacts_environment_changed_after_queueing(self):
        import json
        job = self.job()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_text("fastapi\n")
            with connection() as db:
                db.execute("INSERT OR REPLACE INTO applications(id,name,source,framework,port,status,created_at,env_json) VALUES(?,?,?,?,?,?,?,?)",
                           ("secret-race-app", "secret-race", "ZIP upload", "FastAPI", 8000, "running", jobs.now(), json.dumps({"PASSWORD": "new-execution-secret"})))
            engine = SimpleNamespace(api=SimpleNamespace(build=lambda **kw: iter([{"error": "failed new-execution-secret"}])))
            with patch.object(applications, "client", return_value=engine):
                jobs.run_job(job["id"], lambda: applications.redeploy_tree("secret-race-app", root, "ZIP upload"), ["old-queued-secret"])
        self.authenticate()
        data = self.client.get(f"/api/deployment-jobs/{job['id']}").json()
        self.assertEqual(data["status"], "failed")
        self.assertNotIn("new-execution-secret", str(data))
        self.assertIn("[redacted]", str(data))


if __name__ == "__main__":
    unittest.main()
