"""SPEC-017 实验箱连线接口测试。"""

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


class WiringApiBase(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "wiring.db"
        migrate(self.path)
        self.password = secrets.token_urlsafe(24)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.path),
                               "SECRET_KEY": secrets.token_hex(32), "APP_ORIGIN": ORIGIN,
                               "TEST_NOW": datetime(2026, 10, 13, 12, tzinfo=UTC)})
        with closing(connect(self.path)) as db:
            for number, role in (("T017ADMIN", "admin"), ("T017TEACH", "teacher")):
                db.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                           "VALUES(?,?,?,?,1,?,?)", (number, number, generate_password_hash(self.password), role,
                                                    "2026-10-13T00:00:00Z", "2026-10-13T00:00:00Z"))
        self.admin, self.teacher, self.student, self.outsider = [self.app.test_client() for _ in range(4)]
        self.login(self.admin, "T017ADMIN")
        self.login(self.teacher, "T017TEACH")
        for client, number in ((self.student, "T017STUD1"), (self.outsider, "T017STUD2")):
            self.call(client, "POST", "/auth/register",
                      {"student_no": number, "name": number, "password": self.password}, 201)
            self.login(client, number)
        self.teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        self.student_id = self.student.get("/api/v1/auth/session").json["data"]["user"]["id"]
        self.course_id = self.call(self.admin, "POST", "/courses",
                                   {"title": "C02d CPU", "teacher_id": self.teacher_id}, 201).json["data"]["id"]
        self.call(self.teacher, "POST", f"/courses/{self.course_id}/members",
                  {"user_id": self.student_id, "member_role": "student"}, 201)
        self.exp_base = f"/courses/{self.course_id}/experiments"

    def call(self, client, method, path, data=None, status=200):
        response = client.open("/api/v1" + path, method=method, json=data,
                               headers={"Origin": ORIGIN, "X-CSRF-Token": getattr(client, "csrf", "")})
        self.assertEqual(response.status_code, status, response.json)
        return response

    def login(self, client, number):
        data = self.call(client, "POST", "/auth/login",
                         {"student_no": number, "password": self.password}).json["data"]
        client.csrf = data["csrf_token"]

    def setup_experiment(self, code="EXP-01"):
        exp = self.call(self.teacher, "POST", self.exp_base,
                        {"code": code, "title": code, "description": code}, 201).json["data"]
        ver = self.call(self.teacher, "POST", f"/experiments/{exp['id']}/versions",
                        {"title": "v1", "submission_modes": ["wiring"]}, 201).json["data"]
        return exp, ver

    def create_attempt(self, version_id):
        return self.call(self.student, "POST",
                         f"/experiment-versions/{version_id}/wiring-attempts", {}, 201).json["data"]


class WiringLifecycleTest(WiringApiBase):
    def test_teacher_creates_experiment_and_version(self):
        _exp, ver = self.setup_experiment("EXP-01")
        self.assertIsNotNone(ver["id"])
        self.assertEqual(ver["status"], "published")

    def test_student_cannot_create_experiment(self):
        self.call(self.student, "POST", self.exp_base,
                  {"code": "EXP-01", "title": "x", "description": "x"}, 403)

    def test_create_and_get_attempt(self):
        _, ver = self.setup_experiment("EXP-01")
        attempt = self.create_attempt(ver["id"])
        self.assertEqual(attempt["status"], "draft")
        self.assertEqual(attempt["revision"], 0)
        self.assertEqual(attempt["latest_seq"], 0)
        # 二次创建返回同一 attempt
        again = self.call(self.student, "POST",
                          f"/experiment-versions/{ver['id']}/wiring-attempts", {}).json["data"]
        self.assertEqual(again["id"], attempt["id"])

    def test_save_with_revision_lock(self):
        _, ver = self.setup_experiment("EXP-01")
        attempt = self.create_attempt(ver["id"])
        state = attempt["state"]
        wire = {"id": "w1", "from_terminal": "sw_a_out", "to_terminal": "alu_a"}
        state["wires"] = [wire]
        actions = [{"type": "connect", "payload": wire}]
        saved = self.call(self.student, "PUT", f"/wiring-attempts/{attempt['id']}",
                          {"revision": 0, "state": state, "actions": actions}, 200).json["data"]
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(saved["latest_seq"], 1)
        # stale revision
        self.call(self.student, "PUT", f"/wiring-attempts/{attempt['id']}",
                  {"revision": 0, "state": state, "actions": actions}, 409)

    def test_state_mismatch_rejected(self):
        _, ver = self.setup_experiment("EXP-01")
        attempt = self.create_attempt(ver["id"])
        state = attempt["state"]
        # 客户端声称连了 w2，但动作里是 w1 → 不一致
        state["wires"] = [{"id": "w2", "from_terminal": "sw_a_out", "to_terminal": "alu_a"}]
        actions = [{"type": "connect", "payload": {"id": "w1", "from_terminal": "sw_a_out",
                                                    "to_terminal": "alu_a"}}]
        self.call(self.student, "PUT", f"/wiring-attempts/{attempt['id']}",
                  {"revision": 0, "state": state, "actions": actions}, 422)


