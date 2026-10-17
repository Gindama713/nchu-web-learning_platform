"""005 consumption seams on merged 001/003/009/017/010C, not full I-01.

Only admin/teacher accounts are bootstrapped. Successful business objects use
real APIs. Known teammate contract failures remain expected failures, not passes.
Set I01_EVIDENCE_DIR to retain redacted requests and read-only database facts.
"""

import base64
import copy
import hashlib
import io
import json
import os
import secrets
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, expectedFailure
from uuid import uuid4

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.engines.wiring import _make_panel
from backend.shared.db import connect, migrate

ORIGIN = "http://127.0.0.1:5173"
NOW = datetime(2026, 10, 17, 4, tzinfo=UTC)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ioAAAAASUVORK5CYII=")
PDF1 = b"%PDF-1.4\n% I01 permitted-document control v1\n%%EOF"
PDF2 = b"%PDF-1.4\n% I01 permitted-document control v2\n%%EOF"


def redact(value):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key in {"password", "csrf_token", "storage_key"}
                else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def database_facts(path):
    tables = ("chapter", "knowledge_point", "learning_progress", "experiment",
              "experiment_version", "experiment_knowledge", "experiment_participant",
              "wiring_attempt", "wiring_action", "wiring_validation", "analysis_run",
              "resource", "resource_version", "resource_event")
    with closing(connect(path)) as db:
        facts = {name: [dict(row) for row in db.execute(f"SELECT * FROM {name}")] for name in tables}
        audit = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%audit%'").fetchall()
        for row in audit:
            name = row[0]
            facts[name] = [dict(item) for item in db.execute(f'SELECT * FROM "{name}"')]
        facts["file_objects"] = [dict(row) for row in db.execute(
            "SELECT id,owner_id,original_name,media_type,size_bytes,sha256,purpose FROM file_object ORDER BY id")]
        facts["foreign_key_check"] = [list(row) for row in db.execute("PRAGMA foreign_key_check")]
        facts["integrity_check"] = db.execute("PRAGMA integrity_check").fetchone()[0]
    return redact(facts)


def wire_actions(swapped=False):
    pairs = [("sw_b_out" if swapped else "sw_a_out", "alu_a"),
             ("sw_a_out" if swapped else "sw_b_out", "alu_b"),
             ("sw_op_out", "alu_op"), ("alu_y", "led_y_in"),
             ("alu_z", "led_z_in"), ("alu_c", "led_c_in")]
    return [{"seq": index, "type": "connect", "payload": {
        "id": f"w{index}", "from_terminal": source, "to_terminal": target}}
        for index, (source, target) in enumerate(pairs, 1)]


