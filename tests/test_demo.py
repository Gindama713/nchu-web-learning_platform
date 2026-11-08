"""SPEC-007 课堂演示接口测试。"""

import json
import secrets
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.shared.db import connect, migrate

ORIGIN = "http://127.0.0.1:5173"


class DemoApiBase(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "demo.db"
        migrate(self.path)
        self.password = secrets.token_urlsafe(24)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.path),
                               "SECRET_KEY": secrets.token_hex(32), "APP_ORIGIN": ORIGIN,
                               "TEST_NOW": datetime(2026, 10, 13, 12, tzinfo=UTC)})
        with closing(connect(self.path)) as db:
            for number, role in (("T007ADMIN", "admin"), ("T007TEACH", "teacher")):
                db.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                           "VALUES(?,?,?,?,1,?,?)", (number, number, generate_password_hash(self.password), role,
                                                    "2026-10-13T00:00:00Z", "2026-10-13T00:00:00Z"))
        self.admin, self.teacher, self.student, self.outsider = [self.app.test_client() for _ in range(4)]
        self.login(self.admin, "T007ADMIN")
        self.login(self.teacher, "T007TEACH")
        for client, number in ((self.student, "T007STUD1"), (self.outsider, "T007STUD2")):
            self.call(client, "POST", "/auth/register",
                      {"student_no": number, "name": number, "password": self.password}, 201)
            self.login(client, number)
        self.teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        self.student_id = self.student.get("/api/v1/auth/session").json["data"]["user"]["id"]
        self.course_id = self.call(self.admin, "POST", "/courses",
                                   {"title": "C02d CPU", "teacher_id": self.teacher_id}, 201).json["data"]["id"]
        self.call(self.teacher, "POST", f"/courses/{self.course_id}/members",
                  {"user_id": self.student_id, "member_role": "student"}, 201)
        self.base = f"/courses/{self.course_id}/demo-sessions"

    def call(self, client, method, path, data=None, status=200):
        response = client.open("/api/v1" + path, method=method, json=data,
                               headers={"Origin": ORIGIN, "X-CSRF-Token": getattr(client, "csrf", "")})
        self.assertEqual(response.status_code, status, response.json)
        return response

    def login(self, client, number):
        data = self.call(client, "POST", "/auth/login",
                         {"student_no": number, "password": self.password}).json["data"]
        client.csrf = data["csrf_token"]

    def create(self, preset="gate", **overrides):
        return self.call(self.teacher, "POST", self.base,
                         {"preset": preset, **overrides}, 201).json["data"]


class DemoCreateTest(DemoApiBase):
    def test_permissions_and_invalid_preset(self):
        for client in (self.teacher, self.student):
            self.assertEqual(self.call(client, "GET", self.base).json["data"], [])
        self.call(self.outsider, "GET", self.base, status=404)
        self.call(self.student, "POST", self.base, {"preset": "gate"}, 403)
        self.call(self.teacher, "POST", self.base, {"preset": "invalid"}, 400)
        self.call(self.teacher, "POST", self.base, {}, 400)

    def test_create_each_preset(self):
        for preset in ("gate", "comb", "sequential", "alu", "memory", "cpu"):
            item = self.create(preset)
            self.assertEqual(item["preset"], preset)
            self.assertEqual(item["revision"], 0)
            self.assertTrue(item["active"])
            self.assertIn("state", item)


class DemoAdvanceTest(DemoApiBase):
    def setUp(self):
        super().setUp()
        self.session = self.create("gate")

    def test_step_increments_revision_and_changes_state(self):
        rev0 = self.session["revision"]
        state0 = self.session["state"]
        advanced = self.call(self.teacher, "PUT", f"/demo-sessions/{self.session['id']}/state",
                             {"revision": rev0, "action": "step"}).json["data"]
        self.assertEqual(advanced["revision"], rev0 + 1)
        self.assertNotEqual(advanced["state"]["step"], state0["step"])

    def test_stale_revision_rejected(self):
        self.call(self.teacher, "PUT", f"/demo-sessions/{self.session['id']}/state",
                  {"revision": self.session["revision"], "action": "step"})
        response = self.call(self.teacher, "PUT", f"/demo-sessions/{self.session['id']}/state",
                             {"revision": self.session["revision"], "action": "step"}, 409)
        self.assertEqual(response.json["error"]["code"], "REVISION_CONFLICT")

    def test_student_cannot_advance(self):
        self.call(self.student, "PUT", f"/demo-sessions/{self.session['id']}/state",
                  {"revision": self.session["revision"], "action": "step"}, 403)

    def test_reset_returns_to_initial(self):
        self.call(self.teacher, "PUT", f"/demo-sessions/{self.session['id']}/state",
                  {"revision": self.session["revision"], "action": "step"})
        advanced = self.call(self.teacher, "GET", f"/demo-sessions/{self.session['id']}").json["data"]
        reset = self.call(self.teacher, "PUT", f"/demo-sessions/{self.session['id']}/state",
                          {"revision": advanced["revision"], "action": "reset"}).json["data"]
        self.assertEqual(reset["state"]["step"], 0)

    def test_invalid_action_rejected(self):
        self.call(self.teacher, "PUT", f"/demo-sessions/{self.session['id']}/state",
                  {"revision": self.session["revision"], "action": "fly"}, 400)