class WiringValidationTest(WiringApiBase):
    def test_terminal_not_found(self):
        _, ver = self.setup_experiment("EXP-01")
        attempt = self.create_attempt(ver["id"])
        state = attempt["state"]
        state["wires"] = [{"id": "w1", "from_terminal": "no_such", "to_terminal": "alu_a"}]
        self.call(self.student, "PUT", f"/wiring-attempts/{attempt['id']}",
                  {"revision": 0, "state": state,
                   "actions": [{"type": "connect", "payload": state["wires"][0]}]})
        result = self.call(self.student, "POST", f"/wiring-attempts/{attempt['id']}/validate",
                           {"revision": 1}).json["data"]
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "TERMINAL_NOT_FOUND")

    def test_width_mismatch(self):
        _, ver = self.setup_experiment("EXP-01")
        attempt = self.create_attempt(ver["id"])
        state = attempt["state"]
        # sw_op 位宽 3 接 alu_y (位宽 8)
        wire = {"id": "w1", "from_terminal": "sw_op_out", "to_terminal": "alu_y"}
        state["wires"] = [wire]
        self.call(self.student, "PUT", f"/wiring-attempts/{attempt['id']}",
                  {"revision": 0, "state": state,
                   "actions": [{"type": "connect", "payload": wire}]})
        result = self.call(self.student, "POST", f"/wiring-attempts/{attempt['id']}/validate",
                           {"revision": 1}).json["data"]
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("WIDTH_MISMATCH", codes)


class WiringSubmitTest(WiringApiBase):
    def test_submit_with_structure_errors_returns_422(self):
        _, ver = self.setup_experiment("EXP-01")
        attempt = self.create_attempt(ver["id"])
        self.call(self.student, "POST", f"/wiring-attempts/{attempt['id']}/submit",
                  {"revision": 0}, 422)

    def test_submit_exp01_alu_functional(self):
        _, ver = self.setup_experiment("EXP-01")
        attempt = self.create_attempt(ver["id"])
        state = attempt["state"]
        # 接好 EXP-01 完整连线
        wires = [
            {"id": "w_a", "from_terminal": "sw_a_out", "to_terminal": "alu_a"},
            {"id": "w_b", "from_terminal": "sw_b_out", "to_terminal": "alu_b"},
            {"id": "w_op", "from_terminal": "sw_op_out", "to_terminal": "alu_op"},
            {"id": "w_y", "from_terminal": "alu_y", "to_terminal": "led_y_in"},
            {"id": "w_z", "from_terminal": "alu_z", "to_terminal": "led_z_in"},
            {"id": "w_c", "from_terminal": "alu_c", "to_terminal": "led_c_in"},
        ]
        state["wires"] = wires
        actions = [{"type": "connect", "payload": w} for w in wires]
        self.call(self.student, "PUT", f"/wiring-attempts/{attempt['id']}",
                  {"revision": 0, "state": state, "actions": actions})
        submit = self.call(self.student, "POST", f"/wiring-attempts/{attempt['id']}/submit",
                           {"revision": 1}).json["data"]
        self.assertEqual(submit["status"], "submitted")
        # ADD 255+1 应通过 Y=0 C=1 Z=1
        add_result = next(r for r in submit["functional_results"] if r["op"] == "ADD")
        self.assertTrue(add_result["passed"])

    def test_submitted_immutable(self):
        _, ver = self.setup_experiment("EXP-01")
        attempt = self.create_attempt(ver["id"])
        state = attempt["state"]
        wires = [
            {"id": "w_a", "from_terminal": "sw_a_out", "to_terminal": "alu_a"},
            {"id": "w_b", "from_terminal": "sw_b_out", "to_terminal": "alu_b"},
            {"id": "w_op", "from_terminal": "sw_op_out", "to_terminal": "alu_op"},
            {"id": "w_y", "from_terminal": "alu_y", "to_terminal": "led_y_in"},
            {"id": "w_z", "from_terminal": "alu_z", "to_terminal": "led_z_in"},
            {"id": "w_c", "from_terminal": "alu_c", "to_terminal": "led_c_in"},
        ]
        state["wires"] = wires
        actions = [{"type": "connect", "payload": w} for w in wires]
        self.call(self.student, "PUT", f"/wiring-attempts/{attempt['id']}",
                  {"revision": 0, "state": state, "actions": actions})
        self.call(self.student, "POST", f"/wiring-attempts/{attempt['id']}/submit", {"revision": 1})
        self.call(self.student, "PUT", f"/wiring-attempts/{attempt['id']}",
                  {"revision": 1, "state": state, "actions": []}, 409)


class WiringActionsTest(WiringApiBase):
    def test_actions_pagination(self):
        _, ver = self.setup_experiment("EXP-01")
        attempt = self.create_attempt(ver["id"])
        state = attempt["state"]
        wires = [{"id": f"w{i}", "from_terminal": "sw_a_out", "to_terminal": "alu_a"}
                 for i in range(3)]
        # 只连第一条，其余断开
        state["wires"] = [wires[0]]
        actions = [{"type": "connect", "payload": wires[0]}]
        self.call(self.student, "PUT", f"/wiring-attempts/{attempt['id']}",
                  {"revision": 0, "state": state, "actions": actions})
        resp = self.call(self.student, "GET", f"/wiring-attempts/{attempt['id']}/actions").json["data"]
        self.assertEqual(resp["latest_seq"], 1)
        self.assertEqual(len(resp["items"]), 1)

    def test_list_attempts_for_course(self):
        _, ver = self.setup_experiment("EXP-01")
        self.create_attempt(ver["id"])
        items = self.call(self.teacher, "GET",
                          f"/courses/{self.course_id}/wiring-attempts").json["data"]
        self.assertEqual(len(items), 1)
        # 学生只看自己
        student_items = self.call(self.student, "GET",
                                  f"/courses/{self.course_id}/wiring-attempts").json["data"]
        self.assertEqual(len(student_items), 1)