class KnowledgeI01SeamsTest(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="i01-handlers-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "course.db"
        self.records, self.stages = [], {}
        self.password = secrets.token_urlsafe(24)
        migrate(self.path)
        self.app = create_app({"TESTING": True, "TEST_NOW": NOW, "DATABASE_PATH": str(self.path),
                               "UPLOAD_ROOT": str(Path(self.temporary.name) / "uploads"),
                               "SECRET_KEY": secrets.token_hex(32), "APP_ORIGIN": ORIGIN})
        if getattr(self, "observe_app", None):
            self.observe_app(self.app)
        with closing(connect(self.path)) as db:
            for number, role in (("I01ADMIN", "admin"), ("I01TEACH", "teacher")):
                db.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                           "VALUES(?,?,?,?,1,?,?)", (number, number, generate_password_hash(self.password),
                                                    role, NOW.isoformat(), NOW.isoformat()))
        self.admin, self.teacher, *self.students = [self.app.test_client() for _ in range(6)]
        for client, number in ((self.admin, "I01ADMIN"), (self.teacher, "I01TEACH")):
            self.login(client, number)
        for index, student in enumerate(self.students, 1):
            number = f"I01STUD{index}"
            self.call(student, "POST", "/auth/register", {
                "student_no": number, "name": number, "password": self.password}, 201)
            self.login(student, number)
        self.course = self.call(self.admin, "POST", "/courses", {
            "title": "I01 CPU", "teacher_id": self.uid(self.teacher)}, 201).json["data"]["id"]
        self.base = f"/courses/{self.course}"
        for student in self.students:
            self.call(self.teacher, "POST", self.base + "/members", {
                "user_id": self.uid(student), "member_role": "student"}, 201)
        self.chapter = self.call(self.teacher, "POST", self.base + "/chapters", {
            "title": "I01 ALU"}, 201).json["data"]["id"]
        self.points = [self.call(self.teacher, "POST", f"/chapters/{self.chapter}/knowledge-points", {
            "title": title, "content": "<p>ALU 算术逻辑单元</p>", "published": published}, 201).json["data"]
            for title, published in (("I01 ALU", True), ("I01 进位", True), ("I01 草稿", False))]

    def tearDown(self):
        target = os.environ.get("I01_EVIDENCE_DIR")
        if target:
            output = Path(target)
            output.mkdir(parents=True, exist_ok=True)
            (output / f"{self._testMethodName}.json").write_text(json.dumps({
                "layer": "real Flask handlers/SQLite", "fixtures": "admin/teacher bootstrap and TEST_NOW only",
                "requests": self.records, "stages": self.stages,
                "final_facts": database_facts(self.path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def call(self, client, method, path, payload=None, status=200, headers=None, upload=None):
        options = {"headers": {"Origin": ORIGIN, "X-CSRF-Token": getattr(client, "csrf", ""),
                               **(headers or {})}}
        if upload:
            name, mime, content, fields = upload
            options["data"] = {**fields, "file": (io.BytesIO(content), name, mime)}
            request_body = {**fields, "file": {"name": name, "mime": mime, "size": len(content),
                                              "sha256": hashlib.sha256(content).hexdigest()}}
        else:
            options["json"] = payload
            request_body = payload
        response = client.open("/api/v1" + path, method=method, **options)
        raw = response.get_data()
        actual = response.json if response.is_json else {"base64": base64.b64encode(raw).decode(),
                   "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
        self.records.append({"actor": getattr(client, "actor", "anonymous"), "method": method, "path": path,
                             "request": redact(request_body), "headers": headers or {},
                             "status": response.status_code, "expected_status": status, "response": redact(actual)})
        response.close()
        if status is not None:
            self.assertEqual(response.status_code, status, self.records[-1])
        return response

    def login(self, client, number):
        client.actor = number
        client.csrf = self.call(client, "POST", "/auth/login", {
            "student_no": number, "password": self.password}).json["data"]["csrf_token"]

    def uid(self, client):
        return self.call(client, "GET", "/auth/session").json["data"]["user"]["id"]

    def experiment(self, start=None, end=None):
        exp = self.call(self.teacher, "POST", self.base + "/experiments", {
            "code": "EXP-01", "title": "I01真实ALU实验", "description": "关联同课知识"}, 201).json["data"]
        panel = _make_panel("EXP-01")
        panel["layout"] = {}
        body = {"title": "I01固定v1", "objectives": "理解算术与进位", "instructions": "连接开关与ALU和指示灯",
                "knowledge_ids": [p["id"] for p in self.points[:2]], "submission_modes": ["wiring"],
                "panel": panel, "rules": {"require_required_inputs": True}}
        version = self.call(self.teacher, "POST", f"/experiments/{exp['id']}/versions", body, 201).json["data"]
        self.call(self.teacher, "POST", f"/experiment-versions/{version['id']}/publish", {
            "start_at": (start or NOW - timedelta(hours=1)).isoformat(),
            "end_at": (end or NOW + timedelta(minutes=10)).isoformat()})
        return exp, version, body

    def attempt(self, student, version):
        return self.call(student, "POST", f"/experiment-versions/{version}/wiring-attempts", {}, 201).json["data"]

    def save(self, student, attempt, swapped=False):
        actions = wire_actions(swapped)
        state = copy.deepcopy(attempt["state"])
        state["wires"] = [a["payload"] for a in actions]
        body = {"revision": 0, "state": state, "actions": actions}
        self.call(student, "PUT", f"/wiring-attempts/{attempt['id']}", body)
        return body

    def submit(self, student, attempt, status=200):
        return self.call(student, "POST", f"/wiring-attempts/{attempt['id']}/submit", {"revision": 1}, status,
                         headers={"Idempotency-Key": str(uuid4())})

    def test_published_knowledge_fixed_experiment_facts_and_teacher_consumption(self):
        # SPEC-005/AC03/04,R38; 009/AC01/03; 017/AC05/07/10; 010C/AC01/04,R16/R21 limited consumption.
        exp, version, body = self.experiment()
        vid = version["id"]
        s1, s2, s3, s4 = self.students
        other = self.call(self.admin, "POST", "/courses", {
            "title": "I01 other course", "teacher_id": self.uid(self.teacher)}, 201).json["data"]["id"]
        other_chapter = self.call(self.teacher, "POST", f"/courses/{other}/chapters", {"title": "other"}, 201).json["data"]["id"]
        foreign = self.call(self.teacher, "POST", f"/chapters/{other_chapter}/knowledge-points", {
            "title": "other knowledge", "content": "other", "published": True}, 201).json["data"]["id"]
        self.call(s1, "GET", f"/knowledge-points/{foreign}", status=404)
        self.call(s1, "GET", f"/courses/{other}/experiments", status=404)
        self.call(self.teacher, "POST", f"/experiments/{exp['id']}/versions", {**body, "knowledge_ids": [foreign]}, 400)
        self.call(s1, "POST", f"/experiments/{exp['id']}/versions", body, 403)
        self.call(s1, "PATCH", f"/knowledge-points/{self.points[0]['id']}", {"title": "student edit"}, 403)
        self.call(self.teacher, "PUT", f"/knowledge-points/{self.points[0]['id']}/progress", {"completed": True}, 403)
        listed = self.call(s1, "GET", self.base + "/experiments").json["data"]
        selected = listed[0]["latest_version"]["id"]
        self.assertEqual(selected, vid)
        detail = self.call(s1, "GET", f"/experiment-versions/{selected}").json["data"]
        self.assertEqual(detail["knowledge_ids"], [p["id"] for p in self.points[:2]])
        for point in self.points[:2]:
            self.call(s1, "GET", f"/knowledge-points/{point['id']}")
        self.call(s1, "GET", f"/knowledge-points/{self.points[2]['id']}", status=404)
        self.call(s1, "PUT", f"/knowledge-points/{self.points[0]['id']}/progress", {"completed": True})
        a1, a2, a3 = [self.attempt(s, selected) for s in (s1, s2, s3)]
        saved = self.save(s1, a1)
        refreshed = self.call(s1, "GET", f"/wiring-attempts/{a1['id']}").json["data"]
        self.assertEqual(refreshed["state"], saved["state"])
        self.assertEqual((refreshed["revision"], refreshed["latest_seq"]), (1, 6))
        self.call(s1, "PUT", f"/wiring-attempts/{a1['id']}", saved, 409)
        self.assertTrue(self.call(s1, "POST", f"/wiring-attempts/{a1['id']}/validate", {"revision": 1}).json["data"]["valid"])
        good = self.submit(s1, a1).json["data"]
        self.assertTrue(good["completed"])
        self.assertTrue(all(row["passed"] for row in good["functional_results"]))
        self.save(s2, a2, swapped=True)
        bad = self.submit(s2, a2).json["data"]
        self.assertFalse(bad["completed"])
        self.assertTrue(any(not row["passed"] for row in bad["functional_results"]))
        for _ in range(2):
            invalid = self.call(s3, "POST", f"/wiring-attempts/{a3['id']}/validate", {"revision": 0}).json["data"]
            self.assertFalse(invalid["valid"])
        self.call(s4, "GET", f"/wiring-attempts/{a1['id']}", status=404)
        self.call(self.teacher, "GET", f"/wiring-attempts/{a1['id']}/actions")
        progress = self.call(s1, "GET", self.base + "/analytics?dimension=knowledge").json["data"]
        self.assertEqual((progress["metrics"]["completed_knowledge_count"], progress["metrics"]["published_knowledge_count"],
                          progress["metrics"]["progress"]), (1, 2, 0.5))
        self.assertEqual(progress["sample_size"], 0)
        self.app.config["TEST_NOW"] = NOW + timedelta(minutes=11)
        query = self.base + "/analytics?dimension=wiring&from=2026-10-17T00:00:00Z&to=2026-10-17T04:11:00Z"
        old = self.call(self.teacher, "GET", query).json["data"]
        self.assertEqual(old["metrics"], {"assigned_count": 4, "completed_student_count": 1,
                         "completion_rate": 0.25, "attempt_count": 2, "error_counts": {"REQUIRED_OPEN": 1}})
        old_id = old["analysis_run_id"]
        read = self.base + f"/analytics?analysis_run_id={old_id}"
        export = self.base + f"/analytics/export?analysis_run_id={old_id}&format=csv"
        csv = self.call(self.teacher, "GET", export).data
        self.assertIn(b"0.25", csv)
        self.stages["original_snapshot"] = database_facts(self.path)
        with closing(connect(self.path)) as db:
            snap = json.loads(db.execute("SELECT input_snapshot_json FROM analysis_run WHERE id=?", (old_id,)).fetchone()[0])
        self.assertEqual({a["id"] for a in snap["attempts"]}, {a1["id"], a2["id"], a3["id"]})
        raw = self.stages["original_snapshot"]["wiring_attempt"]
        self.assertEqual([(a["id"], a["status"], bool(a["completed"])) for a in raw],
                         [(a1["id"], "submitted", True), (a2["id"], "submitted", False), (a3["id"], "draft", False)])
        for entry in snap["attempts"]:
            actual = next(a for a in raw if a["id"] == entry["id"])
            self.assertTrue(all(actual[key] == value for key, value in entry.items()))
        # A later published version adds real assignments/submissions without changing v1.
        body["title"], body["knowledge_ids"] = "I01草稿v2", [self.points[1]["id"]]
        v2 = self.call(self.teacher, "POST", f"/experiments/{exp['id']}/versions", body, 201).json["data"]
        self.assertEqual(v2["version"], 2)
        self.assertEqual(self.call(s1, "GET", f"/experiment-versions/{vid}").json["data"]["knowledge_ids"], detail["knowledge_ids"])
        self.call(s1, "GET", f"/experiment-versions/{v2['id']}", status=404)
        self.call(self.teacher, "POST", f"/experiment-versions/{v2['id']}/publish", {
            "start_at": (NOW + timedelta(minutes=11)).isoformat(),
            "end_at": (NOW + timedelta(minutes=15)).isoformat()})
        new_selected = self.call(s3, "GET", self.base + "/experiments").json["data"][0]["latest_version"]["id"]
        self.assertEqual(new_selected, v2["id"])
        a4 = self.attempt(s3, new_selected)
        self.save(s3, a4)
        self.assertTrue(self.submit(s3, a4).json["data"]["completed"])
        self.call(self.teacher, "PATCH", f"/knowledge-points/{self.points[0]['id']}", {"published": False})
        self.call(s1, "GET", f"/knowledge-points/{self.points[0]['id']}", status=404)
        current_progress = self.call(s1, "GET", self.base + "/analytics?dimension=knowledge").json["data"]
        self.assertEqual((current_progress["metrics"]["completed_knowledge_count"],
                          current_progress["metrics"]["published_knowledge_count"], current_progress["metrics"]["progress"]), (0, 1, 0))
        self.app.config["TEST_NOW"] = NOW + timedelta(minutes=16)
        new = self.call(self.teacher, "GET", query.replace("04:11:00Z", "04:16:00Z")).json["data"]
        self.assertEqual((new["metrics"]["assigned_count"], new["metrics"]["completed_student_count"],
                          new["metrics"]["completion_rate"], new["metrics"]["attempt_count"]), (8, 2, 0.25, 3))
        self.assertEqual(self.call(self.teacher, "GET", read).json["data"], old)
        self.assertEqual(self.call(self.teacher, "GET", export).data, csv)
        self.call(s1, "GET", read, status=404)
        self.call(s1, "GET", export, status=403)
        self.call(self.teacher, "DELETE", self.base + f"/members/{self.uid(s1)}", status=204)
        for path in (f"/experiment-versions/{vid}", self.base + "/experiments", f"/wiring-attempts/{a1['id']}"):
            self.call(s1, "GET", path, status=404)
        self.call(s1, "GET", f"/knowledge-points/{self.points[1]['id']}", status=404)
        self.call(s1, "PUT", f"/knowledge-points/{self.points[1]['id']}/progress", {"completed": True}, 404)
        self.call(s1, "GET", self.base + f"/analytics?analysis_run_id={progress['analysis_run_id']}", status=404)
        self.assertEqual(self.call(self.teacher, "GET", read).json["data"], old)
        self.assertEqual(self.call(self.teacher, "GET", export).data, csv)
        self.assertEqual(database_facts(self.path)["foreign_key_check"], [])

    def test_markup_resource_upload_policy_and_current_permissions(self):
        # APIC3.1 forbids images/links; no knowledge-resource reference relation is defined.
        for kind in ("slides", "guide", "video", "question_bank"):
            self.call(self.teacher, "POST", self.base + "/resources", status=415,
                      upload=("alu.png", "image/png", PNG, {"title": "I01 PNG", "kind": kind}))
        resource = self.call(self.teacher, "POST", self.base + "/resources", status=201,
                             upload=("control.pdf", "application/pdf", PDF1, {"title": "I01文档对照", "kind": "guide"})).json["data"]
        v2 = self.call(self.teacher, "POST", f"/resources/{resource['resource_id']}/versions", status=201,
                       upload=("control-v2.pdf", "application/pdf", PDF2, {"change_note": "control v2"})).json["data"]
        student = self.students[0]
        url = f"/api/v1/resource-versions/{resource['id']}/content?intent=view&event_id={uuid4()}"
        markup = f'<h2 class="x">图文核对</h2><p onclick="alert(1)">A<sup>2</sup><sub>i</sub><img src="{url}" onerror="alert(1)"><a href="{url}" target="_blank">原版资源</a></p>'
        point = self.call(self.teacher, "PATCH", f"/knowledge-points/{self.points[0]['id']}", {
            "content": markup, "example": '<p style="color:red"><b>例题</b><a href="https://example.com">链接文本</a></p>'}).json["data"]
        self.assertEqual(point["content"], '<h2>图文核对</h2><p>A<sup>2</sup><sub>i</sub>原版资源</p>')
        self.assertEqual(point["example"], '<p><b>例题</b>链接文本</p>')
        self.assertEqual(self.call(student, "GET", f"/knowledge-points/{point['id']}").json["data"]["content"], point["content"])
        self.call(self.teacher, "PATCH", f"/knowledge-points/{point['id']}", {"resource_version_ids": [resource["id"]]}, 400)
        event = str(uuid4())
        old = f"/resource-versions/{resource['id']}/content?intent=view&event_id={event}"
        self.assertEqual(self.call(student, "GET", old).data, PDF1)
        self.assertEqual(self.call(student, "GET", old).data, PDF1)
        self.assertEqual(self.call(student, "GET", f"/resource-versions/{v2['id']}/content?intent=download&event_id={uuid4()}").data, PDF2)
        self.assertEqual(len(database_facts(self.path)["resource_event"]), 2)
        self.call(self.teacher, "PATCH", f"/resources/{resource['resource_id']}", {"visibility": "teacher_only"})
        self.call(student, "GET", old, status=404)
        self.call(student, "GET", f"/resources/{resource['resource_id']}/versions", status=404)
        self.assertEqual(self.call(self.teacher, "GET", old).data, PDF1)
        self.stages["policy"] = {"image_business_object_created": False, "PNG_upload": "415 for all four defined kinds",
                                 "image_preview_download": "blocked: no API-created image object",
                                 "resource_control": "PDF only; not an image proof"}

    @expectedFailure
    def test_contract_017_future_window_rejects_new_attempt(self):
        _, version, _ = self.experiment(start=NOW + timedelta(hours=1), end=NOW + timedelta(hours=2))
        self.call(self.students[0], "POST", f"/experiment-versions/{version['id']}/wiring-attempts", {}, 409)

    @expectedFailure
    def test_contract_017_closed_window_rejects_submit(self):
        _, version, _ = self.experiment()
        attempt = self.attempt(self.students[0], version["id"])
        self.save(self.students[0], attempt)
        self.app.config["TEST_NOW"] = NOW + timedelta(minutes=11)
        self.submit(self.students[0], attempt, 409)

    @expectedFailure
    def test_contract_017_revoked_member_rejects_old_mutations(self):
        _, version, _ = self.experiment()
        student = self.students[0]
        attempt = self.attempt(student, version["id"])
        body = self.save(student, attempt)
        self.call(self.teacher, "DELETE", self.base + f"/members/{self.uid(student)}", status=204)
        self.call(student, "GET", f"/wiring-attempts/{attempt['id']}", status=404)
        body.update(revision=1, actions=[])
        statuses = [self.call(student, "PUT", f"/wiring-attempts/{attempt['id']}", body, None).status_code,
                    self.call(student, "POST", f"/wiring-attempts/{attempt['id']}/validate", {"revision": 2}, None).status_code,
                    self.call(student, "POST", f"/wiring-attempts/{attempt['id']}/submit", {"revision": 2}, None,
                              headers={"Idempotency-Key": str(uuid4())}).status_code]
        self.assertEqual(statuses, [404, 404, 404])

    @expectedFailure
    def test_contract_017_redo_creates_new_attempt_after_submission(self):
        _, version, _ = self.experiment()
        student = self.students[0]
        attempt = self.attempt(student, version["id"])
        self.save(student, attempt)
        self.submit(student, attempt)
        self.call(student, "POST", f"/experiment-versions/{version['id']}/wiring-attempts", {}, 201)
