import os
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

_runtime = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = str(Path(_runtime.name) / "data")
os.environ["WORKSPACE_DIR"] = str(Path(_runtime.name) / "workspace")
os.environ["STORAGE_DIR"] = str(Path(_runtime.name) / "storage")

from app.api import applications  # noqa: E402
from fastapi import HTTPException  # noqa: E402


class ApplicationDetectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def write_dockerfile(self, contents: str):
        (self.root / "Dockerfile").write_text(contents)

    def assert_expose_error(self, contents: str):
        self.write_dockerfile(contents)
        with self.assertRaises(HTTPException) as raised:
            applications.detect_framework(self.root)
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("EXPOSE <port>", raised.exception.detail)
        return raised.exception

    def test_dockerfile_detection_uses_final_stage_exposed_port(self):
        self.write_dockerfile(
            "FROM node:24 AS builder\n"
            "EXPOSE 3000\n"
            "FROM python:3.11-slim AS runtime\n"
            "EXPOSE 8000\n"
        )

        self.assertEqual(
            applications.detect_framework(self.root),
            ("Dockerfile", 8000, "dockerfile"),
        )

    def test_dockerfile_detection_accepts_case_whitespace_comments_and_tcp_suffix(self):
        self.write_dockerfile(
            "FROM python:3.11-slim\n"
            "  expose   8000/tcp   # application port\n"
        )

        self.assertEqual(
            applications.detect_framework(self.root),
            ("Dockerfile", 8000, "dockerfile"),
        )

    def test_dockerfile_detection_rejects_variable_port(self):
        self.assert_expose_error(
            "FROM python:3.11-slim\n"
            "ENV PORT=8000\n"
            "EXPOSE ${PORT}\n"
        )

    def test_dockerfile_detection_rejects_missing_tcp_port(self):
        self.assert_expose_error(
            "FROM python:3.11-slim\n"
            "EXPOSE 8125/udp\n"
        )

    def test_dockerfile_detection_rejects_multiple_tcp_ports(self):
        error = self.assert_expose_error(
            "FROM python:3.11-slim\n"
            "EXPOSE 8000 9000/tcp\n"
        )
        self.assertIn("one TCP port", error.detail)

    def test_existing_framework_detection_is_unchanged_without_dockerfile(self):
        (self.root / "requirements.txt").write_text("fastapi==0.115.12\n")

        self.assertEqual(
            applications.detect_framework(self.root),
            ("FastAPI", 8000, "python"),
        )


if __name__ == "__main__":
    unittest.main()
