"""SPEC-017 实验箱连线接口测试。"""

import secrets
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.engines.wiring import _make_panel
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
        panel = _make_panel(code)
        panel["layout"] = {}
        ver = self.call(self.teacher, "POST", f"/experiments/{exp['id']}/versions",
                        {"title": "v1", "objectives": "模拟连线", "instructions": "完成连线",
                         "knowledge_ids": [], "submission_modes": ["wiring"],
                         "panel": panel, "rules": {"require_required_inputs": True}}, 201).json["data"]
        published = self.call(self.teacher, "POST", f"/experiment-versions/{ver['id']}/publish",
                              {"start_at": "2026-10-13T11:00:00Z",
                               "end_at": "2026-10-20T00:00:00Z"}).json["data"]
        return exp, published

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

    def test_save_with_undo_action_in_batch(self):
        # 同一批动作含 undo：服务端必须整批一次性重放，逐条重放会丢失 undo 语义
        _, ver = self.setup_experiment("EXP-01")
        attempt = self.create_attempt(ver["id"])
        state = attempt["state"]
        wire = {"id": "w1", "from_terminal": "sw_a_out", "to_terminal": "alu_a"}
        actions = [{"type": "connect", "payload": wire}, {"type": "undo", "payload": {}}]
        saved = self.call(self.student, "PUT", f"/wiring-attempts/{attempt['id']}",
                          {"revision": 0, "state": state, "actions": actions}, 200).json["data"]
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(saved["latest_seq"], 2)


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
        # PRD：八种运算基线全部通过才记 completed
        self.assertTrue(submit["completed"])
        self.assertTrue(all(r["passed"] for r in submit["functional_results"]))
        # ADD 255+1 应通过 Y=0 C=1 Z=1
        add_result = next(r for r in submit["functional_results"] if r["op"] == "ADD")
        self.assertTrue(add_result["passed"])
        # SUB 0-1 有借位：Y=255 C=0；PRD 规定 C=1 表示无借位
        sub_result = next(r for r in submit["functional_results"] if r["op"] == "SUB")
        self.assertEqual(sub_result["actual"], {"Y": 255, "Z": 0, "C": 0})

    def test_sub_borrow_flag_semantics(self):
        from backend.engines import wiring as engine

        panel = engine._make_panel("EXP-01")
        state = engine.initial_state(panel)
        state["wires"] = [
            {"id": "w_a", "from_terminal": "sw_a_out", "to_terminal": "alu_a"},
            {"id": "w_b", "from_terminal": "sw_b_out", "to_terminal": "alu_b"},
            {"id": "w_op", "from_terminal": "sw_op_out", "to_terminal": "alu_op"},
            {"id": "w_y", "from_terminal": "alu_y", "to_terminal": "led_y_in"},
            {"id": "w_z", "from_terminal": "alu_z", "to_terminal": "led_z_in"},
            {"id": "w_c", "from_terminal": "alu_c", "to_terminal": "led_c_in"},
        ]
        # 255-1 无借位：Y=254 C=1
        state["inputs"] = {"sw_a_out": 255, "sw_b_out": 1, "sw_op_out": 1}
        values = engine._propagate(panel, state)
        self.assertEqual((values["alu_y"], values["alu_c"]), (254, 1))
        # 1-255 有借位：Y=2 C=0
        state["inputs"] = {"sw_a_out": 1, "sw_b_out": 255, "sw_op_out": 1}
        values = engine._propagate(panel, state)
        self.assertEqual((values["alu_y"], values["alu_c"]), (2, 0))

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
        # 提交后也不允许再 validate 刷记录
        self.call(self.student, "POST", f"/wiring-attempts/{attempt['id']}/validate",
                  {"revision": 1}, 409)

    def test_submit_exp02_register_functional(self):
        _, ver = self.setup_experiment("EXP-02")
        attempt = self.create_attempt(ver["id"])
        state = attempt["state"]
        wires = [
            {"id": "w_d", "from_terminal": "sw_d_out", "to_terminal": "reg_d"},
            {"id": "w_en", "from_terminal": "sw_en_out", "to_terminal": "reg_en"},
            {"id": "w_clk", "from_terminal": "clk_out", "to_terminal": "reg_clk"},
            {"id": "w_rst", "from_terminal": "rst_out", "to_terminal": "reg_rst"},
            {"id": "w_q", "from_terminal": "reg_q", "to_terminal": "led_q_in"},
        ]
        state["wires"] = wires
        actions = [{"type": "connect", "payload": w} for w in wires]
        self.call(self.student, "PUT", f"/wiring-attempts/{attempt['id']}",
                  {"revision": 0, "state": state, "actions": actions})
        submit = self.call(self.student, "POST", f"/wiring-attempts/{attempt['id']}/submit",
                           {"revision": 1}).json["data"]
        self.assertEqual(submit["status"], "submitted")
        # 三用例连续执行：载入 A5 后 en=0 必须保持
        self.assertTrue(submit["completed"])
        self.assertTrue(all(r["passed"] for r in submit["functional_results"]))

    def test_exp03_datapath_executes_program(self):
        from backend.engines import wiring as engine

        panel = engine._make_panel("EXP-03")
        state = engine.initial_state(panel)
        links = [
            ("pc_q", "rom_addr"), ("rom_data", "ir_d"), ("ir_q", "split_in"),
            ("ir_q", "ctrl_ir"), ("split_lo", "ext_in"), ("split_lo", "pc_d"),
            ("ext_out", "mux_a"), ("ext_out", "alu_b"), ("alu_y", "mux_b"),
            ("mux_y", "acc_d"), ("acc_q", "alu_a"), ("acc_q", "led_acc_in"),
            ("pc_q", "led_pc_in"), ("ctrl_alu_op", "alu_op"), ("ctrl_acc_sel", "mux_sel"),
            ("ctrl_acc_en", "acc_en"), ("ctrl_ir_en", "ir_en"), ("ctrl_pc_inc", "pc_inc"),
            ("ctrl_pc_load", "pc_load"), ("alu_z", "ctrl_alu_z"), ("alu_c", "ctrl_alu_c"),
            ("clk_out", "pc_clk"), ("clk_out", "ir_clk"), ("clk_out", "acc_clk"),
            ("clk_out", "ctrl_clk"), ("rst_out", "pc_rst"), ("rst_out", "ir_rst"),
            ("rst_out", "acc_rst"), ("rst_out", "ctrl_rst"), ("en_out", "pc_en"),
            ("en_out", "ctrl_en"),
        ]
        state["wires"] = [{"id": f"w{i}", "from_terminal": f, "to_terminal": t}
                          for i, (f, t) in enumerate(links, 1)]
        valid, errors = engine.validate_structure(panel, state)
        self.assertTrue(valid, errors)
        # ROM 内置程序 [LDI 3, ADDI 2, HALT]：完整数据通路跑 12 拍后 ACC=5 且停机
        s = engine.reset(panel, state)
        for _ in range(12):
            s = engine.step(panel, s)
        self.assertEqual(s["acc_q"], 5)
        self.assertEqual(s["ir_q"], 0xF0)
        self.assertEqual(s["halted"], 1)


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

    def test_output_conflict_reports_wire_ids(self):
        _, ver = self.setup_experiment("EXP-01")
        attempt = self.create_attempt(ver["id"])
        state = attempt["state"]
        state["wires"] = [
            {"id": "w_a", "from_terminal": "sw_a_out", "to_terminal": "alu_a"},
            {"id": "w_b", "from_terminal": "sw_b_out", "to_terminal": "alu_a"},
        ]
        actions = [{"type": "connect", "payload": w} for w in state["wires"]]
        self.call(self.student, "PUT", f"/wiring-attempts/{attempt['id']}",
                  {"revision": 0, "state": state, "actions": actions})
        result = self.call(self.student, "POST", f"/wiring-attempts/{attempt['id']}/validate",
                           {"revision": 1}).json["data"]
        conflict = next(e for e in result["errors"] if e["code"] == "OUTPUT_CONFLICT")
        # 冲突导线可定位，供前端高亮
        self.assertEqual(sorted(conflict["wire_ids"]), ["w_a", "w_b"])

    def test_list_actions_rejects_non_numeric_after_seq(self):
        _, ver = self.setup_experiment("EXP-01")
        attempt = self.create_attempt(ver["id"])
        self.call(self.student, "GET",
                  f"/wiring-attempts/{attempt['id']}/actions?after_seq=abc", status=400)

    def test_list_attempts_rejects_non_numeric_student_id(self):
        _, ver = self.setup_experiment("EXP-01")
        self.create_attempt(ver["id"])
        self.call(self.teacher, "GET",
                  f"/courses/{self.course_id}/wiring-attempts?student_id=abc", status=400)

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
