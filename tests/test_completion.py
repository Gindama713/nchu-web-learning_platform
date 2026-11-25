"""Regressions for clock conversion, public templates and authorized knowledge images."""

import json
import threading
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import cv2
import numpy as np
from flask import Flask, has_app_context

from backend import runtime, worker
from backend.engines import grading
from backend.models.grading import template_for, validate_cases, validate_port_schema
from backend.models.grading_templates import template
from backend.shared.db import migrate
from tests import test_knowledge_integration as knowledge_fixture

ORIGIN = knowledge_fixture.ORIGIN


class WorkerLifecycleTest(TestCase):
    def test_web_scanner_keeps_application_context(self):
        app = Flask(__name__)
        app.config["DATABASE_PATH"] = "unused-for-probe.db"
        observed = threading.Event()
        contexts = []
        def probe(_path):
            contexts.append(has_app_context())
            observed.set()
        with patch.object(grading, "scan_once", side_effect=probe), patch("backend.operations.maintenance_tick"):
            thread = grading.start_scanner(app)
            try:
                self.assertTrue(observed.wait(7), "Background scanner stopped unexpectedly")
                self.assertEqual(contexts, [True])
            finally:
                app.extensions["grading_scanner_stop"].set()
                thread.join(timeout=1)

    def test_cold_boot_always_selftests_and_singleton_lock_releases(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "worker.db"
            migrate(database)
            with patch.object(worker.time, "monotonic", return_value=1), \
                    patch.object(runtime, "check_engine", return_value={"ready": True}) as selftest:
                worker.consume(database, directory, threading.Event(), once=True)
                selftest.assert_called_once()
            self.assertEqual(runtime.load_state(database, "worker")["state"], "stopped")
            with worker.singleton(database), self.assertRaises(OSError), worker.singleton(database):
                self.fail("A second worker must not run")
            with worker.singleton(database):
                pass  # Closing/crashing the old process releases the OS lock.


class ClockTemplateTest(TestCase):
    def test_templates_and_stabilized_edges_use_the_real_vector_contract(self):
        for code in ("EXP-01", "EXP-02", "EXP-04"):
            preset = template(code)
            schema = preset["profile"]["port_schema"]
            validate_port_schema(schema)
            validate_cases(preset["cases"], template_for(code)[0], schema)
            self.assertEqual({c["group_code"] for c in preset["cases"]}, set(template_for(code)[0]))
        steps = [{"step_no": 1, "inputs": {"D": 90}, "expected": {"Q": 90}, "clock_event": "rising"},
                 {"step_no": 2, "inputs": {}, "expected": {"Q": 90}, "clock_event": "falling"}]
        with TemporaryDirectory() as directory:
            path = grading.write_vector_file(directory, {"id": 1, "steps_json": json.dumps(steps)}, {"D": 8, "Q": 8}, "CLK")
            rows = [row.split() for row in path.read_text().splitlines()]
        self.assertEqual(rows[0][:3], ["D[8]", "CLK", "Q[8]"])
        self.assertEqual([r[1] for r in rows[1:]], ["0x0", "0x1", "0x1", "0x0"])
        self.assertEqual([r[0] for r in rows[1:]], ["0x5A"] * 4)
        self.assertEqual(rows[1][2], "<DC>")
        self.assertEqual(rows[2][2], "0x5A")


class KnowledgeImageTest(TestCase):
    setUp = knowledge_fixture.KnowledgeIntegrationTest.setUp
    tearDown = knowledge_fixture.KnowledgeIntegrationTest.tearDown
    call = knowledge_fixture.KnowledgeIntegrationTest.call
    login = knowledge_fixture.KnowledgeIntegrationTest.login

    def test_upload_publish_relogin_authorization_and_immutable_references(self):
        self.app.config["UPLOAD_ROOT"] = str(Path(self.temporary.name) / "uploads")
        tokens = []
        for extension, media in ((".png", "image/png"), (".jpg", "image/jpeg")):
            ok, data = cv2.imencode(extension, np.full((3, 2, 3), 255, dtype=np.uint8))
            self.assertTrue(ok)
            response = self.teacher.post("/api/v1" + self.detail + "/images", data={
                "file": (BytesIO(data.tobytes()), "diagram" + extension, media)},
                headers={"Origin": ORIGIN, "X-CSRF-Token": self.teacher.csrf})
            self.assertEqual(response.status_code, 201, response.json)
            image = response.json["data"]
            tokens.append(image["token"])
            self.assertEqual(self.student.get(image["url"]).status_code, 404)  # not yet in published content
        self.call(self.teacher, "PATCH", self.detail, {"content": "<p>图文讲解</p>" + "\n".join(tokens)})
        self.login(self.student, "T005STUD1")
        detail = self.call(self.student, "GET", self.detail).json["data"]
        self.assertIn('src="/api/v1/knowledge-points/', detail["content_html"])
        self.assertIn(tokens[0], detail["content"])
        response = self.student.get(image["url"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        response.close()
        self.assertEqual(self.outsider.get(image["url"]).status_code, 404)
        other = self.call(self.teacher, "POST", f"/chapters/{self.chapter_id}/knowledge-points",
                          {"title": "其他知识点", "content": "text", "published": True}, 201).json["data"]
        self.call(self.teacher, "PATCH", f"/knowledge-points/{other['id']}", {"content": tokens[0]}, 400)
        self.call(self.teacher, "PATCH", self.detail, {"published": False})
        self.assertEqual(self.student.get(image["url"]).status_code, 404)
        self.call(self.teacher, "PATCH", self.detail, {"published": True})
        response = self.student.get(image["url"])
        self.assertEqual(response.status_code, 200)
        response.close()
        # External markup remains stripped, and arbitrary file IDs cannot become authorized images.
        self.call(self.teacher, "PATCH", self.detail, {"content": "[[image:999999]]"}, 400)
        self.call(self.teacher, "PATCH", self.detail, {"content": '<img src="https://example.com/a.png" onerror="x()">正文'})
        self.assertNotIn("<img", self.call(self.student, "GET", self.detail).json["data"]["content_html"])
