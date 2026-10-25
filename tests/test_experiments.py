"""T009 real SPEC-001 session/course/CSRF/SQL-runner integration for experiments.

Only account bootstrap is seeded. All experiment, chapter and knowledge operations
use actual API handlers and cookies; no auth, CSRF or migration mocks.

覆盖来源标注：每条用例注释其对应 T009 验收索引（PRD 第13节）：
AC01 指导完整 / AC02 两类提交入口 / AC03 本人历史版本 / AC04 模块边界；
R02 列表可达 / R04 电路配置门槛 / R16 冻结名单 / R41 列表分页。
"""

import copy
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
TEST_NOW = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)
AT = "2026-10-13T08:00:00Z"
PASSWORD = "correct horse battery staple 42"


def exp01_panel():
    """结构合法的 EXP-01 面板（开关 A/B/OP、ALU8、指示灯），每次返回新对象。"""
    return {
        "schema_version": 1,
        "components": [
            {"id": "sw-a", "type": "SWITCH", "params": {"width": 8, "initial": 5},
             "ports": {"OUT": "t-sw-a"}},
            {"id": "sw-b", "type": "SWITCH", "params": {"width": 8, "initial": 3},
             "ports": {"OUT": "t-sw-b"}},
            {"id": "sw-op", "type": "SWITCH", "params": {"width": 3, "initial": 0},
             "ports": {"OUT": "t-sw-op"}},
            {"id": "alu", "type": "ALU8", "params": {},
             "ports": {"A": "t-alu-a", "B": "t-alu-b", "OP": "t-alu-op",
                       "Y": "t-alu-y", "Z": "t-alu-z", "C": "t-alu-c"}},
            {"id": "led-y", "type": "LED", "params": {"width": 8}, "ports": {"IN": "t-led-y"}},
            {"id": "led-z", "type": "LED", "params": {"width": 1}, "ports": {"IN": "t-led-z"}},
            {"id": "led-c", "type": "LED", "params": {"width": 1}, "ports": {"IN": "t-led-c"}},
        ],
        "terminals": [
            {"id": "t-sw-a", "component_id": "sw-a", "name": "A", "direction": "out", "width": 8,
             "required": True},
            {"id": "t-sw-b", "component_id": "sw-b", "name": "B", "direction": "out", "width": 8,
             "required": True},
            {"id": "t-sw-op", "component_id": "sw-op", "name": "OP", "direction": "out", "width": 3,
             "required": True},
            {"id": "t-alu-a", "component_id": "alu", "name": "A", "direction": "in", "width": 8,
             "required": True},
            {"id": "t-alu-b", "component_id": "alu", "name": "B", "direction": "in", "width": 8,
             "required": True},
            {"id": "t-alu-op", "component_id": "alu", "name": "OP", "direction": "in", "width": 3,
             "required": True},
            {"id": "t-alu-y", "component_id": "alu", "name": "Y", "direction": "out", "width": 8,
             "required": True},
            {"id": "t-alu-z", "component_id": "alu", "name": "Z", "direction": "out", "width": 1,
             "required": False},
            {"id": "t-alu-c", "component_id": "alu", "name": "C", "direction": "out", "width": 1,
             "required": False},
            {"id": "t-led-y", "component_id": "led-y", "name": "Y", "direction": "in", "width": 8,
             "required": True},
            {"id": "t-led-z", "component_id": "led-z", "name": "Z", "direction": "in", "width": 1,
             "required": False},
            {"id": "t-led-c", "component_id": "led-c", "name": "C", "direction": "in", "width": 1,
             "required": False},
        ],
        "layout": {"columns": 3},
    }


RULES = {"require_required_inputs": True, "hidden": {"expected_y": "8"}}


