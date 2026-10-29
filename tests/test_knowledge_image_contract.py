"""005 image readiness probes on real handlers, not image feature acceptance.

Account bootstrap reuses the existing 005 fixture. No successful image objects
are seeded. PDF controls prove only existing content/permission/event behavior.
"""

import hashlib
import io
import json
import os
from contextlib import closing
from pathlib import Path
from unittest import TestCase
from uuid import uuid4

import cv2
import numpy as np

from backend.app import create_app
from backend.shared.db import connect
from tests import test_knowledge_integration as integration

PDF1 = b"%PDF-1.4\n% knowledge image contract control v1\n%%EOF"
PDF2 = b"%PDF-1.4\n% knowledge image contract control v2\n%%EOF"


def redacted(value):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key in {"password", "csrf_token", "storage_key"}
                else redacted(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redacted(item) for item in value]
    return value


class KnowledgeImageContractTest(TestCase):
    def login(self, client, number):
        client.actor = number
        integration.KnowledgeIntegrationTest.login(self, client, number)

    def setUp(self):
        self.records, self.observations = [], []
        integration.KnowledgeIntegrationTest.setUp(self)
        self.app.config["UPLOAD_ROOT"] = str(Path(self.temporary.name) / "uploads")
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.save_evidence)
        teacher_id = self.call(self.teacher, "GET", "/auth/session").json["data"]["user"]["id"]
        outsider_id = self.call(self.outsider, "GET", "/auth/session").json["data"]["user"]["id"]
        self.other_course = self.call(self.admin, "POST", "/courses", {
            "title": "Other image contract course", "teacher_id": teacher_id}, 201).json["data"]["id"]
        self.call(self.teacher, "POST", f"/courses/{self.other_course}/members", {
            "user_id": outsider_id, "member_role": "student"}, 201)
        self.other_chapter = self.call(self.teacher, "POST", f"/courses/{self.other_course}/chapters", {
            "title": "Other chapter"}, 201).json["data"]["id"]

    def save_evidence(self):
        target = os.environ.get("KNOWLEDGE_IMAGE_EVIDENCE_DIR")
        if not target:
            return
        with closing(connect(self.path)) as db:
            facts = {name: [dict(row) for row in db.execute(f"SELECT * FROM {name} ORDER BY id")]
                     for name in ("knowledge_point", "resource", "resource_version", "resource_event")}
            facts["files"] = [dict(row) for row in db.execute(
                "SELECT id,media_type,size_bytes,sha256,purpose FROM file_object ORDER BY id")]
            facts["integrity_check"] = db.execute("PRAGMA integrity_check").fetchone()[0]
            facts["foreign_key_check"] = [list(row) for row in db.execute("PRAGMA foreign_key_check")]
        output = Path(target)
        output.mkdir(parents=True, exist_ok=True)
        (output / f"{self._testMethodName}.json").write_text(json.dumps({
            "layer": "real Flask handlers/SQLite; no browser or successful image integration",
            "fixtures": "admin/teacher bootstrap; generated 2x3 PNG/JPEG; short PDF type controls",
            "requests": self.records, "contract_observations": self.observations,
            "final_facts": facts}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def call(self, client, method, path, data=None, status=200, *, upload=None, headers=None):
        options = {"headers": {"Origin": integration.ORIGIN,
                               "X-CSRF-Token": getattr(client, "csrf", ""), **(headers or {})}}
        request_body = data
        if upload:
            name, mime, content = upload
            options["data"] = {**(data or {}), "file": (io.BytesIO(content), name, mime)}
            request_body = {**(data or {}), "file": {"name": name, "mime": mime,
                            "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}}
        elif method not in {"GET", "HEAD"}:
            options["json"] = data
        response = client.open("/api/v1" + path, method=method, **options)
        raw = response.get_data()
        actual = response.json if response.is_json else {"size": len(raw),
                                                         "sha256": hashlib.sha256(raw).hexdigest()}
        self.records.append({"actor": getattr(client, "actor", "bootstrap/anonymous"),
                             "method": method, "path": path, "request": redacted(request_body),
                             "status": response.status_code, "expected_status": status,
                             "response": redacted(actual), "headers": headers or {}})
        response.close()
        if status is not None:
            self.assertEqual(response.status_code, status, self.records[-1])
        return response

    def pdf(self):
        return self.call(self.teacher, "POST", self.course + "/resources", {
            "title": "PDF type control", "kind": "guide", "chapter_id": str(self.chapter_id)},
            201, upload=("control.pdf", "application/pdf", PDF1)).json["data"]

    def content(self, client, version, event, intent="view", status=200, method="GET", headers=None):
        return self.call(client, method,
                         f"/resource-versions/{version}/content?intent={intent}&event_id={event}",
                         status=status, headers=headers)

    def counts(self):
        with closing(connect(self.path)) as db:
            return tuple(db.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
                         for name in ("resource", "resource_version", "file_object", "resource_event"))

    def test_png_jpeg_uploads_and_new_versions_are_currently_blocked(self):
        control = self.pdf()
        before = self.counts()
        for extension, mime in ((".png", "image/png"), (".jpg", "image/jpeg")):
            ok, encoded = cv2.imencode(extension, np.zeros((2, 3, 3), dtype=np.uint8))
            self.assertTrue(ok)
            self.assertEqual(cv2.imdecode(encoded, cv2.IMREAD_COLOR).shape, (2, 3, 3))
            content = encoded.tobytes()
            for kind in ("slides", "guide", "video", "question_bank"):
                with self.subTest(mime=mime, kind=kind):
                    response = self.call(self.teacher, "POST", self.course + "/resources", {
                        "title": "PNG/JPEG readiness", "kind": kind}, 415,
                        upload=("probe" + extension, mime, content))
                    self.assertEqual(response.json["error"]["code"], "UNSUPPORTED_MEDIA")
            self.call(self.teacher, "POST", f"/resources/{control['resource_id']}/versions", {},
                      415, upload=("probe" + extension, mime, content))
        self.assertEqual(self.counts(), before)
        self.observations.append({"capability": "real PNG/JPEG create and version upload",
                                  "status": "blocked", "reason": "no allowed image MIME in any current kind"})

    def test_markup_persists_without_images_urls_or_attributes_after_relogin(self):
        source = ('<p class="x" onclick="x()">PC<sup>2</sup></p>'
                  '<img src="https://invalid.example/p.png" onerror="x()">'
                  '<img src="data:image/png;base64,AAAA"><a href="/resource-versions/1/content">图</a>')
        body = {"content": source, "example": '<p style="color:red">A<sub>0</sub></p>'}
        first = self.call(self.teacher, "PATCH", self.detail, body).json["data"]
        self.assertEqual(first["content"], "<p>PC<sup>2</sup></p>图")
        self.assertEqual(first["example"], "<p>A<sub>0</sub></p>")
        self.assertEqual(self.call(self.teacher, "PATCH", self.detail, body).json["data"], first)
        self.call(self.student, "POST", "/auth/logout", status=204)
        self.login(self.student, "T005STUD1")
        # A new application reads the persisted DB, with the original real session cookie.
        restarted = create_app({"TESTING": True, "DATABASE_PATH": str(self.path),
                               "SECRET_KEY": self.app.config["SECRET_KEY"], "APP_ORIGIN": integration.ORIGIN})
        reader = restarted.test_client()
        reader.actor = "T005STUD1/restarted-app"
        reader.set_cookie("cpu_session", self.student.get_cookie("cpu_session").value)
        after = self.call(reader, "GET", self.detail).json["data"]
        for key in ("content", "example", "content_revision"):
            self.assertEqual(after[key], first[key])
        self.assertEqual(self.counts(), (0, 0, 0, 0))

    def test_unknown_image_fields_fail_atomically_and_roles_remain_enforced(self):
        before = self.call(self.teacher, "GET", self.detail).json["data"]
        for field, value in (("images", []), ("resource_version_ids", [1]),
                             ("image_url", "https://invalid.example/a.png")):
            self.call(self.teacher, "PATCH", self.detail, {"title": "must not persist", field: value}, 400)
            self.call(self.teacher, "POST", f"/chapters/{self.chapter_id}/knowledge-points", {
                "title": "must not create", "content": "text", "published": False, field: value}, 400)
        self.assertEqual(self.call(self.teacher, "GET", self.detail).json["data"], before)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM knowledge_point").fetchone()[0], 1)
        self.call(self.student, "PATCH", self.detail, {"content": "forbidden"}, 403)
        self.call(self.outsider, "GET", self.detail, status=404)
        self.call(self.outsider, "PATCH", self.detail, {"content": "cross course"}, 404)
        self.call(self.teacher, "PATCH", self.detail, {"published": False})
        self.call(self.student, "GET", self.detail, status=404)
        self.call(self.teacher, "PATCH", self.detail, {"published": True})
        self.call(self.teacher, "DELETE", self.course + f"/members/{self.student_id}", status=204)
        self.call(self.student, "GET", self.detail, status=404)
        self.call(self.student, "PATCH", self.detail, {"title": "revoked"}, 404)

    def test_pdf_control_fixed_versions_current_permissions_and_revocation(self):
        control = self.pdf()
        v1, resource = control["id"], control["resource_id"]
        v2 = self.call(self.teacher, "POST", f"/resources/{resource}/versions", {}, 201,
                       upload=("control-v2.pdf", "application/pdf", PDF2)).json["data"]["id"]
        self.assertEqual(self.content(self.student, v1, str(uuid4())).data, PDF1)
        self.assertEqual(self.content(self.student, v2, str(uuid4())).data, PDF2)
        self.content(self.outsider, v1, str(uuid4()), status=404)
        before = self.counts()
        self.call(self.teacher, "POST", self.course + "/resources", {
            "title": "cross course chapter", "kind": "guide", "chapter_id": str(self.other_chapter)},
            404, upload=("a.pdf", "application/pdf", PDF1))
        self.assertEqual(self.counts(), before)
        self.call(self.student, "POST", self.course + "/resources", {
            "title": "forbidden", "kind": "guide"}, 403, upload=("a.pdf", "application/pdf", PDF1))
        before = self.counts()
        self.call(self.teacher, "PATCH", f"/resources/{resource}", {"visibility": "teacher_only"})
        self.content(self.student, v1, str(uuid4()), status=404)
        self.call(self.student, "GET", f"/resources/{resource}/versions", status=404)
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.content(self.teacher, v1, str(uuid4())).data, PDF1)
        self.call(self.teacher, "PATCH", f"/resources/{resource}", {"visibility": "students"})
        self.call(self.teacher, "DELETE", self.course + f"/members/{self.student_id}", status=204)
        before = self.counts()
        self.content(self.student, v1, str(uuid4()), status=404)
        self.assertEqual(self.counts(), before)

    def test_pdf_control_retries_range_conflicts_and_non_content_responses(self):
        control = self.pdf()
        version, event = control["id"], str(uuid4())
        path = f"/resource-versions/{version}/content?intent=view&event_id={event}"
        self.content(self.student, version, event, method="HEAD")
        self.assertEqual(self.counts()[-1], 0)
        first = self.content(self.student, version, event)
        self.assertEqual(self.content(self.student, version, event).data, first.data)
        partial = self.content(self.student, version, event, status=206, headers={"Range": "bytes=0-7"})
        self.assertEqual(partial.data, PDF1[:8])
        self.content(self.student, version, str(uuid4()), status=304, headers={"If-None-Match": first.headers["ETag"]})
        self.content(self.student, version, str(uuid4()), status=416, headers={"Range": "bytes=9999-10000"})
        self.content(self.student, version, event, intent="download", status=409)
        v2 = self.call(self.teacher, "POST", f"/resources/{control['resource_id']}/versions", {}, 201,
                       upload=("v2.pdf", "application/pdf", PDF2)).json["data"]["id"]
        self.content(self.student, v2, event, status=409)
        self.assertEqual(self.counts()[-1], 1)
        self.call(self.student, "GET", path.replace("intent=view", "intent=invalid"), status=400)
        self.call(self.student, "GET", path.replace(f"event_id={event}", "event_id="), status=400)
        # Observation only: expected contract status is not rewritten to the observed status.
        probe = self.content(self.student, version, "not-a-uuid", status=None)
        self.observations.append({"capability": "APIC event_id UUID validation", "expected_status": 400,
                                  "actual_status": probe.status_code,
                                  "status": "passed" if probe.status_code == 400 else "contract_failure"})

    def test_pdf_control_missing_file_and_archived_resource_fail_closed(self):
        control = self.pdf()
        # Fault/state injection: 003 currently has no archive HTTP operation.
        with closing(connect(self.path)) as db:
            db.execute("UPDATE resource SET archived=1 WHERE id=?", (control["resource_id"],))
        self.content(self.student, control["id"], str(uuid4()), status=404)
        with closing(connect(self.path)) as db:
            db.execute("UPDATE resource SET archived=0 WHERE id=?", (control["resource_id"],))
            key = db.execute("SELECT storage_key FROM file_object WHERE id=(SELECT file_id "
                             "FROM resource_version WHERE id=?)", (control["id"],)).fetchone()[0]
        (Path(self.app.config["UPLOAD_ROOT"]) / key).unlink()
        self.content(self.student, control["id"], str(uuid4()), status=404)
        self.assertEqual(self.counts()[-1], 0)
