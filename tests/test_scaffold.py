"""Smoke check that distinguishes a running API from a ready grader."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import TestCase

from backend.app import create_app
from backend.shared.db import migrate


class ScaffoldTest(TestCase):
    def test_health_and_catalog(self):
        with NamedTemporaryFile(dir=Path(__file__).parent, delete=False) as temporary:
            database = Path(temporary.name)
        try:
            migrate(database)
            app = create_app({"TESTING": True, "DATABASE_PATH": str(database)})
            with app.test_client() as client:
                health = client.get("/api/v1/health")
                self.assertEqual(health.status_code, 503)
                self.assertTrue(health.json["data"]["db_ready"])
                self.assertFalse(health.json["data"]["grader_ready"])
                catalog = client.get("/api/v1/modules")
                self.assertEqual(catalog.status_code, 200)
                self.assertEqual(catalog.json["data"][-2]["spec"], "SPEC-018")
        finally:
            database.unlink(missing_ok=True)