class ExperimentsTest(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.path = Path(self.temporary.name)/"course.db"
        self.password = secrets.token_urlsafe(24)
        migrate(self.path)
        self.app = create_app({"TESTING": True, "TEST_NOW": TEST_NOW, "DATABASE_PATH": str(self.path),
                               "SECRET_KEY": secrets.token_hex(32), "APP_ORIGIN": ORIGIN})
        with closing(connect(self.path)) as db:
            for number, role in (("T009ADMIN", "admin"), ("T009TEACH", "teacher"),
                                 ("T009TEACH2", "teacher")):
                db.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                           "VALUES(?,?,?,?,1,?,?)", (number, number, generate_password_hash(self.password),
                                                    role, AT, AT))
        self.admin, self.teacher, self.teacher2, self.student, self.student2, self.student3 = [
            self.app.test_client() for _ in range(6)]
        self.login(self.admin, "T009ADMIN")
        self.login(self.teacher, "T009TEACH")
        self.login(self.teacher2, "T009TEACH2")
        for client, number in ((self.student, "T009STUD1"), (self.student2, "T009STUD2"),
                               (self.student3, "T009STUD3")):
            self.call(client, "POST", "/auth/register", {
                "student_no": number, "name": number, "password": self.password}, 201)
            self.login(client, number)
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        teacher2_id = self.teacher2.get("/api/v1/auth/session").json["data"]["user"]["id"]
        course = self.call(self.admin, "POST", "/courses", {
            "title": "T009 controlled CPU", "teacher_id": teacher_id}, 201)
        self.course_id = course.json["data"]["id"]
        self.course = f"/courses/{self.course_id}"
        self.call(self.teacher, "POST", self.course+"/members",
                  {"user_id": self._uid(self.student), "member_role": "student"}, 201)
        self.call(self.teacher, "POST", self.course+"/members",
                  {"user_id": self._uid(self.student2), "member_role": "student"}, 201)
        course2 = self.call(self.admin, "POST", "/courses", {
            "title": "T009 empty course", "teacher_id": teacher2_id}, 201)
        self.course2_id = course2.json["data"]["id"]
        self.course2 = f"/courses/{self.course2_id}"
        chapter = self.call(self.teacher, "POST", self.course+"/chapters", {"title": "CPU"}, 201)
        self.knowledge_id = self.call(self.teacher, "POST",
                                      f"/chapters/{chapter.json['data']['id']}/knowledge-points", {
                                          "title": "程序计数器", "content": "<p>PC 指向下一条指令</p>",
                                          "published": True, "is_foundational": True}, 201).json["data"]["id"]
        chapter2 = self.call(self.teacher2, "POST", self.course2+"/chapters", {"title": "其他课程"}, 201)
        self.other_knowledge_id = self.call(self.teacher2, "POST",
                                            f"/chapters/{chapter2.json['data']['id']}/knowledge-points", {
                                                "title": "外部知识点", "content": "x", "published": True}, 201
                                            ).json["data"]["id"]

    def tearDown(self):
        self.temporary.cleanup()

    def login(self, client, number):
        data = self.call(client, "POST", "/auth/login",
                         {"student_no": number, "password": self.password}).json["data"]
        client.csrf = data["csrf_token"]

    def _uid(self, client):
        return client.get("/api/v1/auth/session").json["data"]["user"]["id"]

    def call(self, client, method, path, payload=None, status=200):
        headers = {"Origin": ORIGIN, "X-CSRF-Token": getattr(client, "csrf", "")}
        response = getattr(client, method.lower())(f"/api/v1{path}", json=payload, headers=headers)
        assert response.status_code == status, (path, response.status_code, response.json)
        return response

    def create_experiment(self, client=None, course=None, code="EXP-01", title="8位ALU", status=201):
        client = client or self.teacher
        course = course or self.course
        response = self.call(client, "POST", f"{course}/experiments", {
            "code": code, "title": title, "description": "组合逻辑实验"}, status)
        return response.json.get("data", response.json)

    def create_version(self, experiment_id, modes=("wiring",), panel="default",
                       rules=None, knowledge=None, title="v标题", status=201,
                       client=None, **extra):
        payload = {
            "title": title,
            "objectives": "理解ALU运算",
            "knowledge_ids": [self.knowledge_id] if knowledge is None else knowledge,
            "instructions": "1. 连接 A/B/OP；2. 观察指示灯",
            "submission_modes": list(modes),
            "rules": copy.deepcopy(RULES) if rules is None else rules,
        }
        if panel == "default":
            payload["panel"] = exp01_panel()
        elif panel is not None:
            payload["panel"] = panel
        payload.update(extra)
        response = self.call(client or self.teacher, "POST", f"/experiments/{experiment_id}/versions",
                             payload, status)
        return response.json.get("data", response.json)

    def publish(self, version_id, status=200, client=None, start="2026-10-14T02:00:00Z",
                end="2026-10-20T02:00:00Z", **extra):
        payload = {"start_at": start, "end_at": end}
        payload.update(extra)
        response = self.call(client or self.teacher, "POST", f"/experiment-versions/{version_id}/publish",
                             payload, status)
        return response.json.get("data", response.json)

    def publish_ready(self):
        """创建 EXP-01 实验并发布 v1（wiring 提交，含 student/student2）。

        circuit 模式的发布依赖 SPEC-018 的判分配置，本分支内不可发布（R04）。
        """
        experiment = self.create_experiment()
        version = self.create_version(experiment["id"], modes=("wiring",))
        published = self.publish(version["id"])
        return experiment, version, published

    def test_ac01_full_guidance_visible_to_teacher(self):
        # 覆盖 T009-AC01（指导完整：目标/器件/步骤/验证/关联知识点）。
        experiment = self.create_experiment()
        version = self.create_version(experiment["id"])
        detail = self.call(self.teacher, "GET", f"/experiment-versions/{version['id']}").json["data"]
        self.assertEqual(detail["objectives"], "理解ALU运算")
        self.assertEqual(detail["instructions"], "1. 连接 A/B/OP；2. 观察指示灯")
        self.assertEqual(detail["knowledge_ids"], [self.knowledge_id])
        self.assertEqual(len(detail["panel"]["components"]), 7)
        self.assertEqual(detail["rules"]["require_required_inputs"], True)
        self.assertEqual(detail["rules"]["hidden"], {"expected_y": "8"})
        self.assertEqual(detail["experiment"]["code"], "EXP-01")

    def test_ac01_student_rules_sanitized(self):
        # 覆盖 T009-AC01/APIC：学生不可见隐藏 rules 答案。
        _, _, published = self.publish_ready()
        detail = self.call(self.student, "GET", f"/experiment-versions/{published['id']}").json["data"]
        self.assertEqual(detail["rules"], {"require_required_inputs": True})
        self.assertNotIn("hidden", detail["rules"])

    def test_ac02_submission_modes_roundtrip(self):
        # 覆盖 T009-AC02（两类提交入口：wiring 与 circuit 并存）。
        experiment = self.create_experiment()
        both = self.create_version(experiment["id"], modes=("wiring", "circuit"))
        self.assertEqual(both["submission_modes"], ["wiring", "circuit"])
        exp03 = self.create_experiment(code="EXP-03", title="数据通路连线")
        wiring_only = self.create_version(exp03["id"], modes=("wiring",))
        self.assertEqual(wiring_only["submission_modes"], ["wiring"])
        exp04 = self.create_experiment(code="EXP-04", title="简易CPU")
        circuit_only = self.create_version(exp04["id"], modes=("circuit",), panel=None)
        self.assertEqual(circuit_only["submission_modes"], ["circuit"])
        self.assertIsNone(circuit_only["panel"])

    def test_ac02_circuit_draft_readable_without_config(self):
        # 覆盖 T009-AC02/R04：circuit 草稿无配置可创建/读取，judge_profile_id 为 null。
        exp04 = self.create_experiment(code="EXP-04", title="简易CPU")
        version = self.create_version(exp04["id"], modes=("circuit",), panel=None)
        self.assertIsNone(version["judge_profile_id"])
        detail = self.call(self.teacher, "GET", f"/experiment-versions/{version['id']}").json["data"]
        self.assertIsNone(detail["judge_profile_id"])
        self.assertEqual(detail["status"], "draft")

    def test_ac03_student_sees_own_history_versions(self):
        # 覆盖 T009-AC03（本人历史版本）：发布 v1、v2 后学生能看到两个版本。
        experiment, _, published = self.publish_ready()
        version2 = self.create_version(experiment["id"], title="v2标题")
        published2 = self.publish(version2["id"])
        listed = self.call(self.student, "GET",
                           f"{self.course}/experiment-versions?experiment_id={experiment['id']}").json
        self.assertEqual([row["id"] for row in listed["data"]], [published2["id"], published["id"]])
        self.assertEqual([row["version"] for row in listed["data"]], [2, 1])
        experiments = self.call(self.student, "GET", self.course+"/experiments").json
        self.assertEqual(experiments["data"][0]["latest_version"]["id"], published2["id"])

    def test_ac04_module_boundary(self):
        # 覆盖 T009-AC04（模块边界）：本模块不提供 017 连线端点；
        # 018 评测端点已在 SPEC-018 分支落地，不再 404。
        self.call(self.student, "GET", "/wiring-attempts/1", status=404)

    def test_r02_student_finds_version_from_list(self):
        # 覆盖 T009-R02：学生从列表获得版本 id 后打开详情，不手工猜 ID。
        _, _, _published = self.publish_ready()
        experiments = self.call(self.student, "GET", self.course+"/experiments").json["data"]
        self.assertEqual(len(experiments), 1)
        version_id = experiments[0]["latest_version"]["id"]
        detail = self.call(self.student, "GET", f"/experiment-versions/{version_id}").json["data"]
        self.assertEqual(detail["id"], version_id)

    def test_r04_circuit_publish_requires_config(self):
        # 覆盖 T009-R04：缺判分配置发布 409 且保持 draft。
        exp04 = self.create_experiment(code="EXP-04", title="简易CPU")
        version = self.create_version(exp04["id"], modes=("circuit",), panel=None)
        self.publish(version["id"], status=409, initial_test_suite_id=1)
        detail = self.call(self.teacher, "GET", f"/experiment-versions/{version['id']}").json["data"]
        self.assertEqual(detail["status"], "draft")
        self.assertIsNone(detail["start_at"])
        self.assertIsNone(detail["end_at"])

    def test_r04_reject_client_judge_profile_id(self):
        # 覆盖 T009-R04：创建版本不接收服务端派生字段 judge_profile_id。
        experiment = self.create_experiment()
        self.create_version(experiment["id"], status=400, judge_profile_id=7)

    def test_r16_participants_frozen_at_publish(self):
        # 覆盖 T009-R16：发布后加入的学生不在名单，退课不改历史分母。
        experiment, _, published = self.publish_ready()
        self.assertEqual(published["participant_count"], 2)
        self.call(self.teacher, "POST", self.course+"/members",
                  {"user_id": self._uid(self.student3), "member_role": "student"}, 201)
        experiments = self.call(self.student3, "GET", self.course+"/experiments").json
        self.assertEqual(experiments["data"], [])
        self.call(self.student3, "GET", f"/experiment-versions/{published['id']}", status=404)
        versions = self.call(self.student3, "GET",
                             f"{self.course}/experiment-versions?experiment_id={experiment['id']}").json
        self.assertEqual(versions["data"], [])
        detail = self.call(self.teacher, "GET", f"/experiment-versions/{published['id']}").json["data"]
        self.assertEqual(detail["participant_count"], 2)
        with closing(connect(self.path)) as db:
            db.execute("UPDATE course_member SET active=0 WHERE course_id=? AND user_id=?",
                       (self.course_id, self._uid(self.student2)))
            db.commit()
        detail = self.call(self.teacher, "GET", f"/experiment-versions/{published['id']}").json["data"]
        self.assertEqual(detail["participant_count"], 2)

    def test_r41_empty_lists_and_real_total_beyond_last_page(self):
        # 覆盖 T009-R41：空列表 200 且 data=[]、分页字段与 request_id 完整；末页以外保留真实 total。
        empty = self.call(self.student, "GET", self.course+"/experiments").json
        self.assertEqual(empty["data"], [])
        self.assertEqual(empty["total"], 0)
        self.assertEqual(empty["page"], 1)
        self.assertEqual(empty["page_size"], 20)
        self.assertIn("request_id", empty)
        empty_versions = self.call(self.student, "GET", self.course+"/experiment-versions").json
        self.assertEqual(empty_versions["data"], [])
        self.assertEqual(empty_versions["total"], 0)
        self.assertIn("request_id", empty_versions)
        self.publish_ready()
        beyond = self.call(self.student, "GET", self.course+"/experiments?page=5&page_size=20").json
        self.assertEqual(beyond["data"], [])
        self.assertEqual(beyond["total"], 1)
        self.assertEqual(beyond["page"], 5)

    def test_publish_validations(self):
        # 覆盖 APIC 发布契约：窗口、重复发布、模式组合、空名单。
        experiment = self.create_experiment()
        version = self.create_version(experiment["id"])
        self.publish(version["id"], status=400, start="2026-10-20T02:00:00Z",
                     end="2026-10-14T02:00:00Z")
        self.publish(version["id"], status=400, start="2026-10-14T02:00:00Z",
                     end="2026-10-14T02:00:00Z")
        self.publish(version["id"])
        self.publish(version["id"], status=409)
        exp03 = self.create_experiment(code="EXP-03", title="数据通路连线")
        mixed = self.create_version(exp03["id"], modes=("wiring", "circuit"))
        self.publish(mixed["id"], status=409)
        detail = self.call(self.teacher, "GET", f"/experiment-versions/{mixed['id']}").json["data"]
        self.assertEqual(detail["status"], "draft")
        exp03_wiring = self.create_version(exp03["id"], modes=("wiring",), title="仅连线")
        self.publish(exp03_wiring["id"])
        empty_course_experiment = self.create_experiment(client=self.teacher2, course=self.course2,
                                                         code="EXP-01", title="空课程实验")
        empty_course_version = self.create_version(empty_course_experiment["id"], client=self.teacher2,
                                                   knowledge=[])
        self.publish(empty_course_version["id"], status=422, client=self.teacher2)

    def test_wiring_publish_requires_panel_and_rules(self):
        # 覆盖 APIC 发布契约：wiring 模式需端子和规则完整（circuit-only 版本无 panel 时不可按 wiring 发布）。
        experiment = self.create_experiment()
        version = self.create_version(experiment["id"])
        with closing(connect(self.path)) as db:
            db.execute("UPDATE experiment_version SET panel_json=NULL WHERE id=?", (version["id"],))
            db.commit()
        self.publish(version["id"], status=409)

    def test_notifications_sent_on_publish(self):
        # 覆盖 APIC 第9节：实验版本发布冻结名单并向每个学生生成一次通知。
        experiment, _, published = self.publish_ready()
        notifications = self.call(self.student, "GET", "/notifications").json
        row = notifications["data"][0]
        self.assertEqual(row["target_type"], "experiment_version")
        self.assertEqual(row["target_id"], published["id"])
        self.assertIn(experiment["title"], row["title"])
        self.assertEqual(notifications["total"], 1)

    def test_permissions(self):
        # 覆盖 T009 共通越权矩阵：学生/他课教师/课程外成员。
        experiment = self.create_experiment()
        self.call(self.student, "POST", self.course+"/experiments", {
            "code": "EXP-02", "title": "寄存器", "description": "x"}, 403)
        self.call(self.student, "POST", f"/experiments/{experiment['id']}/versions", {
            "title": "t", "objectives": "o", "knowledge_ids": [], "instructions": "i",
            "submission_modes": ["circuit"], "rules": {}}, 403)
        version = self.create_version(experiment["id"])
        self.call(self.student, "POST", f"/experiment-versions/{version['id']}/publish", {
            "start_at": "2026-10-14T02:00:00Z", "end_at": "2026-10-20T02:00:00Z"}, 403)
        self.call(self.teacher2, "GET", self.course+"/experiments", status=404)
        self.call(self.teacher2, "POST", f"/experiments/{experiment['id']}/versions", {
            "title": "t", "objectives": "o", "knowledge_ids": [], "instructions": "i",
            "submission_modes": ["circuit"], "rules": {}}, 404)
        self.call(self.student, "GET", f"/experiment-versions/{version['id']}", status=404)
        self.publish(version["id"])
        self.call(self.student3, "GET", f"/experiment-versions/{version['id']}", status=404)
        self.call(self.admin, "GET", self.course+"/experiments", status=404)

    def test_version_input_validation(self):
        # 覆盖 APIC 版本契约：modes/panel/rules/knowledge 输入校验。
        experiment = self.create_experiment()
        self.create_version(experiment["id"], modes=(), status=400)
        self.create_version(experiment["id"], modes=("wiring", "wiring"), status=400)
        self.create_version(experiment["id"], modes=("both",), status=400)
        self.create_version(experiment["id"], modes=("wiring",), panel=None, status=400)
        bad = exp01_panel()
        bad["schema_version"] = 2
        self.create_version(experiment["id"], panel=bad, status=400)
        bad = exp01_panel()
        bad["components"][3]["type"] = "GPU"
        self.create_version(experiment["id"], panel=bad, status=400)
        bad = exp01_panel()
        bad["terminals"][0]["width"] = 4
        self.create_version(experiment["id"], panel=bad, status=400)
        bad = exp01_panel()
        bad["terminals"][1]["id"] = "t-sw-a"
        self.create_version(experiment["id"], panel=bad, status=400)
        bad = exp01_panel()
        bad["components"][0]["params"]["width"] = 5
        self.create_version(experiment["id"], panel=bad, status=400)
        bad = exp01_panel()
        bad["components"][0]["params"]["initial"] = 256
        self.create_version(experiment["id"], panel=bad, status=400)
        self.create_version(experiment["id"], rules="must-be-object", status=400)
        self.create_version(experiment["id"], rules={"hidden": "must-be-object"}, status=400)
        self.create_version(experiment["id"], knowledge=[self.other_knowledge_id], status=400)
        self.create_version(experiment["id"], knowledge=["x"], status=400)
        self.create_version(experiment["id"], title="", status=400)
        self.create_version(experiment["id"], objectives="", status=400)
        self.create_version(experiment["id"], instructions="", status=400)

    def test_experiment_create_validation(self):
        # 覆盖 APIC 实验契约：code 白名单、同课程唯一、入参校验。
        self.create_experiment(code="EXP-05", status=400)
        self.create_experiment(title="", status=400)
        self.call(self.teacher, "POST", self.course+"/experiments",
                  {"code": "EXP-01", "title": "缺描述"}, 400)
        self.create_experiment()
        self.create_experiment(status=409)
        self.create_experiment(code="EXP-02", title="寄存器与总线")

    def test_version_increment_and_immutability(self):
        # 覆盖 DBD：版本号自增、definition_sha256 区分、发布后内容不变。
        experiment = self.create_experiment()
        first = self.create_version(experiment["id"])
        second = self.create_version(experiment["id"], title="第二版")
        self.assertEqual((first["version"], second["version"]), (1, 2))
        with closing(connect(self.path)) as db:
            digests = [row["definition_sha256"] for row in db.execute(
                "SELECT definition_sha256 FROM experiment_version WHERE experiment_id=? "
                "ORDER BY version", (experiment["id"],))]
        self.assertNotEqual(digests[0], digests[1])
        self.publish(first["id"])
        after = self.call(self.teacher, "GET", f"/experiment-versions/{first['id']}").json["data"]
        self.assertEqual(after["objectives"], first["objectives"])
        self.assertEqual(after["instructions"], first["instructions"])
        self.assertEqual(after["panel"], first["panel"])
        self.assertEqual(after["status"], "published")

    def test_teacher_sees_drafts_student_only_published(self):
        # 覆盖 T009-AC03/R02：教师版本列表含 draft，学生仅见参与名单内已发布。
        experiment = self.create_experiment()
        draft = self.create_version(experiment["id"])
        teacher_versions = self.call(self.teacher, "GET",
                                     f"{self.course}/experiment-versions?experiment_id={experiment['id']}").json
        self.assertEqual([row["status"] for row in teacher_versions["data"]], ["draft"])
        self.assertEqual(teacher_versions["total"], 1)
        student_versions = self.call(self.student, "GET",
                                     f"{self.course}/experiment-versions?experiment_id={experiment['id']}").json
        self.assertEqual(student_versions["data"], [])
        self.publish(draft["id"])
        student_versions = self.call(self.student, "GET",
                                     f"{self.course}/experiment-versions?experiment_id={experiment['id']}").json
        self.assertEqual([row["status"] for row in student_versions["data"]], ["published"])
        self.assertEqual(student_versions["total"], 1)
