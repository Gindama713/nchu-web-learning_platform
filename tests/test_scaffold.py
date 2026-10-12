"""Smoke check that distinguishes a running API from a ready grader."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import TestCase
from unittest.mock import patch

from backend.app import app


class ScaffoldTest(TestCase):
    def test_health_and_catalog(self):
        with NamedTemporaryFile(dir=Path(__file__).parent, delete=False) as temporary:
            database = Path(temporary.name)
        try:
            with patch.dict("os.environ", {"DATABASE_PATH": str(database)}):
                client = app.test_client()
                health = client.get("/api/v1/health")
                self.assertEqual(health.status_code, 503)
                self.assertTrue(health.json["data"]["db_ready"])
                self.assertFalse(health.json["data"]["grader_ready"])
                catalog = client.get("/api/v1/modules")
                self.assertEqual(catalog.status_code, 200)
                self.assertEqual(catalog.json["data"][-2]["spec"], "SPEC-018")
        finally:
            database.unlink(missing_ok=True)
