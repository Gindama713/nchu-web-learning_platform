"""T018 real API integration for SPEC-018 online circuit grading.

Only account bootstrap is seeded. All grading operations use actual API
handlers, cookies and CSRF; worker completion is injected through the real
claim/submit lease path (engine results, not API mocks).

覆盖来源标注（PRD 第13节 T018）：AC-01 提交即排队 / AC-02 状态查询 /
AC-03 预检4xx不建任务 / AC-04 独立视图模型 / AC-05 系统故障不误判 /
AC-06 成绩隔离 / AC-07 幂等 / AC-08 重评 / AC-10 快照一致性 /
AC-11 队列容量 / AC-12 分数构成；R02/R03/R04/R13/R18/R19/R29/R41。
"""

import copy
import json
import secrets
from contextlib import closing
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from uuid import uuid4

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.engines import grading as engine
from backend.shared.db import connect, migrate

ORIGIN = "http://127.0.0.1:5173"
TEST_NOW = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)
AT = "2026-10-13T08:00:00Z"
PASSWORD = "correct horse battery staple 42"

CIRC = """<?xml version="1.0" encoding="UTF-8"?>
<logisim-evolution version="5.0.0">
  <circuit name="alu8">
    <comp name="Pin" loc="(10,10)"><a name="label" val="A"/><a name="width" val="8"/></comp>
    <comp name="Pin" loc="(10,40)"><a name="label" val="B"/><a name="width" val="8"/></comp>
    <comp name="Pin" loc="(300,10)"><a name="label" val="Y"/><a name="width" val="8"/>
      <a name="output" val="true"/></comp>
    <comp name="Adder" loc="(150,10)"/>
  </circuit>
</logisim-evolution>
"""

PORT_SCHEMA = {"inputs": {"A": 8, "B": 8}, "outputs": {"Y": 8}}
COMPONENTS = ["Adder", "AND", "OR"]
LIMITS = {"cpu_seconds": 10, "memory_mib": 512, "output_bytes": 1048576, "processes": 1}
GROUPS = ("add", "sub", "and", "or", "xor", "not", "shl", "shr")


def cases_payload():
    """EXP-01 模板 8 组各 1 case，public/hidden 交替。"""
    return [{"label": f"{group}-1", "visibility": "public" if index % 2 == 0 else "hidden",
             "group_code": group,
             "steps": [{"step_no": 1, "inputs": {"A": 5, "B": 3},
                        "expected": {"Y": 8}, "clock_event": "none"}]}
            for index, group in enumerate(GROUPS)]


