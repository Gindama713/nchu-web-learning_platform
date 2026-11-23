"""Exercise real backup/restore, maintenance, cleanup and failed log retry."""

import json
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from backend import operations, runtime
from backend.apis import logs
from backend.app import create_app
from backend.engines import grading
from backend.shared.api import ApiError
from backend.shared.db import connect, migrate, write


class OperationsTest(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / "live.db"
        self.uploads = self.root / "uploads"
        self.uploads.mkdir()
        migrate(self.database)
        self.at = datetime(2026, 11, 23, 8, tzinfo=UTC)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.database),
                               "UPLOAD_ROOT": str(self.uploads), "SECRET_KEY": "ops-test-secret", "TEST_NOW": self.at})
        self.runner = self.app.test_cli_runner()
        with closing(connect(self.database)) as db:
            db.execute("INSERT INTO user(id,student_no,name,password_hash,role,created_at,updated_at) "
                       "VALUES(1,'TEST0001','Student','not-used','student',?,?)", (self.at.isoformat(), self.at.isoformat()))
            for key, content, purpose in (("resource-file", b"course-resource", "resource:guide"),
                                          ("circuit-file", b"circuit-source", "submission")):
                file = self.uploads / key
                file.write_bytes(content)
                db.execute("INSERT INTO file_object(owner_id,storage_key,original_name,media_type,size_bytes,sha256,"
                           "purpose,created_at) VALUES(1,?,?,'application/octet-stream',?,?,?,?)",
                           (key, key, len(content), operations.sha256(file), purpose, self.at.isoformat()))

    def tearDown(self):
        with logs._pending_lock:
            logs._buffers.pop(str(self.database.resolve()), None)
        self.temporary.cleanup()

    def test_backup_restore_and_maintenance_are_real_and_fail_closed(self):
        backup, restored = self.root / "backup", self.root / "restored"
        result = self.runner.invoke(args=["backup", "create", "--destination", str(backup)])
        self.assertNotEqual(result.exit_code, 0)
        self.assertFalse(backup.exists())
        self.assertEqual(self.runner.invoke(args=["maintenance", "on"]).exit_code, 0)
        client = self.app.test_client()
        for method, path in (("GET", "/api/v1/modules"), ("POST", "/api/v1/auth/login")):
            response = client.open(path, method=method, json={})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json["error"]["code"], "MAINTENANCE")
        self.assertEqual(client.get("/api/v1/health").json["data"]["status"], "maintenance")
        with self.app.app_context(), closing(connect(self.database)) as db, \
                patch.object(grading, "reclaim_expired", side_effect=AssertionError("Must not claim")):
            self.assertIsNone(grading.claim_run(db, self.at))
            self.assertIsNone(grading.claim_validation(db, self.at))
            with self.assertRaises(ApiError) as blocked, write(db):
                self.fail("Business write must be blocked even outside the HTTP guard")
            self.assertEqual(blocked.exception.code, "MAINTENANCE")
        result = self.runner.invoke(args=["backup", "create", "--destination", str(backup)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(len(json.loads(result.output)["files"]), 2)
        result = self.runner.invoke(args=["backup", "restore", "--directory", str(backup), "--destination", str(restored)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(operations.in_maintenance(restored / "app.db"))
        self.assertEqual((restored / "uploads" / "circuit-file").read_bytes(), b"circuit-source")
        self.assertEqual(len(operations.check_database(restored / "app.db")), 2)
        # No overwrite, and tampered archives never produce a restore directory.
        self.assertNotEqual(self.runner.invoke(args=["backup", "restore", "--directory", str(backup),
                                                    "--destination", str(restored)]).exit_code, 0)
        (backup / "uploads" / "resource-file").write_bytes(b"tampered")
        failed = self.runner.invoke(args=["backup", "restore", "--directory", str(backup),
                                          "--destination", str(self.root / "failed")])
        self.assertNotEqual(failed.exit_code, 0)
        self.assertFalse((self.root / "failed").exists())
        self.assertTrue(operations.in_maintenance(self.database))
        self.assertEqual(self.runner.invoke(args=["maintenance", "off"]).exit_code, 0)
        self.assertEqual(client.get("/api/v1/modules").status_code, 200)

    def test_cleanup_is_bounded_and_keeps_audit_and_valid_sessions(self):
        old = (self.at - timedelta(days=100)).isoformat().replace("+00:00", "Z")
        future = (self.at + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        with closing(connect(self.database)) as db:
            for index, expiry in enumerate((old, old, old, future)):
                db.execute("INSERT INTO session(token_hash,user_id,csrf_hash,session_version,expires_at,last_seen_at,created_at) "
                           "VALUES(?,1,'csrf',0,?,?,?)", (str(index), expiry, old, old))
                db.execute("INSERT INTO access_log(method,path,status,duration_ms,at) VALUES('GET','/help',200,1,?)",
                           (old if index < 3 else future,))
            db.execute("INSERT INTO audit_event(action,object_type,request_id,created_at) VALUES('keep','user','test',?)", (old,))
        result = self.runner.invoke(args=["cleanup", "--batch-size", "2"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.output)["expired_sessions_deleted"], 2)
        with closing(connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM session").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM access_log").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_event").fetchone()[0], 1)
        self.assertNotEqual(self.runner.invoke(args=["cleanup", "--retention-days", "30"]).exit_code, 0)
        self.app.config["AUTO_CLEANUP"] = True
        operations.maintenance_tick(self.app)
        with closing(connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM session").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM access_log").fetchone()[0], 1)
        self.assertGreater(self.app.extensions["cleanup_due"], time.monotonic())

    def test_failed_access_batch_retries_atomically_and_is_bounded(self):
        with self.app.test_request_context("/help"):
            with patch("backend.apis.logs.sqlite3.connect", side_effect=sqlite3.OperationalError("busy")):
                logs.write_access(200, 1)
            self.assertEqual(logs.buffer_status(), {"pending": 1, "flush_failures": 1, "dropped": 0})
            logs.flush_access(force=True)
            self.assertEqual(logs.buffer_status()["pending"], 0)
            with closing(connect(self.database)) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM access_log").fetchone()[0], 1)
            with patch.object(logs, "MAX_PENDING_ROWS", 2), patch.object(logs, "flush_access"):
                for _ in range(5):
                    logs.write_access(200, 1)
            self.assertEqual(logs.buffer_status()["pending"], 2)
            self.assertEqual(logs.buffer_status()["dropped"], 3)

    def test_health_needs_real_identity_selftest_and_fresh_worker(self):
        identity = ("pinned.jar", 12, 34)
        with patch.object(runtime, "jar_identity", return_value=identity), \
                patch.object(runtime, "verified_jar", return_value=True):
            runtime.save_state(self.database, "engine", {"ready": True, "identity": list(identity), "at": time.time()})
            self.assertFalse(runtime.health_details(self.database)["grader_ready"])
            runtime.publish_worker_status(self.database, "test-worker", "idle")
            self.assertTrue(runtime.health_details(self.database)["grader_ready"])
            runtime.save_state(self.database, "worker", {"worker_id": "test-worker", "state": "idle",
                                                         "at": time.time() - runtime.HEARTBEAT_SECONDS - 1})
            self.assertFalse(runtime.health_details(self.database)["worker_ready"])
            runtime.publish_worker_status(self.database, "test-worker", "stopped")
            self.assertFalse(runtime.health_details(self.database)["worker_ready"])
        with patch.dict("os.environ", {"LOGISIM_JAR_PATH": str(self.uploads / "resource-file")}):
            self.assertFalse(grading.grader_ready())
            self.assertNotEqual(self.runner.invoke(args=["engine-check"]).exit_code, 0)

    def test_backup_safety_and_maintenance_lock(self):
        with self.app.app_context():
            operations.maintenance_path(self.database).touch()
            with operations.operation_lock(self.database):
                self.assertNotEqual(self.runner.invoke(args=["maintenance", "off"]).exit_code, 0)
                self.assertTrue(operations.in_maintenance(self.database))
            with self.assertRaises(ValueError):
                operations.file_path(self.uploads, "../live.db")
            (self.uploads / "circuit-file").unlink()
            with self.assertRaises(OSError):
                operations.create_backup(self.database, self.uploads, self.root / "bad-backup")
            self.assertFalse((self.root / "bad-backup").exists())
            self.assertTrue(operations.in_maintenance(self.database))