class DemoCpuTest(DemoApiBase):
    def test_cpu_fetch_decode_execute_cycle(self):
        session = self.create("cpu")
        self.assertEqual(session["state"]["cycle"], "fetch")
        fetch = self.call(self.teacher, "PUT", f"/demo-sessions/{session['id']}/state",
                          {"revision": session["revision"], "action": "step"}).json["data"]
        self.assertEqual(fetch["state"]["cycle"], "decode")
        decode = self.call(self.teacher, "PUT", f"/demo-sessions/{session['id']}/state",
                           {"revision": fetch["revision"], "action": "step"}).json["data"]
        self.assertEqual(decode["state"]["cycle"], "execute")
        execute = self.call(self.teacher, "PUT", f"/demo-sessions/{session['id']}/state",
                            {"revision": decode["revision"], "action": "step"}).json["data"]
        self.assertEqual(execute["state"]["cycle"], "fetch")
        # LDA #5 应当加载 A=05
        self.assertEqual(execute["state"]["registers"]["A"], "05")

    def test_cpu_illegal_opcode_halt(self):
        # 直接构造一个含非法 opcode 的 state 推进，验证停机
        session = self.create("cpu")
        state = {"step": 0, "cycle": "fetch", "pc": 0, "ir": 0, "a": 0, "x": 0,
                 "flags": {"zero": 0, "carry": 0},
                 "ram": [0xFF] + [0] * 255,
                 "registers": {"A": "00", "X": "00", "PC": "0000", "IR": "00"},
                 "buses": {"addr": "0000", "data": "00"},
                 "control": {"fetch": 1, "decode": 0, "execute": 0, "mem_wr": 0, "halt": 0},
                 "message": ""}
        with closing(connect(self.path)) as db:
            db.execute("UPDATE demo_session SET state=? WHERE id=?",
                       (json.dumps(state), session["id"]))
            db.commit()
        fetch = self.call(self.teacher, "PUT", f"/demo-sessions/{session['id']}/state",
                          {"revision": 0, "action": "step"}).json["data"]
        decode = self.call(self.teacher, "PUT", f"/demo-sessions/{session['id']}/state",
                           {"revision": fetch["revision"], "action": "step"}).json["data"]
        self.assertEqual(decode["state"]["cycle"], "halt")
        self.assertTrue(decode["state"]["control"]["halt"])


class DemoReadTest(DemoApiBase):
    def setUp(self):
        super().setUp()
        self.session = self.create("cpu")

    def test_student_can_read(self):
        item = self.call(self.student, "GET", f"/demo-sessions/{self.session['id']}").json["data"]
        self.assertEqual(item["id"], self.session["id"])
        self.assertEqual(item["state"]["cycle"], "fetch")

    def test_after_revision_polling(self):
        advanced = self.call(self.teacher, "PUT", f"/demo-sessions/{self.session['id']}/state",
                             {"revision": self.session["revision"], "action": "step"}).json["data"]
        # after_revision 已追上时返回当前 revision
        poll = self.call(self.student, "GET",
                         f"/demo-sessions/{self.session['id']}?after_revision={advanced['revision']}").json["data"]
        self.assertEqual(poll["revision"], advanced["revision"])

    def test_list_with_active_filter(self):
        self.create("gate")
        all_items = self.call(self.teacher, "GET", self.base).json["data"]
        self.assertEqual(len(all_items), 2)
        active_items = self.call(self.teacher, "GET", f"{self.base}?active=true").json["data"]
        self.assertEqual(len(active_items), 2)
        inactive = self.call(self.teacher, "GET", f"{self.base}?active=false").json["data"]
        self.assertEqual(inactive, [])


class DemoCloseTest(DemoApiBase):
    def setUp(self):
        super().setUp()
        self.session = self.create("gate")

    def test_close_makes_immutable(self):
        closed = self.call(self.teacher, "POST", f"/demo-sessions/{self.session['id']}/close",
                           {"revision": self.session["revision"]}).json["data"]
        self.assertFalse(closed["active"])
        # 关闭后不可推进
        self.call(self.teacher, "PUT", f"/demo-sessions/{self.session['id']}/state",
                  {"revision": closed["revision"], "action": "step"}, 409)
        # 重复关闭幂等
        again = self.call(self.teacher, "POST", f"/demo-sessions/{self.session['id']}/close",
                          {"revision": closed["revision"]}).json["data"]
        self.assertFalse(again["active"])