class GradingFixture(TestCase):
    """共享 SPEC-018 fixture 与真实 API 辅助；不含测试方法，供 018/010D 复用。"""

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.path = Path(self.temporary.name)/"grading.db"
        self.password = secrets.token_urlsafe(24)
        migrate(self.path)
        self.app = create_app({"TESTING": True, "TEST_NOW": TEST_NOW, "DATABASE_PATH": str(self.path),
                               "UPLOAD_ROOT": str(Path(self.temporary.name)/"uploads"),
                               "SECRET_KEY": secrets.token_hex(32), "APP_ORIGIN": ORIGIN})
        with closing(connect(self.path)) as db:
            for number, role in (("T018ADMIN", "admin"), ("T018TEACH", "teacher"),
                                 ("T018TEACH2", "teacher")):
                db.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                           "VALUES(?,?,?,?,1,?,?)", (number, number, generate_password_hash(self.password),
                                                    role, AT, AT))
        self.admin, self.teacher, self.teacher2, self.student, self.student2, self.student3 = [
            self.app.test_client() for _ in range(6)]
        self.login(self.admin, "T018ADMIN")
        self.login(self.teacher, "T018TEACH")
        self.login(self.teacher2, "T018TEACH2")
        for client, number in ((self.student, "T018STUD1"), (self.student2, "T018STUD2"),
                               (self.student3, "T018STUD3")):
            self.call(client, "POST", "/auth/register",
                      {"student_no": number, "name": number, "password": self.password}, 201)
            self.login(client, number)
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        teacher2_id = self.teacher2.get("/api/v1/auth/session").json["data"]["user"]["id"]
        course = self.call(self.admin, "POST", "/courses", {
            "title": "T018 grading CPU", "teacher_id": teacher_id}, 201)
        self.course_id = course.json["data"]["id"]
        self.course = f"/courses/{self.course_id}"
        self.call(self.teacher, "POST", self.course+"/members",
                  {"user_id": self._uid(self.student), "member_role": "student"}, 201)
        self.call(self.teacher, "POST", self.course+"/members",
                  {"user_id": self._uid(self.student2), "member_role": "student"}, 201)
        course2 = self.call(self.admin, "POST", "/courses", {
            "title": "T018 other", "teacher_id": teacher2_id}, 201)
        self.course2_id = course2.json["data"]["id"]
        self.course2 = f"/courses/{self.course2_id}"
        chapter = self.call(self.teacher, "POST", self.course+"/chapters",
                            {"title": "CPU"}, status=201)
        self.knowledge_id = self.call(self.teacher, "POST",
                                      f"/chapters/{chapter.json['data']['id']}/knowledge-points", {
                                          "title": "运算器", "content": "x", "published": True,
                                          "is_foundational": True}, 201).json["data"]["id"]
        # circuit 版本（EXP-01，双模式以覆盖 wiring-only 拒绝场景）。
        experiment = self.call(self.teacher, "POST", f"{self.course}/experiments", {
            "code": "EXP-01", "title": "8位ALU", "description": "组合逻辑"}, 201).json["data"]
        self.experiment_id = experiment["id"]
        self.version_id = self.create_version(("wiring", "circuit"))

    def tearDown(self):
        self.temporary.cleanup()

    # ---------- 辅助 ----------

    def login(self, client, number):
        data = self.call(client, "POST", "/auth/login",
                         {"student_no": number, "password": self.password}).json["data"]
        client.csrf = data["csrf_token"]

    def _uid(self, client):
        return client.get("/api/v1/auth/session").json["data"]["user"]["id"]

    def create_version(self, modes, code_experiment=None, title="v标题"):
        payload = {
            "title": title, "objectives": "理解ALU", "knowledge_ids": [self.knowledge_id],
            "instructions": "1. 完成 alu8", "submission_modes": list(modes),
            "rules": {"hidden": {"y": "8"}},
        }
        if "wiring" in modes:
            payload["panel"] = {
                "schema_version": 1, "components": [
                    {"id": "s", "type": "SWITCH", "params": {"width": 8, "initial": 0},
                     "ports": {"OUT": "t-s"}},
                    {"id": "l", "type": "LED", "params": {"width": 8}, "ports": {"IN": "t-l"}}],
                "terminals": [
                    {"id": "t-s", "component_id": "s", "name": "OUT", "direction": "out",
                     "width": 8, "required": True},
                    {"id": "t-l", "component_id": "l", "name": "IN", "direction": "in",
                     "width": 8, "required": True}],
                "layout": {"columns": 2}}
        return self.call(self.teacher, "POST",
                         f"/experiments/{code_experiment or self.experiment_id}/versions",
                         payload, 201).json["data"]["id"]

    def put_profile(self, version_id=None, status=200, **overrides):
        payload = {"top_circuit": "alu8", "port_schema": copy.deepcopy(PORT_SCHEMA),
                   "allowed_components": list(COMPONENTS), "limits": copy.deepcopy(LIMITS),
                   **overrides}
        for key in ("port_schema", "allowed_components", "limits"):
            if overrides.get(key) is not None:
                payload[key] = overrides[key]
        return self.call(self.teacher, "PUT",
                         f"/experiment-versions/{version_id or self.version_id}/judge-profile",
                         payload, status)

    def create_suite(self, version_id=None, status=201, cases=None):
        return self.call(self.teacher, "POST",
                         f"/experiment-versions/{version_id or self.version_id}/test-suites",
                         {"cases": cases if cases is not None else cases_payload()}, status).json["data"]

    def upload_reference(self, version_id=None, kind="correct", content=None, status=201):
        data = {"kind": kind}
        headers = {"Origin": ORIGIN, "X-CSRF-Token": self.teacher.csrf}
        response = self.teacher.post(
            f"/api/v1/experiment-versions/{version_id or self.version_id}/reference-files",
            data={**data, "file": (BytesIO(content or CIRC.encode()), "alu.circ")},
            headers=headers)
        assert response.status_code == status, (response.status_code, response.json)
        return response.json.get("data", response.json)

    def pass_validation(self, version_id, suite):
        """走真实 API 发起验证，再经 worker 提交路径注入 passed 结果。"""
        reference = self.upload_reference(version_id, "correct")
        negative = self.upload_reference(version_id, "known_wrong")
        validation = self.call(self.teacher, "POST", f"/test-suites/{suite['id']}/validations",
                               {"reference_file_id": reference["reference_file_id"],
                                "negative_file_id": negative["reference_file_id"]}, 202).json["data"]
        with closing(connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = engine.claim_validation(db, TEST_NOW)
            assert row is not None and row["id"] == validation["validation_id"]
            assert engine.submit_validation_result(db, row["id"], row["worker_token"],
                                                   TEST_NOW, True, True)
            db.commit()
        return validation["validation_id"]

    def publish_suite(self, version_id, suite, validation_id, status=200):
        return self.call(self.teacher, "POST", f"/test-suites/{suite['id']}/publish",
                         {"validation_id": validation_id}, status).json["data"]

    def publish_circuit(self, version_id=None, start="2026-10-12T02:00:00Z",
                        end="2026-10-20T02:00:00Z"):
        """全流程：profile → suite → 验证 → 发布测试集 → 发布实验版本。"""
        version_id = version_id or self.version_id
        self.put_profile(version_id)
        suite = self.create_suite(version_id)
        validation_id = self.pass_validation(version_id, suite)
        self.publish_suite(version_id, suite, validation_id)
        published = self.call(self.teacher, "POST",
                              f"/experiment-versions/{version_id}/publish",
                              {"start_at": start, "end_at": end,
                               "initial_test_suite_id": suite["id"]}, 200).json["data"]
        return version_id, suite, published

    def submit(self, client, version_id=None, content=None, key=None, filename="alu.circ",
               status=202):
        headers = {"Origin": ORIGIN, "X-CSRF-Token": getattr(client, "csrf", ""),
                   "Idempotency-Key": key or str(uuid4())}
        response = client.post(
            f"/api/v1/experiment-versions/{version_id or self.version_id}/submissions",
            data={"file": (BytesIO(content or CIRC.encode()), filename)}, headers=headers)
        assert response.status_code == status, (response.status_code, response.json)
        return response.json.get("data", response.json)

    def finish_run(self, run_id, passed_cases, error=None):
        """经真实领取/提交路径完成 run（引擎结果注入，非 API mock）。"""
        with closing(connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            run = engine.claim_run(db, TEST_NOW)
            assert run is not None and run["id"] == run_id, (run and run["id"], run_id)
            cases = db.execute("SELECT id FROM test_case WHERE suite_id=?", (run["suite_id"],)).fetchall()
            results = [{"case_id": case["id"], "passed": index < passed_cases,
                        "actual": [{"Y": 8}], "elapsed_ms": 5}
                       for index, case in enumerate(cases)]
            assert engine.submit_run_result(db, run_id, run["worker_token"], TEST_NOW,
                                            error, results)
            db.commit()

    def _get_run(self, client, run_id, status=200):
        response = client.get(f"/api/v1/grading-runs/{run_id}",
                              headers={"Origin": ORIGIN})
        assert response.status_code == status, (response.status_code, response.json)
        return response.json.get("data", response.json)

    def call(self, client, method, path, payload=None, status=200, headers_extra=None):
        headers = {"Origin": ORIGIN, "X-CSRF-Token": getattr(client, "csrf", "")}
        if headers_extra:
            headers.update(headers_extra)
        response = getattr(client, method.lower())(f"/api/v1{path}", json=payload, headers=headers)
        assert response.status_code == status, (path, response.status_code, response.json)
        return response


class GradingTest(GradingFixture):
    # ---------- 教师配置（R04/R13） ----------

    def test_teacher_profile_configuration(self):
        # 覆盖 T018-R04：仅 circuit 草稿可配置；wiring-only 与已发布版本 409；
        # engine_version 固定、limits 不超平台上限、白名单外元件拒绝。
        data = self.put_profile().json["data"]
        self.assertEqual(data["engine_version"], "logisim-evolution 5.0.0")
        self.assertEqual(data["top_circuit"], "alu8")
        self.assertTrue(data["canonical_sha256"])
        # wiring-only 版本 409。
        wiring_only = self.create_version(("wiring",), title="w only")
        self.put_profile(version_id=wiring_only, status=409)
        # 平台外元件 / 超限 limits / 错误 engine_version 拒绝。
        self.put_profile(allowed_components=["Adder", "HDLLoader"], status=400)
        self.put_profile(limits={"cpu_seconds": 999, "memory_mib": 512,
                                 "output_bytes": 1024, "processes": 1}, status=400)
        self.put_profile(engine_version="logisim 3.8.0", status=400)
        # 重复 PUT 更新同一配置（唯一配置源），发布后冻结 409。
        self.put_profile()
        version_id, _suite, _published = self.publish_circuit()
        self.put_profile(version_id=version_id, status=409)

    def test_reference_upload_preflight(self):
        # 覆盖 AC-03：教师参考文件与学生文件同样结构校验，身份不绕过沙箱。
        self.put_profile()
        bad = self.upload_reference(kind="correct",
                                    content=b"<html>not xml</html>", status=400)
        self.assertEqual(bad["error"]["code"], "INVALID_CIRCUIT")
        # 伪扩展名 / 错误 kind 拒绝。
        self.call(self.teacher, "POST",
                  f"/experiment-versions/{self.version_id}/reference-files", {}, status=400)
        headers = {"Origin": ORIGIN, "X-CSRF-Token": self.teacher.csrf}
        response = self.teacher.post(
            f"/api/v1/experiment-versions/{self.version_id}/reference-files",
            data={"kind": "correct", "file": (BytesIO(CIRC.encode()), "alu.txt")}, headers=headers)
        self.assertEqual(response.status_code, 400)
        self.upload_reference(kind="wrong", status=400)
        good = self.upload_reference()
        self.assertEqual(good["kind"], "correct")
        listed = self.call(self.teacher, "GET",
                           f"/experiment-versions/{self.version_id}/reference-files").json
        self.assertEqual(listed["total"], 1)

    def test_suite_validation_and_publish_gates(self):
        # 覆盖 R13/R04：测试集不接受 weight；缺组不能验证；无 profile 验证 409；
        # 只有与当前配置全部哈希一致且 passed 的验证可发布（AC-10）。
        with_weight = [{"label": "add-1", "visibility": "public", "group_code": "add",
                        "steps": [{"step_no": 1, "inputs": {"A": 1}, "expected": {"Y": 1},
                                   "clock_event": "none"}], "weight": 9}]
        self.call(self.teacher, "POST", f"/experiment-versions/{self.version_id}/test-suites",
                  {"cases": with_weight}, 400)
        # 无 profile：可建测试集与参考文件，但验证 409（R04）。
        suite = self.create_suite()
        reference = self.upload_reference()
        negative = self.upload_reference(kind="known_wrong")
        self.call(self.teacher, "POST", f"/test-suites/{suite['id']}/validations",
                  {"reference_file_id": reference["reference_file_id"],
                   "negative_file_id": negative["reference_file_id"]}, 409)
        self.put_profile()
        # 缺组（只覆盖 add）不能验证。
        partial = [{"label": "add-1", "visibility": "public", "group_code": "add",
                    "steps": [{"step_no": 1, "inputs": {"A": 1}, "expected": {"Y": 1},
                               "clock_event": "none"}]}]
        partial_suite = self.create_suite(cases=partial)
        self.call(self.teacher, "POST", f"/test-suites/{partial_suite['id']}/validations",
                  {"reference_file_id": reference["reference_file_id"],
                   "negative_file_id": negative["reference_file_id"]}, 409)
        # 全组套件验证 passed 后可发布；发布后不可重复发布。
        full_suite = self.create_suite()
        validation_id = self.pass_validation(self.version_id, full_suite)
        self.call(self.teacher, "GET", f"/test-suite-validations/{validation_id}")
        self.publish_suite(self.version_id, full_suite, validation_id)
        self.call(self.teacher, "POST", f"/test-suites/{full_suite['id']}/publish",
                  {"validation_id": validation_id}, 409)
        # AC-10：profile 变化后旧验证失效，不能再发布同验证的新套件。
        suite2 = self.create_suite()
        validation2 = self.pass_validation(self.version_id, suite2)
        self.put_profile(allowed_components=["Adder"])  # 变更配置
        self.call(self.teacher, "POST", f"/test-suites/{suite2['id']}/publish",
                  {"validation_id": validation2}, 409)
        detail = self.call(self.teacher, "GET", f"/test-suites/{full_suite['id']}").json["data"]
        self.assertEqual(detail["total_count"], 8)
        suites = self.call(self.teacher, "GET",
                           f"/experiment-versions/{self.version_id}/test-suites?status=published").json
        self.assertEqual(suites["total"], 1)

    def test_publish_closed_loop_and_active_suite(self):
        # 覆盖 R04（experiments 发布闸门）：initial_test_suite_id 非 published 409、
        # 验证身份不匹配 409；成功后 experiment_grading 建立，后续切换仅改绑定。
        self.put_profile()
        draft_suite = self.create_suite()
        # 未发布的测试集不能作为 initial suite。
        self.call(self.teacher, "POST", f"/experiment-versions/{self.version_id}/publish",
                  {"start_at": "2026-10-12T02:00:00Z", "end_at": "2026-10-20T02:00:00Z",
                   "initial_test_suite_id": draft_suite["id"]}, 409)
        suite = self.create_suite()
        validation_id = self.pass_validation(self.version_id, suite)
        self.publish_suite(self.version_id, suite, validation_id)
        # 验证不匹配（先改 profile 再发布）→ 409 保持 draft。
        self.put_profile(allowed_components=["Adder"])
        self.call(self.teacher, "POST", f"/experiment-versions/{self.version_id}/publish",
                  {"start_at": "2026-10-12T02:00:00Z", "end_at": "2026-10-20T02:00:00Z",
                   "initial_test_suite_id": suite["id"]}, 409)
        detail = self.call(self.teacher, "GET",
                           f"/experiment-versions/{self.version_id}").json["data"]
        self.assertEqual(detail["status"], "draft")
        # 恢复一致配置后发布成功。
        self.put_profile()
        self.call(self.teacher, "POST", f"/experiment-versions/{self.version_id}/publish",
                  {"start_at": "2026-10-12T02:00:00Z", "end_at": "2026-10-20T02:00:00Z",
                   "initial_test_suite_id": suite["id"]}, 200)
        # 后续切换 active suite：revision CAS；旧 revision 409；未发布套件 400。
        suite2 = self.create_suite()
        validation2 = self.pass_validation(self.version_id, suite2)
        self.publish_suite(self.version_id, suite2, validation2)
        switched = self.call(self.teacher, "PUT",
                             f"/experiment-versions/{self.version_id}/active-test-suite",
                             {"test_suite_id": suite2["id"], "revision": 1}).json["data"]
        self.assertEqual(switched["revision"], 2)
        self.call(self.teacher, "PUT", f"/experiment-versions/{self.version_id}/active-test-suite",
                  {"test_suite_id": suite["id"], "revision": 1}, 409)
        self.call(self.teacher, "PUT", f"/experiment-versions/{self.version_id}/active-test-suite",
                  {"test_suite_id": draft_suite["id"], "revision": 2}, 400)

    # ---------- 学生提交（AC-01/02/03/07、R18） ----------

    def test_student_submission_and_run_flow(self):
        # 覆盖 AC-01/AC-02/AC-03：窗口内名单学生提交 202 即排队；
        # 预检失败 4xx 不创建任务；轮询 run 到终态。
        version_id, _suite, _published = self.publish_circuit()
        first = self.submit(self.student, version_id)
        self.assertEqual(first["status"], "queued")
        run = self._get_run(self.student, first["run_id"])
        self.assertEqual(run["status"], "queued")
        self.assertEqual(run["total_count"], 8)
        self.finish_run(first["run_id"], passed_cases=8)
        run = self._get_run(self.student, first["run_id"])
        self.assertEqual(run["status"], "accepted")
        self.assertEqual(run["score"], 100.0)
        # AC-04：公开用例给输入/期望/实际，隐藏用例仅汇总。
        self.assertEqual(len(run["public_cases"]), 4)
        public_labels = {case["label"] for case in run["public_cases"]}
        self.assertEqual(public_labels, {"add-1", "and-1", "shl-1", "xor-1"})
        self.assertEqual(run["public_cases"][0]["expected"], [{"Y": 8}])
        self.assertEqual(run["public_cases"][0]["actual"], [{"Y": 8}])
        self.assertEqual(run["hidden_summary"], {"total": 4, "passed": 4, "failures": []})
        for case in run["public_cases"]:
            self.assertTrue(case["passed"])
        # AC-03：伪 XML / 端口位宽不符 / 白名单外元件 / 错扩展名 / 超2MiB。
        self.submit(self.student, version_id, content=b"not xml", status=400)
        bad_pin = CIRC.replace('val="A"/><a name="width" val="8"', 'val="A"/><a name="width" val="4"')
        self.submit(self.student, version_id, content=bad_pin.encode(), status=400)
        rogue = CIRC.replace('name="Adder"', 'name="HDLLoader"')
        self.submit(self.student, version_id, content=rogue.encode(), status=400)
        self.submit(self.student, version_id, filename="alu.txt", status=400)
        self.submit(self.student, version_id, content=b"x" * (2 * 1024 * 1024 + 1), status=413)
        # 预检失败不建任务：runs 仍只有一条。
        detail = self.call(self.student, "GET",
                           f"/submissions/{first['submission_id']}").json["data"]
        self.assertEqual(detail["latest_run"]["id"], first["run_id"])

    def test_submission_idempotency_and_limits(self):
        # 覆盖 AC-07/R18：同键同指纹重放原响应；同键异指纹 409；
        # 每实验最多2个排队/运行、每分钟3次、队列100上限（AC-11）。
        version_id, _suite, _published = self.publish_circuit()
        key = str(uuid4())
        first = self.submit(self.student, version_id, key=key)
        replay = self.submit(self.student, version_id, key=key)
        self.assertEqual(replay["run_id"], first["run_id"])
        self.submit(self.student, version_id, key=key,
                    content=CIRC.replace("8", "7").encode(), status=409)
        # 第2个活跃任务允许，第3个 429。
        second = self.submit(self.student, version_id)
        self.submit(self.student, version_id, status=429)
        self.finish_run(first["run_id"], 8)
        self.finish_run(second["run_id"], 8)
        # 每分钟3次：已用2次（first/second），第3次允许、第4次 429（R18）。
        self.submit(self.student, version_id)
        self.submit(self.student, version_id, status=429)
        # 队列容量：注入100个 queued 后 503。
        self._fill_queue(version_id, 100)
        self.submit(self.student2, version_id, status=503)

    def _fill_queue(self, version_id, count):
        with closing(connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            teacher_id = db.execute("SELECT id FROM user WHERE student_no='T018TEACH'").fetchone()[0]
            suite_id = db.execute("SELECT active_suite_id FROM experiment_grading "
                                  "WHERE experiment_version_id=?", (version_id,)).fetchone()[0]
            profile = db.execute("SELECT * FROM judge_profile WHERE experiment_version_id=?",
                                 (version_id,)).fetchone()
            for index in range(count):
                file_id = db.execute(
                    "INSERT INTO file_object(owner_id,storage_key,original_name,media_type,"
                    "size_bytes,sha256,purpose,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (teacher_id, f"q{index}", "q.circ", "application/xml", 10, f"h{index}",
                     "grading_submission", AT)).lastrowid
                submission_id = db.execute(
                    "INSERT INTO submission(experiment_version_id,student_id,file_id,file_sha256,"
                    "size_bytes,filename,created_at) VALUES(?,?,?,?,?,?,?)",
                    (version_id, teacher_id, file_id, f"h{index}", 10, "q.circ", AT)).lastrowid
                db.execute(
                    "INSERT INTO grading_run(submission_id,suite_id,engine_version,jar_sha256,"
                    "status,total_count,profile_snapshot_json,profile_sha256,suite_sha256,"
                    "created_at) VALUES(?,?,?,NULL,'queued',0,'{}',?,?,?)",
                    (submission_id, suite_id, profile["engine_version"],
                     profile["canonical_sha256"], "c", AT))
            db.commit()

    def test_effective_run_semantics(self):
        # 覆盖 R19/AC-12：回退范围是同一 submission 内（重评/重试）；
        # 最新 run system_error 时回退到此前最近一次有效评分，不覆盖旧成绩。
        version_id, _suite, _published = self.publish_circuit()
        first = self.submit(self.student, version_id)
        self.finish_run(first["run_id"], passed_cases=6)  # wrong_answer 75分
        submission_id = first["submission_id"]
        # 教师重评产生同 submission 的第二个 run，引擎崩溃 → system_error。
        regrade = self.call(self.teacher, "POST",
                            f"/submissions/{submission_id}/regrades",
                            {"reason": "复核"}, 202,
                            headers_extra={"Idempotency-Key": str(uuid4())}).json["data"]
        self.finish_run(regrade["run_id"], passed_cases=0, error="ENGINE_CRASH")
        detail = self.call(self.student, "GET",
                           f"/submissions/{submission_id}").json["data"]
        self.assertEqual(detail["latest_run"]["status"], "system_error")
        self.assertEqual(detail["latest_run"]["error_code"], "ENGINE_CRASH")
        self.assertEqual(detail["effective_run"]["status"], "wrong_answer")
        self.assertEqual(detail["effective_run"]["score"], 75.0)
        self.assertEqual(detail["effective_run"]["id"], first["run_id"])
        # 管理员重试成功 → 最新有效成绩变为 accepted（不回退旧 wrong_answer）。
        retry = self.call(self.admin, "POST",
                          f"/admin/grading-runs/{regrade['run_id']}/retry",
                          {"reason": "worker lost"}, 202,
                          headers_extra={"Idempotency-Key": str(uuid4())}).json["data"]
        self.finish_run(retry["run_id"], passed_cases=8)
        detail = self.call(self.student, "GET",
                           f"/submissions/{submission_id}").json["data"]
        self.assertEqual(detail["latest_run"]["status"], "accepted")
        self.assertEqual(detail["effective_run"]["status"], "accepted")
        self.assertEqual(detail["effective_run"]["score"], 100.0)
        runs = self.call(self.student, "GET",
                         f"/submissions/{submission_id}/runs").json
        self.assertEqual(runs["total"], 3)

    def test_result_isolation_and_permissions(self):
        # 覆盖 AC-06：学生不可见隐藏用例向量/他人提交；教师限定本人课程；
        # 学生不能重评或下载他人文件；无幂等键拒绝。
        version_id, _suite, _published = self.publish_circuit()
        submission = self.submit(self.student, version_id)
        self.finish_run(submission["run_id"], passed_cases=4)
        run = self._get_run(self.student, submission["run_id"])
        self.assertEqual(len(run["public_cases"]), 4)
        # AC-06：隐藏用例标签与向量都不出现在响应中（仅汇总计数）。
        run_json = json.dumps(run)
        for label in ("sub-1", "or-1", "not-1", "shr-1"):
            self.assertNotIn(f'"{label}"', run_json)
        # 前4用例通过：public 2/4、hidden 2/4（顺序 add,sub,and,or,xor,not,shl,shr）。
        self.assertEqual(run["hidden_summary"]["passed"], 2)
        # 他人 run/提交 404；下载他人文件 404。
        self._get_run(self.student2, submission["run_id"], status=404)
        self.call(self.student2, "GET",
                  f"/submissions/{submission['submission_id']}", status=404)
        headers = {"Origin": ORIGIN}
        download = self.student2.get(
            f"/api/v1/submissions/{submission['submission_id']}/file", headers=headers)
        self.assertEqual(download.status_code, 404)
        own = self.student.get(f"/api/v1/submissions/{submission['submission_id']}/file",
                               headers=headers)
        self.assertEqual(own.status_code, 200)
        self.assertIn("attachment", own.headers.get("Content-Disposition", ""))
        own.close()  # 释放 send_file 句柄，避免 Windows 下临时目录清理失败。
        # 本课程教师可见并可下载；他课教师不可见（404）；学生重评 403。
        self.call(self.teacher, "GET", f"/submissions/{submission['submission_id']}")
        self.call(self.teacher2, "GET",
                  f"/submissions/{submission['submission_id']}", status=404)
        self.call(self.student, "POST", f"/submissions/{submission['submission_id']}/regrades",
                  {"reason": "x"}, 403, headers_extra={"Idempotency-Key": str(uuid4())})
        # 缺 Idempotency-Key 的重评与提交拒绝（幂等执行顺序，APIC 第11节）。
        headers_csrf = {"Origin": ORIGIN, "X-CSRF-Token": self.teacher.csrf}
        response = self.teacher.post(
            f"/api/v1/submissions/{submission['submission_id']}/regrades",
            json={"reason": "重评"}, headers=headers_csrf)
        self.assertEqual(response.status_code, 400)
        # wiring-only 版本不接受 circuit 提交（模块边界）。
        wiring_only = self.create_version(("wiring",), title="w only")
        self.call(self.teacher, "POST", f"/experiment-versions/{wiring_only}/publish",
                  {"start_at": "2026-10-12T02:00:00Z", "end_at": "2026-10-20T02:00:00Z"}, 200)
        self.submit(self.student, wiring_only, status=409)

    def test_window_roster_and_freeze(self):
        # 覆盖 R16/窗口：名单外学生 403；窗口外 409 WINDOW_CLOSED；
        # 发布后名单固化（experiment_participant 快照不随后续加退课漂移）。
        version_id, _suite, _published = self.publish_circuit()
        # 未加入课程的学生：课程不可见（APIC 总则）→ 404。
        self.submit(self.student3, version_id, status=404)
        # 发布后再加入课程的学生不在冻结名单 → 403。
        self.call(self.teacher, "POST", self.course+"/members",
                  {"user_id": self._uid(self.student3), "member_role": "student"}, 201)
        self.submit(self.student3, version_id, status=403)
        # 窗口外：start 在未来。
        version2 = self.create_version(("circuit",), title="v2 future")
        self.put_profile(version2)
        suite2 = self.create_suite(version2)
        validation2 = self.pass_validation(version2, suite2)
        self.publish_suite(version2, suite2, validation2)
        self.call(self.teacher, "POST", f"/experiment-versions/{version2}/publish",
                  {"start_at": "2026-10-14T02:00:00Z", "end_at": "2026-10-20T02:00:00Z",
                   "initial_test_suite_id": suite2["id"]}, 200)
        self.submit(self.student, version2, status=409)
        # 教师移除名单内学生：课程成员资格失效 → 404（course_access 先于名单检查；
        # R16 名单快照保留用于历史分母统计，不代表退课后仍可提交）。
        self.call(self.teacher, "DELETE",
                  f"{self.course}/members/{self._uid(self.student)}", status=204)
        self.submit(self.student, version_id, status=404)

    def test_teacher_regrade_and_admin_retry(self):
        # 覆盖 AC-08：教师重评（可指定套件）产生新 run；
        # 管理员重试仅 system_error、retry_of 链≤2（APIC 第7节）。
        version_id, _suite, _published = self.publish_circuit()
        submission = self.submit(self.student, version_id)
        self.finish_run(submission["run_id"], passed_cases=0, error="ENGINE_CRASH")
        # 系统错误终态释放活跃限制，教师可重评；重评排队期间再评 → 409。
        regrade = self.call(self.teacher, "POST",
                            f"/submissions/{submission['submission_id']}/regrades",
                            {"reason": "引擎故障重评"}, 202,
                            headers_extra={"Idempotency-Key": str(uuid4())}).json["data"]
        self.call(self.teacher, "POST",
                  f"/submissions/{submission['submission_id']}/regrades",
                  {"reason": "again"}, 409, headers_extra={"Idempotency-Key": str(uuid4())})
        self.finish_run(regrade["run_id"], passed_cases=8)
        detail = self.call(self.teacher, "GET",
                           f"/submissions/{submission['submission_id']}").json["data"]
        self.assertEqual(detail["effective_run"]["status"], "accepted")
        # 管理员重试：非 system_error 终态 409。
        self.call(self.admin, "POST", f"/admin/grading-runs/{regrade['run_id']}/retry",
                  {"reason": "x"}, 409)
        # retry_of 链≤2：system_error 重评 run 可重试两次，第三次 409。
        regrade2 = self.call(self.teacher, "POST",
                             f"/submissions/{submission['submission_id']}/regrades",
                             {"reason": "再评故障"}, 202,
                             headers_extra={"Idempotency-Key": str(uuid4())}).json["data"]
        self.finish_run(regrade2["run_id"], passed_cases=0, error="WORKER_LOST")
        retry1 = self.call(self.admin, "POST",
                           f"/admin/grading-runs/{regrade2['run_id']}/retry",
                           {"reason": "chain 1"}, 202,
                           headers_extra={"Idempotency-Key": str(uuid4())}).json["data"]
        self.assertEqual(retry1["retry_of"], regrade2["run_id"])
        self.finish_run(retry1["run_id"], passed_cases=0, error="WORKER_LOST")
        retry2 = self.call(self.admin, "POST",
                           f"/admin/grading-runs/{retry1['run_id']}/retry",
                           {"reason": "chain 2"}, 202,
                           headers_extra={"Idempotency-Key": str(uuid4())}).json["data"]
        self.finish_run(retry2["run_id"], passed_cases=0, error="WORKER_LOST")
        self.call(self.admin, "POST", f"/admin/grading-runs/{retry2['run_id']}/retry",
                  {"reason": "chain 3"}, 409,
                  headers_extra={"Idempotency-Key": str(uuid4())})

    def test_course_submissions_listing(self):
        # 覆盖 R02/R41：教师班级全部、学生仅本人；分页与筛选。
        version_id, _suite, _published = self.publish_circuit()
        one = self.submit(self.student, version_id)
        self.finish_run(one["run_id"], 8)
        two = self.submit(self.student2, version_id)
        self.finish_run(two["run_id"], 6)
        teacher_view = self.call(self.teacher, "GET",
                                 f"{self.course}/submissions").json
        self.assertEqual(teacher_view["total"], 2)
        student_view = self.call(self.student, "GET",
                                 f"{self.course}/submissions").json
        self.assertEqual(student_view["total"], 1)
        self.assertEqual(student_view["data"][0]["student_id"], self._uid(self.student))
        self.assertEqual(student_view["data"][0]["effective_run"]["score"], 100.0)
        filtered = self.call(self.teacher, "GET",
                             f"{self.course}/submissions?status=wrong_answer").json
        self.assertEqual(filtered["total"], 1)
        paged = self.call(self.teacher, "GET",
                          f"{self.course}/submissions?page=1&page_size=1").json
        self.assertEqual(len(paged["data"]), 1)
        self.assertEqual(paged["total"], 2)
        self.call(self.student, "GET",
                  f"{self.course}/submissions?student_id={self._uid(self.student2)}", status=403)
        # 他课教师：课程不可见（APIC 总则，非成员统一 404）。
        self.call(self.teacher2, "GET", f"{self.course}/submissions", status=404)
