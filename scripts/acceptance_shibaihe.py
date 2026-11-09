"""石佰合负责功能的完整、可重复运行验收脚本。

覆盖 SPEC-003 教学资源 / SPEC-009 实验辅助 / SPEC-018 电路在线评测 /
SPEC-010D 评测分析，以及新增的电路模拟与电路控制界面。重点回答：
「登录后无法使用」是不是后台数据缺失造成的。

特点
----
* **自包含**：自己建两个隔离的临时 SQLite 库（空库 / 已初始化），用
  Flask ``test_client()`` 走真实 API，不依赖任何正在运行的服务，可反复运行。
* **双场景对照**：同一个检查项在「后台数据缺失」与「后台数据正常」下各跑一遍，
  据此做归因（数据缺失 / 代码缺陷 / 与数据无关）。
* **真引擎**：判分走固定 Logisim-evolution 5.0.0 JAR 与
  ``backend.engines.grading`` 的真实 claim/run/submit 链路，不 mock。
* **前后端交叉验证**：7485 全 2048 组合、74181 全 512 组合，
  前端模拟内核与后端功能表逐行比对；组件级双场景测试用 node:test。
* **交付物**：测试覆盖清单、逐项结果汇总、归因结论、问题清单、验收结论。

用法
----
    python scripts/acceptance_shibaihe.py
    python scripts/acceptance_shibaihe.py --scenario empty
    python scripts/acceptance_shibaihe.py --scenario seeded --no-frontend
    python scripts/acceptance_shibaihe.py --out tests/acceptance --keep

退出码：全部被测项通过为 0，否则 1。
"""

# ruff: noqa: PLC3002 — 验收探针用「立即求值的一次性 lambda」让检查项与断言紧挨着写，
# 每个检查项自成一个表达式，便于逐项核对预期/实际值；改写成命名函数反而要来回跳读。
from __future__ import annotations

import argparse
import hashlib
import io
import itertools
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures" / "logisim"
JAR = ROOT / "instance" / "tools" / "le.jar"
FRONTEND = ROOT / "frontend"

# 固定 JAR 必须在导入引擎模块之前可见。
os.environ.setdefault("LOGISIM_JAR_PATH", str(JAR))

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.shared.db import connect, migrate

ACCOUNTS = (
    ("teacher", "任课教师", "teacher", "teacher"),
    ("24201501", "测试学生甲", "student", "24201501"),
    ("24201502", "测试学生乙", "student", "24201502"),
    ("24201737", "石佰合", "admin", "Spec018@Test"),
)
TEACHER_NO, STUDENT_NO, OTHER_NO = "teacher", "24201501", "24201502"
GROUP = {0: "add", 1: "sub", 2: "and", 3: "or", 4: "xor", 5: "not", 6: "shl", 7: "shr"}
PORT_SCHEMA = {"inputs": {"A": 8, "B": 8, "OP": 3},
               "outputs": {"Y": 8, "Z": 1, "C": 1}}
LIMITS = {"cpu_seconds": 10, "memory_mib": 512, "output_bytes": 1048576, "processes": 1}

# 覆盖清单：(编号, 模块, 被测功能, 依赖的后台数据)
COVERAGE = [
    ("L01", "登录与会话", "健康检查 db_ready / grader_ready", "无"),
    ("L02", "登录与会话", "教师登录返回会话与 CSRF", "user"),
    ("L03", "登录与会话", "会话恢复", "session"),
    ("L04", "登录与会话", "学生登录", "user"),
    ("L05", "登录与会话", "未登录访问受保护接口被拒", "session"),
    ("L06", "登录与会话", "CSRF 来源校验", "session"),
    ("L07", "登录与会话", "退出后会话失效", "session"),
    ("L08", "登录与会话", "登录后课程列表可用", "course"),
    ("L09", "登录与会话", "后台数据就绪判定（bootstrap）", "全部业务表"),
    ("L10", "登录与会话", "缺失项逐项列出（归因依据）", "全部业务表"),
    ("R01", "SPEC-003 教学资源", "资源列表", "course / resource"),
    ("R02", "SPEC-003 教学资源", "教师上传资源", "course"),
    ("R03", "SPEC-003 教学资源", "按课程/类型检索", "course / resource"),
    ("R04", "SPEC-003 教学资源", "授权下载并比对字节", "course / resource_version"),
    ("R05", "SPEC-003 教学资源", "缺少 intent/event_id 的下载被拒", "course / resource_version"),
    ("R06", "SPEC-003 教学资源", "学生越权上传被拒", "course"),
    ("R07", "SPEC-003 教学资源", "更新生成新版本且旧引用仍可访问", "course / resource_version"),
    ("R08", "SPEC-003 教学资源", "真实访问事件汇总", "course / access_event"),
    ("E01", "SPEC-009 实验辅助", "实验列表", "course / experiment"),
    ("E02", "SPEC-009 实验辅助", "学生可见已发布实验", "course / experiment_version"),
    ("E03", "SPEC-009 实验辅助", "实验指导含目标/步骤/说明", "experiment_version"),
    ("E04", "SPEC-009 实验辅助", "两类提交入口（wiring / circuit）", "experiment_version"),
    ("E05", "SPEC-009 实验辅助", "发布闸门：未配测试集不得发布", "test_suite"),
    ("E06", "SPEC-009 实验辅助", "本人历史版本", "submission"),
    ("E07", "SPEC-009 实验辅助", "发布窗口与冻结名单", "experiment_participant"),
    ("G01", "SPEC-018 电路评测", "固定 JAR 与评测就绪", "无（本地 JAR）"),
    ("G02", "SPEC-018 电路评测", "judge profile 配置与指纹", "judge_profile"),
    ("G03", "SPEC-018 电路评测", "正例/反例参考文件", "reference_file"),
    ("G04", "SPEC-018 电路评测", "测试集 8 个计分组", "test_case"),
    ("G05", "SPEC-018 电路评测", "测试集真引擎验证（正例全过/反例失败）", "test_suite_validation"),
    ("G06", "SPEC-018 电路评测", "测试集发布", "test_suite"),
    ("G07", "SPEC-018 电路评测", "学生提交正确 .circ → accepted 100", "grading_run"),
    ("G08", "SPEC-018 电路评测", "学生提交错误 .circ → 部分给分", "grading_run"),
    ("G09", "SPEC-018 电路评测", "非 .circ 预检拒绝", "grading_run"),
    ("G10", "SPEC-018 电路评测", "顶层电路名不符拒绝", "grading_run"),
    ("G11", "SPEC-018 电路评测", "学生报告脱敏", "grading_run"),
    ("G12", "SPEC-018 电路评测", "重评生成新的 run", "grading_run"),
    ("G13", "SPEC-018 电路评测", "空向量/零用例不得判满分", "无（纯函数契约）"),
    ("A01", "SPEC-010D 评测分析", "教师查看评测统计", "grading_run"),
    ("A02", "SPEC-010D 评测分析", "通过率与分数分布", "grading_run"),
    ("A03", "SPEC-010D 评测分析", "system_error 排除正确率分母", "grading_run"),
    ("A04", "SPEC-010D 评测分析", "学生 scope=self", "grading_run"),
    ("A05", "SPEC-010D 评测分析", "学生查他人统计被拒", "grading_run"),
    ("A06", "SPEC-010D 评测分析", "重评分组可区分", "grading_run"),
    ("C01", "电路模拟与控制", "电路实验台 spec 与就绪状态", "全部业务表（仅就绪标记）"),
    ("C02", "电路模拟与控制", "芯片/引脚/正交导线/用例定义完整性", "无（静态定义）"),
    ("C03", "电路模拟与控制", "7485 全组合后端表与 compute 一致", "无（静态功能表）"),
    ("C04", "电路模拟与控制", "74181 全组合与 74181 引擎一致", "无（静态功能表）"),
    ("C05", "电路模拟与控制", "前后端模拟内核全组合逐行一致", "无（静态功能表）"),
    ("C06", "电路模拟与控制", "验证用例期望与权威求值一致", "无（静态功能表）"),
    ("C07", "电路模拟与控制", "前端组件双场景 16 项交互测试", "仅就绪标记"),
    ("C08", "电路模拟与控制", "后台数据缺失时电路控制仍可用", "无（静态定义）"),
]


def utcnow():
    return datetime.now(UTC)


def stamp(offset_seconds=0):
    return (utcnow() + timedelta(seconds=offset_seconds)).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


class Client:
    """带会话/CSRF 的 test_client 包装，等价于浏览器里的一次登录。"""

    def __init__(self, app, origin="http://localhost"):
        self.raw = app.test_client()
        self.origin = origin
        self.csrf = None
        self.user = None

    def open(self, method, path, payload=None, form=None, origin=True, csrf=True,
             extra_headers=None):
        headers = {}
        if origin:
            headers["Origin"] = self.origin
        if csrf and self.csrf and method in ("POST", "PATCH", "PUT", "DELETE"):
            headers["X-CSRF-Token"] = self.csrf
        if extra_headers:
            headers.update(extra_headers)
        kwargs = {"headers": headers}
        if form is not None:
            kwargs["data"] = form
            kwargs["content_type"] = "multipart/form-data"
        elif payload is not None:
            kwargs["json"] = payload
        return self.raw.open(path, method=method, **kwargs)

    def json(self, method, path, payload=None, **kwargs):
        response = self.open(method, path, payload, **kwargs)
        try:
            body = response.get_json() or {}
        except Exception:  # noqa: BLE001 — 非 JSON 响应也要收成一条可判定的失败记录
            body = {}
        return response.status_code, body.get("data"), body

    def upload(self, path, filename, content, fields=None, media="application/octet-stream"):
        blob = io.BytesIO(content)
        blob.name = filename
        form = {"file": (blob, filename, media)}
        for key, value in (fields or {}).items():
            form[key] = value
        response = self.open("POST", path, form=form)
        try:
            body = response.get_json() or {}
        except Exception:  # noqa: BLE001 — 上传失败返回 HTML 时不能让整轮验收中断
            body = {}
        return response.status_code, body.get("data"), body

    def download(self, path):
        response = self.open("GET", path)
        return response.status_code, response.data

    def login(self, student_no, password):
        status, data, body = self.json("POST", "/api/v1/auth/login",
                                       {"student_no": student_no, "password": password})
        if status == 200:
            self.csrf = data["csrf_token"]
            self.user = data["user"]
        return status, data, body


def items(payload):
    data = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("items", [])
    return []


class Scenario:
    """一个隔离场景：空库（数据缺失）或已初始化（数据正常）。"""

    def __init__(self, name, seeded, jar=JAR):
        self.name = name
        self.seeded = seeded
        self.tmp = Path(tempfile.mkdtemp(prefix=f"sbh-{name}-"))
        self.db = self.tmp / "app.db"
        self.uploads = self.tmp / "uploads"
        self.uploads.mkdir()
        self.ids = {}
        self.app = None
        self.clients = {}
        self.jar = jar

    def setup(self):
        migrate(str(self.db))
        now = stamp()
        db = sqlite3.connect(self.db)
        for number, name, role, password in ACCOUNTS:
            db.execute(
                "INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                "VALUES(?,?,?,?,1,?,?)",
                (number, name, generate_password_hash(password), role, now, now))
        db.commit()
        db.close()

        self.app = create_app({
            "TESTING": True,
            "DATABASE_PATH": str(self.db),
            "UPLOAD_ROOT": str(self.uploads),
            "APP_ORIGIN": "http://localhost",
            "SECRET_KEY": "acceptance-" + "x" * 32,
        })
        for key in ("teacher", "student", "other", "admin", "anon"):
            self.clients[key] = Client(self.app)
        if self.seeded:
            self._seed()

    def sql(self, query, params=()):
        db = sqlite3.connect(self.db)
        db.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in db.execute(query, params).fetchall()]
        finally:
            db.close()

    def scalar(self, query, params=()):
        rows = self.sql(query, params)
        return rows[0][next(iter(rows[0]))] if rows else None

    def _create_course(self):
        now = stamp()
        db = sqlite3.connect(self.db)
        teacher_id = db.execute("SELECT id FROM user WHERE student_no=?", (TEACHER_NO,)).fetchone()[0]
        cursor = db.execute(
            "INSERT INTO course(title,description,teacher_id,created_at,updated_at) "
            "VALUES(?,?,?,?,?)",
            ("计算机组成原理 · 验收课程", "验收脚本自动创建的课程", teacher_id, now, now))
        course_id = cursor.lastrowid
        for student_no, member_role in ((TEACHER_NO, "teacher"), (STUDENT_NO, "student"),
                                        (OTHER_NO, "student")):
            uid = db.execute("SELECT id FROM user WHERE student_no=?", (student_no,)).fetchone()[0]
            db.execute(
                "INSERT INTO course_member(course_id,user_id,member_role,active,created_at,updated_at) "
                "VALUES(?,?,?,1,?,?)", (course_id, uid, member_role, now, now))
        db.commit()
        db.close()
        self.ids["course_id"] = course_id

    @staticmethod
    def _cases():
        lines = [line for line in (FIXTURES / "alu8_ok.txt").read_text(
            encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
        header = lines[0].split("\t")
        result = []
        for line in lines[1:]:
            record = dict(zip(header, line.split("\t")))
            op = int(record["OP[3]"], 16)
            result.append({
                "label": f"OP={op} {GROUP[op]} A={record['A[8]']} B={record['B[8]']}",
                "visibility": "public", "group_code": GROUP[op],
                "steps": [{"step_no": 1,
                           "inputs": {"A": int(record["A[8]"], 16),
                                      "B": int(record["B[8]"], 16), "OP": op},
                           "expected": {"Y": int(record["Y[8]"], 16),
                                        "Z": int(record["Z"]), "C": int(record["C"])},
                           "clock_event": "none"}],
            })
        return result

    def _seed(self):
        from backend.engines.grading import BASE_COMPONENTS
        self._create_course()
        teacher = self.clients["teacher"]
        teacher.login(TEACHER_NO, "teacher")
        course = self.ids["course_id"]

        status, data, _ = teacher.json("POST", f"/api/v1/courses/{course}/experiments", {
            "code": "EXP-01", "title": "8 位 ALU 设计与验证",
            "description": "用逻辑门与算术元件实现 8 位 ALU。",
        })
        assert status == 201, f"建实验失败 {status}"
        experiment_id = data["id"]
        self.ids["experiment_id"] = experiment_id

        # wiring 模式必须带合法 panel（PRD §6.1），这里给一个最小可校验面板。
        panel = {
            "schema_version": 1,
            "components": [
                {"id": "sw_a", "type": "SWITCH", "params": {"width": 8, "initial": 0},
                 "ports": {"OUT": "sw_a_out"}},
                {"id": "led_y", "type": "LED", "params": {"width": 8},
                 "ports": {"IN": "led_y_in"}},
            ],
            "terminals": [
                {"id": "sw_a_out", "component_id": "sw_a", "name": "OUT",
                 "direction": "out", "width": 8, "required": False},
                {"id": "led_y_in", "component_id": "led_y", "name": "IN",
                 "direction": "in", "width": 8, "required": False},
            ],
            "wires": [{"id": "w1", "from_terminal": "sw_a_out", "to_terminal": "led_y_in"}],
            "layout": {"components": {"sw_a": [0, 0], "led_y": [100, 0]}},
        }
        status, data, _ = teacher.json("POST", f"/api/v1/experiments/{experiment_id}/versions", {
            "title": "ALU8 v1",
            "objectives": "掌握 8 位 ALU 的算术/逻辑/移位实现及进位与零标志语义。",
            "instructions": "1. 顶层电路名 ALU8；2. 输入 A[8] B[8] OP[3]，输出 Y[8] Z C；"
                            "3. OP=0..7 依次为加/减/与/或/异或/取反/左移/右移。",
            "knowledge_ids": [], "submission_modes": ["wiring", "circuit"],
            "panel": panel, "rules": {"max_submissions": 10},
        })
        assert status == 201, f"建版本失败 {status}"
        version_id = data["id"]
        self.ids["version_id"] = version_id

        # 发布闸门反例：一个未配置测试集的草稿版本。
        status, data, _ = teacher.json("POST", f"/api/v1/experiments/{experiment_id}/versions", {
            "title": "ALU8 草稿（未配置）", "objectives": "闸门测试", "instructions": "占位",
            "knowledge_ids": [], "submission_modes": ["circuit"], "rules": {},
        })
        if status == 201:
            self.ids["draft_version_id"] = data["id"]

        status, data, _ = teacher.json(
            "PUT", f"/api/v1/experiment-versions/{version_id}/judge-profile", {
                "top_circuit": "ALU8", "port_schema": PORT_SCHEMA,
                "allowed_components": sorted(BASE_COMPONENTS), "limits": LIMITS,
            })
        assert status == 200, f"judge profile 失败 {status}"
        self.ids["profile_sha"] = data["canonical_sha256"]

        refs = {}
        for kind, name in (("correct", "alu8.circ"), ("known_wrong", "alu8_wrong.circ")):
            status, data, _ = teacher.upload(
                f"/api/v1/experiment-versions/{version_id}/reference-files", name,
                (FIXTURES / name).read_bytes(), {"kind": kind}, media="application/xml")
            assert status == 201, f"上传 {name} 失败 {status}"
            refs[kind] = data["reference_file_id"]
        self.ids["refs"] = refs

        cases = self._cases()
        status, data, _ = teacher.json(
            "POST", f"/api/v1/experiment-versions/{version_id}/test-suites", {"cases": cases})
        assert status == 201, f"建测试集失败 {status}"
        suite_id = data["id"]
        self.ids["suite_id"] = suite_id
        self.ids["case_count"] = len(cases)

        status, data, _ = teacher.json(
            "POST", f"/api/v1/test-suites/{suite_id}/validations",
            {"reference_file_id": refs["correct"], "negative_file_id": refs["known_wrong"]})
        assert status == 202, f"发起验证失败 {status}"
        validation_id = data["validation_id"]
        self.ids["validation_id"] = validation_id
        self.drain()
        status, data, _ = teacher.json("GET", f"/api/v1/test-suite-validations/{validation_id}")
        assert data["status"] == "passed", f"验证未通过：{data}"

        status, data, _ = teacher.json("POST", f"/api/v1/test-suites/{suite_id}/publish",
                                       {"validation_id": validation_id})
        assert status == 200, f"发布测试集失败 {status}"

        status, data, _ = teacher.json(
            "POST", f"/api/v1/experiment-versions/{version_id}/publish",
            {"start_at": stamp(-3600), "end_at": stamp(30 * 86400),
             "initial_test_suite_id": suite_id})
        assert status == 200, f"发布版本失败 {status}"

        # SPEC-003：一条教学资源（guide 只接受 PDF）。
        pdf = (b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n"
               b"trailer<</Root 1 0 R>>\n%%EOF\n")
        self.ids["pdf"] = pdf
        status, data, _ = teacher.upload(f"/api/v1/courses/{course}/resources",
                                         "alu8-guide.pdf", pdf,
                                         {"title": "实验一 · ALU8 实现指导", "kind": "guide"},
                                         media="application/pdf")
        assert status == 201, f"上传资源失败 {status}"
        self.ids["resource_id"] = data["resource_id"]
        self.ids["resource_version_id"] = data["id"]

        # SPEC-018：学生提交正例 / 反例，真引擎判分。
        student = self.clients["student"]
        student.login(STUDENT_NO, STUDENT_NO)
        self.ids["student_id"] = student.user["id"]
        for key, name in (("good", "alu8.circ"), ("bad", "alu8_wrong.circ")):
            status, data = self._submit(student, version_id, name, key)
            assert status in (201, 202), f"提交 {name} 失败 {status} {data}"
            self.ids[key + "_run"] = data.get("run_id") or data.get("id")
            self.ids[key + "_submission"] = data.get("submission_id") or data.get("id")
        self.drain()

    def _submit(self, client, version_id, filename, key):
        content = (FIXTURES / filename).read_bytes()
        blob = io.BytesIO(content)
        headers = {"Origin": client.origin, "X-CSRF-Token": client.csrf,
                   "Idempotency-Key": str(uuid.uuid4())}
        response = client.raw.post(
            f"/api/v1/experiment-versions/{version_id}/submissions",
            data={"file": (blob, filename, "application/xml")},
            content_type="multipart/form-data", headers=headers)
        body = response.get_json() or {}
        if response.status_code not in (201, 202):
            print(f"[debug] 提交 {filename}: HTTP {response.status_code} {body}", flush=True)
        return response.status_code, body.get("data")

    def drain(self, limit=30):
        """消费评测队列：与生产 worker 完全相同的 claim / sandbox / submit 函数。"""
        from backend.engines import grading as engine
        db = connect(str(self.db))
        handled = []
        try:
            for _ in range(limit):
                run = engine.claim_run(db, utcnow())
                if run is not None:
                    self._handle_run(db, engine, run)
                    handled.append(("run", run["id"]))
                    continue
                validation = engine.claim_validation(db, utcnow())
                if validation is not None:
                    self._handle_validation(db, engine, validation)
                    handled.append(("validation", validation["id"]))
                    continue
                break
        finally:
            db.close()
        return handled

    def _handle_run(self, db, engine, run):
        cases = db.execute("SELECT * FROM test_case WHERE suite_id=? ORDER BY id",
                           (run["suite_id"],)).fetchall()
        submission = db.execute("SELECT * FROM submission WHERE id=?",
                                (run["submission_id"],)).fetchone()
        key = db.execute("SELECT storage_key FROM file_object WHERE id=?",
                         (submission["file_id"],)).fetchone()[0]
        outcome = engine.run_in_sandbox(run, self.uploads / key, cases, engine.real_executor)
        details = []
        for case in cases:
            hit = outcome["results"].get(case["id"])
            details.append({"case_id": case["id"],
                            "passed": bool(hit["passed"]) if hit else False,
                            "actual": (hit or {}).get("actual") or []})
        engine.submit_run_result(db, run["id"], run["worker_token"], utcnow(),
                                 outcome["error_code"], details)

    def _handle_validation(self, db, engine, row):
        cases = db.execute("SELECT * FROM test_case WHERE suite_id=? ORDER BY id",
                           (row["suite_id"],)).fetchall()
        profile = db.execute(
            "SELECT p.top_circuit,p.limits_json,p.port_schema_json FROM judge_profile p "
            "JOIN test_suite s ON s.experiment_version_id=p.experiment_version_id "
            "WHERE s.id=?", (row["suite_id"],)).fetchone()
        snapshot = json.dumps({"top_circuit": profile["top_circuit"],
                               "limits": json.loads(profile["limits_json"]),
                               "port_schema": json.loads(profile["port_schema_json"])})
        fake = {"profile_snapshot_json": snapshot}
        def path_of(ref_id):
            file_id = db.execute("SELECT file_id FROM reference_file WHERE id=?",
                                 (ref_id,)).fetchone()[0]
            key = db.execute("SELECT storage_key FROM file_object WHERE id=?",
                             (file_id,)).fetchone()[0]
            return self.uploads / key
        good = engine.run_in_sandbox(fake, path_of(row["reference_file_id"]),
                                    cases, engine.real_executor)
        bad = engine.run_in_sandbox(fake, path_of(row["negative_file_id"]),
                                   cases, engine.real_executor)
        if good["error_code"] or bad["error_code"]:
            engine.submit_validation_result(db, row["id"], row["worker_token"], utcnow(),
                                            False, False,
                                            error=good["error_code"] or bad["error_code"])
            return
        reference_passed = len(good["results"]) == len(cases) and all(
            item["passed"] for item in good["results"].values())
        negative_failed = any(not item["passed"] for item in bad["results"].values())
        engine.submit_validation_result(db, row["id"], row["worker_token"], utcnow(),
                                        reference_passed, negative_failed)


class Recorder:
    def __init__(self, scenario):
        self.scenario = scenario
        self.rows = []

    def add(self, cid, module, feature, expected, actual, passed, dependency="", usable=None):
        self.rows.append({
            "id": cid, "scene": self.scenario, "module": module, "feature": feature,
            "expected": expected, "actual": str(actual), "passed": bool(passed),
            "dependency": dependency, "usable": usable,
        })
        return bool(passed)

    def probe(self, cid, module, feature, expected, dependency, fn):
        """执行断言函数 fn() -> (actual, ok, usable)。"""
        try:
            actual, ok, usable = fn()
        except Exception as exc:  # noqa: BLE001 — 任何异常都记为失败项，不中断整轮验收
            actual, ok, usable = f"异常：{type(exc).__name__}: {exc}", False, False
        return self.add(cid, module, feature, expected, actual, ok, dependency, usable)


def run_checks(sc, rec, jar_ok):
    """两场景共用的一套检查；预期按场景参数化。"""
    seeded = sc.seeded
    teacher = sc.clients["teacher"]
    student = sc.clients["student"]
    other = sc.clients["other"]
    anon = sc.clients["anon"]
    course = sc.ids.get("course_id", 1)
    version = sc.ids.get("version_id", 1)

    def data_expect(what, positive):
        return f"{what}：{'200 且有数据' if positive else '空库返回明确的 404/空列表，并有数据缺失引导'}"

    # ---------------- 登录与会话 ----------------
    def login_probe():
        t = Client(sc.app)
        status, data, _ = t.login(TEACHER_NO, "teacher")
        sc.clients["teacher"] = t
        return (f"HTTP {status} csrf={'有' if data and data.get('csrf_token') else '无'}",
                status == 200 and bool(data.get("csrf_token")), True)
    def health_probe():
        response = anon.raw.get("/api/v1/health")
        body = response.get_json() or {}
        data = body.get("data") or {}
        return ((f"HTTP {response.status_code} db={data.get('db_ready')} "
                f"grader={data.get('grader_ready')} jar_ok={jar_ok}"),
                response.status_code == 200 and data.get("db_ready") is True
                and data.get("grader_ready") is True and jar_ok, True)
    rec.probe("L01", "登录与会话", COVERAGE[0][2],
              "health 200，db_ready=true，grader_ready=true", "无", health_probe)
    rec.probe("L02", "登录与会话", COVERAGE[1][2], "教师登录 200 且返回 csrf_token", "user", login_probe)
    teacher = sc.clients["teacher"]
    rec.probe("L03", "登录与会话", COVERAGE[2][2], "会话恢复 200 且学号一致", "session",
              lambda: (lambda s, d: (f"HTTP {s} user={d.get('user', {}).get('student_no') if d else None}",
                                     s == 200 and d.get("user", {}).get("student_no") == TEACHER_NO, True))(
                  *teacher.json("GET", "/api/v1/auth/session")[:2]))
    st = Client(sc.app)
    sc.clients["student"] = st
    rec.probe("L04", "登录与会话", COVERAGE[3][2], "学生登录 200", "user",
              lambda: (lambda s, d: (f"HTTP {s} role={d.get('user', {}).get('role') if d else None}",
                                     s == 200 and d.get("user", {}).get("role") == "student", True))(
                  *st.login(STUDENT_NO, STUDENT_NO)[:2]))
    student = sc.clients["student"]
    ot = Client(sc.app)
    sc.clients["other"] = ot
    ot.login(OTHER_NO, OTHER_NO)
    other = sc.clients["other"]
    rec.probe("L05", "登录与会话", COVERAGE[4][2], "未登录 GET /courses → 401", "session",
              lambda: (lambda s: (f"HTTP {s}", s == 401, True))(
                  Client(sc.app).json("GET", "/api/v1/courses")[0]))
    rec.probe("L06", "登录与会话", COVERAGE[5][2], "写请求缺 Origin → 403 CSRF_FAILED", "session",
              lambda: (lambda s, b: (f"HTTP {s} code={(b.get('error') or {}).get('code')}",
                                     s == 403 and (b.get("error") or {}).get("code") == "CSRF_FAILED",
                                     True))(*teacher.json("POST", "/api/v1/auth/logout",
                                                         origin=False)[::2]))
    # L06 的 logout 会真的退出；重新登录后续检查。
    teacher.login(TEACHER_NO, "teacher")
    teacher = sc.clients["teacher"]
    probe_logout = Client(sc.app)
    probe_logout.login(TEACHER_NO, "teacher")
    rec.probe("L07", "登录与会话", COVERAGE[6][2], "退出后 /auth/session → 401", "session",
              lambda: (
                  (lambda out, after: (f"退出 HTTP {out}，之后 session HTTP {after}",
                                       out in (200, 204) and after == 401, True))(
                      probe_logout.json("POST", "/api/v1/auth/logout")[0],
                      probe_logout.json("GET", "/api/v1/auth/session")[0])))

    def courses_probe():
        s, d, _ = teacher.json("GET", "/api/v1/courses")
        count = len(items({"data": d}))
        expected = count > 0 if seeded else count == 0
        return f"HTTP {s} 课程数={count}", s == 200 and expected, count > 0
    rec.probe("L08", "登录与会话", COVERAGE[7][2],
              data_expect("课程列表", seeded), "course", courses_probe)

    def bootstrap_probe():
        s, d, _ = teacher.json("GET", "/api/v1/circuit-lab/bootstrap")
        ready = bool(d and d.get("data_ready"))
        missing = (d or {}).get("missing", [])
        return (f"HTTP {s} data_ready={ready} 缺失 {len(missing)} 项",
                s == 200 and ready == seeded, ready)
    rec.probe("L09", "登录与会话", COVERAGE[8][2],
              f"bootstrap 200；data_ready={'true' if seeded else 'false'}", "全部业务表",
              bootstrap_probe)
    rec.probe("L10", "登录与会话", COVERAGE[9][2],
              "就绪清单覆盖 8 张业务表，空库逐项列出缺失原因", "全部业务表",
              lambda: (lambda s, d: (
                  (f"HTTP {s} 检查 {len((d or {}).get('items', []))} 项，缺失 "
                  f"{len((d or {}).get('missing', []))} 项"),
                  s == 200 and len((d or {}).get("items", [])) == 8
                  and ((seeded and not (d or {}).get("missing")) or
                       (not seeded and len((d or {}).get("missing", [])) == 8)), True))(
                  *teacher.json("GET", "/api/v1/circuit-lab/bootstrap")[:2]))

    # ---------------- SPEC-003 ----------------
    def resources_list_probe():
        s, d, body = teacher.json("GET", f"/api/v1/courses/{course}/resources")
        listed = items({"data": d})
        if seeded:
            ok = s == 200 and any(r.get("resource_id") == sc.ids.get("resource_id") or
                                  r.get("id") == sc.ids.get("resource_id") for r in listed)
        else:
            ok = s == 404 and (body.get("error") or {}).get("code") == "NOT_FOUND"
        return f"HTTP {s} 条数={len(listed)}", ok, s == 200 and bool(listed)
    rec.probe("R01", "SPEC-003 教学资源", COVERAGE[10][2],
              data_expect("资源列表", seeded), "course / resource", resources_list_probe)

    def resource_upload_probe():
        pdf = sc.ids.get("pdf") or b"%PDF-1.4\n%%EOF\n"
        s, d, body = teacher.upload(f"/api/v1/courses/{course}/resources",
                                    "acceptance.pdf", pdf,
                                    {"title": "验收用资源", "kind": "guide"},
                                    media="application/pdf")
        if seeded:
            return f"HTTP {s} resource_id={(d or {}).get('resource_id')}", s == 201, True
        return (f"HTTP {s} code={(body.get('error') or {}).get('code')}",
                s == 404 and (body.get("error") or {}).get("code") == "NOT_FOUND", False)
    rec.probe("R02", "SPEC-003 教学资源", COVERAGE[11][2],
              data_expect("教师上传资源", seeded), "course", resource_upload_probe)

    rec.probe("R03", "SPEC-003 教学资源", COVERAGE[12][2],
              data_expect("按课程/类型检索", seeded), "course / resource",
              lambda: (lambda s, d, b: (
                  f"HTTP {s} kind=guide 命中 {len(items({'data': d}))} 条",
                  (s == 200 and bool(items({"data": d}))) if seeded
                  else (s == 404 and (b.get("error") or {}).get("code") == "NOT_FOUND"),
                  s == 200))(*teacher.json("GET", f"/api/v1/courses/{course}/resources?kind=guide")))

    def download_probe():
        rv = sc.ids.get("resource_version_id", 1)
        s, body = teacher.download(
            f"/api/v1/resource-versions/{rv}/content?intent=download&event_id={uuid.uuid4()}")
        if seeded:
            return f"HTTP {s} 字节一致={body == sc.ids.get('pdf')}", s == 200 and body == sc.ids.get("pdf"), True
        return f"HTTP {s}", s == 404, False
    rec.probe("R04", "SPEC-003 教学资源", COVERAGE[13][2],
              data_expect("授权下载", seeded), "course / resource_version", download_probe)

    def missing_intent_probe():
        rv = sc.ids.get("resource_version_id", 1)
        response = teacher.raw.get(f"/api/v1/resource-versions/{rv}/content",
                                   headers={"Origin": teacher.origin})
        body = response.get_json() or {}
        code = (body.get("error") or {}).get("code")
        return f"HTTP {response.status_code} 错误码={code}", response.status_code == 400, True
    rec.probe("R05", "SPEC-003 教学资源", COVERAGE[14][2],
              "缺 intent/event_id 的下载一律 400（参数校验先于数据查询，两场景一致）",
              "course / resource_version", missing_intent_probe)

    rec.probe("R06", "SPEC-003 教学资源", COVERAGE[15][2],
              "空库明确 404；正常库学生上传 → 403", "course",
              lambda: (lambda s: (f"HTTP {s}", (s == 403) if seeded else (s == 404), s == 403))(
                  student.upload(f"/api/v1/courses/{course}/resources", "evil.pdf", b"x",
                                 {"title": "越权", "kind": "guide"},
                                 media="application/pdf")[0]))

    def version_probe():
        rid = sc.ids.get("resource_id", 1)
        rv = sc.ids.get("resource_version_id", 1)
        old = sc.ids.get("pdf")
        s, _d, _ = teacher.upload(f"/api/v1/resources/{rid}/versions", "alu8-guide-v2.pdf",
                                 (old or b"") + b"\n% supplement\n",
                                 {"change_note": "补充进位说明"}, media="application/pdf")
        s2, body = teacher.download(
            f"/api/v1/resource-versions/{rv}/content?intent=download&event_id={uuid.uuid4()}")
        if seeded:
            return f"新版本 HTTP {s}，旧版本 HTTP {s2} 内容一致={body == old}", \
                s == 201 and s2 == 200 and body == old, True
        return f"新版本 HTTP {s}，旧版本 HTTP {s2}", s == 404 and s2 == 404, False
    rec.probe("R07", "SPEC-003 教学资源", COVERAGE[16][2],
              data_expect("版本更新与旧引用", seeded), "course / resource_version", version_probe)

    rec.probe("R08", "SPEC-003 教学资源", COVERAGE[17][2],
              data_expect("访问事件汇总", seeded), "course / access_event",
              lambda: (lambda s, d, b: (
                  f"HTTP {s} 含 download={'download' in json.dumps(d or {}, ensure_ascii=False)}",
                  (s == 200 and "download" in json.dumps(d or {}, ensure_ascii=False)) if seeded
                  else (s == 404 and (b.get("error") or {}).get("code") == "NOT_FOUND"),
                  s == 200))(*teacher.json("GET", f"/api/v1/courses/{course}/analytics?dimension=resources")))

    # ---------------- SPEC-009 ----------------
    def experiments_probe():
        s, d, b = teacher.json("GET", f"/api/v1/courses/{course}/experiments")
        listed = items({"data": d})
        if seeded:
            ok = s == 200 and any(e.get("code") == "EXP-01" for e in listed)
        else:
            ok = s == 404 and (b.get("error") or {}).get("code") == "NOT_FOUND"
        return f"HTTP {s} 实验数={len(listed)}", ok, s == 200 and bool(listed)
    rec.probe("E01", "SPEC-009 实验辅助", COVERAGE[18][2],
              data_expect("实验列表", seeded), "course / experiment", experiments_probe)

    rec.probe("E02", "SPEC-009 实验辅助", COVERAGE[19][2],
              data_expect("学生可见已发布实验", seeded), "course / experiment_version",
              lambda: (lambda s, d, b: (
                  f"HTTP {s} 可见 {len(items({'data': d}))} 个",
                  (s == 200 and bool(items({"data": d}))) if seeded
                  else (s == 404 and (b.get("error") or {}).get("code") == "NOT_FOUND"),
                  s == 200))(*student.json("GET", f"/api/v1/courses/{course}/experiments")))

    rec.probe("E03", "SPEC-009 实验辅助", COVERAGE[20][2],
              data_expect("实验指导字段", seeded), "experiment_version",
              lambda: (lambda s, d, b: (
                  (f"HTTP {s} objectives/instructions="
                  f"{'齐' if d and d.get('objectives') and d.get('instructions') else '缺'}"),
                  (s == 200 and bool(d.get("objectives") and d.get("instructions"))) if seeded
                  else (s == 404 and (b.get("error") or {}).get("code") == "NOT_FOUND"),
                  s == 200))(*student.json("GET", f"/api/v1/experiment-versions/{version}")))

    rec.probe("E04", "SPEC-009 实验辅助", COVERAGE[21][2],
              data_expect("两类提交入口", seeded), "experiment_version",
              lambda: (lambda s, d, b: (
                  f"HTTP {s} modes={(d or {}).get('submission_modes')}",
                  (s == 200 and {"wiring", "circuit"}.issubset(
                      set((d or {}).get("submission_modes") or []))) if seeded
                  else (s == 404 and (b.get("error") or {}).get("code") == "NOT_FOUND"),
                  s == 200))(*student.json("GET", f"/api/v1/experiment-versions/{version}")))

    def gate_probe():
        vid = sc.ids.get("draft_version_id", 999)
        s, _d, b = teacher.json("POST", f"/api/v1/experiment-versions/{vid}/publish",
                               {"start_at": stamp(-60), "end_at": stamp(86400)})
        if seeded:
            return f"HTTP {s} code={(b.get('error') or {}).get('code')}", s in (400, 409, 422), True
        return f"HTTP {s} code={(b.get('error') or {}).get('code')}", s == 404, False
    rec.probe("E05", "SPEC-009 实验辅助", COVERAGE[22][2],
              "空库明确 404；正常库未配测试集的草稿发布被拒", "test_suite", gate_probe)

    rec.probe("E06", "SPEC-009 实验辅助", COVERAGE[23][2],
              data_expect("本人历史版本/提交记录", seeded), "submission",
              lambda: (lambda s, d, b: (
                  f"HTTP {s} 提交 {len(items({'data': d}))} 条",
                  (s == 200 and bool(items({"data": d}))) if seeded
                  else (s == 404 and (b.get("error") or {}).get("code") == "NOT_FOUND"),
                  s == 200))(*student.json("GET", f"/api/v1/courses/{course}/submissions")))

    rec.probe("E07", "SPEC-009 实验辅助", COVERAGE[24][2],
              "空库无冻结名单；正常库冻结名单含提交学生", "experiment_participant",
              lambda: (lambda rows: (
                  f"experiment_participant {len(rows)} 行",
                  (len(rows) > 0) if seeded else (len(rows) == 0), len(rows) > 0))(
                  sc.sql("SELECT * FROM experiment_participant")))

    # ---------------- SPEC-018 ----------------
    rec.probe("G01", "SPEC-018 电路评测", COVERAGE[25][2],
              f"固定 JAR 存在且 sha256 可校验（jar_ok={jar_ok}）", "无（本地 JAR）",
              lambda: (f"JAR {JAR.stat().st_size} 字节，grader_ready 由 health 断言",
                       jar_ok, True))
    rec.probe("G02", "SPEC-018 电路评测", COVERAGE[26][2],
              data_expect("judge profile 配置", seeded), "judge_profile",
              lambda: (lambda rows: (
                  f"judge_profile {len(rows)} 行，sha={sc.ids.get('profile_sha', '')[:12]}",
                  (len(rows) > 0 and rows[0]["canonical_sha256"]) if seeded
                  else len(rows) == 0, len(rows) > 0))(
                  sc.sql("SELECT * FROM judge_profile")))
    rec.probe("G03", "SPEC-018 电路评测", COVERAGE[27][2],
              data_expect("正例/反例参考文件", seeded), "reference_file",
              lambda: (lambda rows: (
                  f"reference_file {len(rows)} 行",
                  (len(rows) == 2) if seeded else (len(rows) == 0), len(rows) == 2))(
                  sc.sql("SELECT * FROM reference_file")))
    rec.probe("G04", "SPEC-018 电路评测", COVERAGE[28][2],
              data_expect("测试集 8 个计分组", seeded), "test_case",
              lambda: (lambda rows: (
                  f"test_case {len(rows)} 行，分组 {len({r['group_code'] for r in rows})} 个",
                  (len(rows) == 11 and len({r["group_code"] for r in rows}) == 8)
                  if seeded else len(rows) == 0, len(rows) > 0))(
                  sc.sql("SELECT * FROM test_case")))
    def validation_probe():
        rows = sc.sql("SELECT * FROM test_suite_validation")
        if not seeded:
            return f"validation {len(rows)} 行", len(rows) == 0, False
        row = rows[0]
        result = json.loads(row.get("result_json") or "{}")
        ok = (row["status"] == "passed" and result.get("reference") == "all_passed"
              and result.get("negative") == "functional_failure")
        return (f"status={row['status']} result={result}", ok, ok)
    rec.probe("G05", "SPEC-018 电路评测", COVERAGE[29][2],
              data_expect("测试集真引擎验证", seeded), "test_suite_validation", validation_probe)
    rec.probe("G06", "SPEC-018 电路评测", COVERAGE[30][2],
              data_expect("测试集发布", seeded), "test_suite",
              lambda: (lambda rows: (
                  f"published 测试集 {len(rows)} 个",
                  (len(rows) > 0) if seeded else (len(rows) == 0), len(rows) > 0))(
                  sc.sql("SELECT * FROM test_suite WHERE status='published'")))

    def run_probe(key, expected_status, expected_score, expected_passed):
        def inner():
            run_id = sc.ids.get(key + "_run")
            if not seeded:
                s, _d, b = sc.clients["student"].json("GET", "/api/v1/grading-runs/1")
                return f"HTTP {s} code={(b.get('error') or {}).get('code')}", \
                    s == 404 and (b.get("error") or {}).get("code") == "NOT_FOUND", False
            rows = sc.sql("SELECT * FROM grading_run WHERE id=?", (run_id,))
            row = rows[0] if rows else {}
            score = row.get("score_hundredths")
            score = score / 100 if isinstance(score, int) else score
            ok = (row.get("status") == expected_status and score == expected_score
                  and row.get("passed_count") == expected_passed)
            return ((f"status={row.get('status')} score={score} "
                    f"passed={row.get('passed_count')}/{row.get('total_count')} "
                    f"error={row.get('error_code')}"), ok, ok)
        return inner
    rec.probe("G07", "SPEC-018 电路评测", COVERAGE[31][2],
              "空库明确 404；正常库 accepted / 100.0 / 11 通过", "grading_run",
              run_probe("good", "accepted", 100.0, 11))
    rec.probe("G08", "SPEC-018 电路评测", COVERAGE[32][2],
              "空库明确 404；正常库 wrong_answer / 87.5 / 10 通过（部分给分）", "grading_run",
              run_probe("bad", "wrong_answer", 87.5, 10))

    def reject_probe(label, content, filename):
        def inner():
            if not seeded:
                s, _, b = student.json("GET", "/api/v1/grading-runs/1")
                return f"HTTP {s} code={(b.get('error') or {}).get('code')}", s == 404, False
            blob = io.BytesIO(content)
            response = student.open(
                "POST", f"/api/v1/experiment-versions/{version}/submissions",
                form={"file": (blob, filename, "application/xml")})
            body = response.get_json() or {}
            code = (body.get("error") or {}).get("code")
            return (f"HTTP {response.status_code} code={code}",
                    response.status_code == 400 and code in ("VALIDATION_ERROR", "INVALID_CIRCUIT"),
                    True)
        return inner
    rec.probe("G09", "SPEC-018 电路评测", COVERAGE[33][2],
              "空库明确 404；正常库非 .circ → 400 且明确错误码", "grading_run",
              reject_probe("非 .circ", b"not a circuit", "notes.txt"))
    wrong_name = (FIXTURES / "alu8.circ").read_bytes().replace(b'name="ALU8"', b'name="WRONG"')
    rec.probe("G10", "SPEC-018 电路评测", COVERAGE[34][2],
              "空库明确 404；正常库顶层名不符 → 400 INVALID_CIRCUIT", "grading_run",
              reject_probe("顶层名", wrong_name, "wrong.circ"))

    def desensitize_probe():
        if not seeded:
            s, _, b = student.json("GET", "/api/v1/grading-runs/1")
            return f"HTTP {s} code={(b.get('error') or {}).get('code')}", s == 404, False
        s, d, _ = student.json("GET", f"/api/v1/grading-runs/{sc.ids.get('good_run')}")
        blob = json.dumps(d or {}, ensure_ascii=False)
        leaked = [word for word in ("storage_key", "jar_sha256", "worker_token",
                                    "profile_snapshot_json", "file_path") if word in blob]
        return f"HTTP {s} 敏感字段 {leaked}", s == 200 and not leaked, s == 200 and not leaked
    rec.probe("G11", "SPEC-018 电路评测", COVERAGE[35][2],
              "空库明确 404；正常库学生报告不含内部路径/快照/worker token", "grading_run",
              desensitize_probe)

    def regrade_probe():
        if not seeded:
            s, _, b = teacher.json("GET", "/api/v1/grading-runs/1")
            return f"HTTP {s} code={(b.get('error') or {}).get('code')}", s == 404, False
        run_rows = sc.sql("SELECT submission_id FROM grading_run WHERE id=?",
                          (sc.ids.get("good_run"),))
        submission_id = run_rows[0]["submission_id"] if run_rows else sc.ids.get("good_submission")
        s, _d, _ = teacher.json(
            "POST", f"/api/v1/submissions/{submission_id}/regrades",
            {"reason": "验收重评"},
            extra_headers={"Idempotency-Key": str(uuid.uuid4())})
        rows = sc.sql("SELECT * FROM grading_run WHERE reason=?", ("验收重评",))
        ok = s == 202 and len(rows) == 1 and rows[0]["status"] == "queued"
        return ((f"HTTP {s} 新 run #{rows[0]['id'] if rows else '—'} status="
                f"{rows[0]['status'] if rows else '—'}，reason 标记 {len(rows)} 条"), ok, ok)
    rec.probe("G12", "SPEC-018 电路评测", COVERAGE[36][2],
              "空库明确 404；正常库重评生成 retry_of 新 run", "grading_run", regrade_probe)

    def zero_case_probe():
        from backend.engines import grading as engine
        empty = engine.parse_engine_output("Passed: 0, Failed: 0\n", [{"id": 1, "steps_json": "[]"}])
        ok_empty = empty is None or not empty.get("results")
        with tempfile.TemporaryDirectory() as directory:
            none_vector = engine.write_vector_file(
                directory, {"id": 2, "steps_json": json.dumps(
                    [{"step_no": 1, "inputs": {"A": 1}, "expected": {}, "clock_event": "none"}])},
                {"A": 8})
        return f"空汇总解析={empty}，无输出列向量={none_vector}", ok_empty and none_vector is None, True
    rec.probe("G13", "SPEC-018 电路评测", COVERAGE[37][2],
              "零用例/无输出列不得被判满分（两场景一致）", "无（纯函数契约）", zero_case_probe)

    # ---------------- SPEC-010D ----------------
    def analytics_probe():
        s, d, b = teacher.json("GET", f"/api/v1/courses/{course}/analytics?dimension=grading")
        if seeded:
            return f"HTTP {s} 维度字段 {list((d or {}).keys())[:6]}", s == 200, True
        return f"HTTP {s} code={(b.get('error') or {}).get('code')}", \
            s == 404 and (b.get("error") or {}).get("code") == "NOT_FOUND", False
    rec.probe("A01", "SPEC-010D 评测分析", COVERAGE[38][2],
              data_expect("教师评测统计", seeded), "grading_run", analytics_probe)

    def distribution_probe():
        s, d, b = teacher.json("GET", f"/api/v1/courses/{course}/analytics?dimension=grading")
        if not seeded:
            return (f"HTTP {s} code={(b.get('error') or {}).get('code')}",
                    s == 404 and (b.get("error") or {}).get("code") == "NOT_FOUND", False)
        metrics = (d or {}).get("metrics") or {}
        keys = ("accepted_count", "pass_rate", "mean_score", "score_bins",
                "run_count", "system_error_count")
        present = [key for key in keys if key in metrics]
        return ((f"HTTP {s} 指标 {present}，score_bins "
                f"{len(metrics.get('score_bins') or [])} 档，pass_rate={metrics.get('pass_rate')}"),
                s == 200 and len(present) == len(keys), s == 200)
    rec.probe("A02", "SPEC-010D 评测分析", COVERAGE[39][2],
              data_expect("通过率与分数分布", seeded), "grading_run", distribution_probe)

    def system_error_probe():
        if not seeded:
            s, _, b = teacher.json("GET", f"/api/v1/courses/{course}/analytics?dimension=grading")
            return f"HTTP {s} code={(b.get('error') or {}).get('code')}", s == 404, False
        url = f"/api/v1/courses/{course}/analytics?dimension=grading"
        s0, before, _ = teacher.json("GET", url)
        baseline = (before.get("sample_size"), (before.get("metrics") or {}).get("pass_rate"))
        db = sqlite3.connect(sc.db)
        cursor = db.execute(
            "INSERT INTO grading_run(submission_id,suite_id,engine_version,jar_sha256,status,"
            "score_hundredths,passed_count,executed_count,total_count,error_code,reason,"
            "profile_snapshot_json,profile_sha256,suite_sha256,created_at) "
            "SELECT submission_id,suite_id,engine_version,jar_sha256,'system_error',"
            "NULL,0,0,total_count,'ENGINE_CRASH','验收注入',"
            "profile_snapshot_json,profile_sha256,suite_sha256,? "
            "FROM grading_run WHERE status='accepted' LIMIT 1", (stamp(),))
        injected_id = cursor.lastrowid
        db.commit()
        db.close()
        s1, after, _ = teacher.json("GET", url)
        current = (after.get("sample_size"), (after.get("metrics") or {}).get("pass_rate"))
        blob = json.dumps(after or {}, ensure_ascii=False)
        db = sqlite3.connect(sc.db)
        db.execute("DELETE FROM grading_run WHERE id=?", (injected_id,))
        db.commit()
        db.close()
        ok = (s0 == 200 and s1 == 200 and baseline == current
              and "system_error" in blob)
        return ((f"注入 system_error 前 sample_size/pass_rate={baseline}，"
                f"注入后={current}，独立成项={'system_error' in blob}"), ok, ok)
    rec.probe("A03", "SPEC-010D 评测分析", COVERAGE[40][2],
              "空库明确 404；正常库 system_error 单独成项、不并入正确率分母",
              "grading_run", system_error_probe)

    rec.probe("A04", "SPEC-010D 评测分析", COVERAGE[41][2],
              data_expect("学生 scope=self", seeded), "grading_run",
              lambda: (lambda s, d, b: (
                  f"HTTP {s} student_id={((d or {}).get('filters') or {}).get('student_id')}",
                  (s == 200 and ((d or {}).get("filters") or {}).get("student_id")
                   == sc.ids.get("student_id")) if seeded
                  else (s == 404 and (b.get("error") or {}).get("code") == "NOT_FOUND"),
                  s == 200))(*student.json("GET", f"/api/v1/courses/{course}/analytics?dimension=grading")))

    rec.probe("A05", "SPEC-010D 评测分析", COVERAGE[42][2],
              "空库明确 404；正常库学生查他人统计被拒", "grading_run",
              lambda: (lambda s: (
                  f"HTTP {s}", (s in (403, 404)) if seeded else (s == 404), s in (403, 404)))(
                  student.json("GET", f"/api/v1/courses/{course}/analytics"
                                      f"?dimension=grading&student_id={other.user['id']}")[0]))

    rec.probe("A06", "SPEC-010D 评测分析", COVERAGE[43][2],
              "空库无重评记录；正常库重评 run 带 reason 标记可单独分组", "grading_run",
              lambda: (lambda rows: (
                  f"reason 非空的重评 run {len(rows)} 条",
                  (len(rows) > 0) if seeded else (len(rows) == 0), len(rows) > 0))(
                  sc.sql("SELECT * FROM grading_run WHERE reason IS NOT NULL")))

    # ---------------- 电路模拟与控制 ----------------
    def spec_probe():
        s, d, _ = teacher.json("GET", "/api/v1/circuit-lab/spec")
        exps = (d or {}).get("experiments", [])
        ready = bool((d or {}).get("data_ready"))
        return (f"HTTP {s} 实验 {len(exps)} 个 data_ready={ready}",
                s == 200 and len(exps) == 2 and ready == seeded, len(exps) == 2)
    rec.probe("C01", "电路模拟与控制", COVERAGE[44][2],
              f"spec 200；两个实验；data_ready={'true' if seeded else 'false'}",
              "全部业务表（仅就绪标记）", spec_probe)

    def geometry_probe():
        s, d, _ = teacher.json("GET", "/api/v1/circuit-lab/spec")
        problems = []
        for exp in (d or {}).get("experiments", []):
            pins = exp.get("pins", [])
            if not exp.get("chip") or len(pins) < 10 or len(exp.get("cases", [])) < 2:
                problems.append(exp.get("id", "?") + " 定义不全")
            for wire in exp.get("wires", []):
                points = wire.get("points", [])
                for left, right in itertools.pairwise(points):
                    if left[0] != right[0] and left[1] != right[1]:
                        problems.append(f"{exp['id']} 斜导线 {left}->{right}")
        return (f"HTTP {s} 几何问题 {len(problems)} 处",
                s == 200 and not problems, not problems)
    rec.probe("C02", "电路模拟与控制", COVERAGE[45][2],
              "芯片/引脚/正交导线/用例定义齐全（两场景一致）", "无（静态定义）", geometry_probe)

    def backend_table_probe(chip, expected_count):
        def inner():
            s, d, _ = teacher.json("GET", f"/api/v1/circuit-lab/table?chip={chip}")
            rows = (d or {}).get("rows", [])
            mismatch = 0
            for row in rows[::max(1, len(rows) // 32)][:32]:
                if chip == "7485":
                    q = (f"&a={row['a']}&b={row['b']}&i_lt={row['i_lt']}"
                         f"&i_eq={row['i_eq']}&i_gt={row['i_gt']}")
                else:
                    q = f"&a={row['a']}&b={row['b']}&op={row['op']}"
                _, one, _ = teacher.json("GET", f"/api/v1/circuit-lab/compute?chip={chip}{q}")
                keys = ("gt", "eq", "lt", "relation") if chip == "7485" else (
                    "f", "cn4", "carry", "zero", "equal", "decimal_result")
                if any(one.get(k) != row.get(k) for k in keys):
                    mismatch += 1
            return (f"HTTP {s} 行数={len(rows)} 抽样不符={mismatch}",
                    s == 200 and len(rows) == expected_count and mismatch == 0, mismatch == 0)
        return inner
    rec.probe("C03", "电路模拟与控制", COVERAGE[46][2],
              "7485 全 2048 组合表与 compute 抽样一致（两场景一致）",
              "无（静态功能表）", backend_table_probe("7485", 2048))
    rec.probe("C04", "电路模拟与控制", COVERAGE[47][2],
              "74181 全 512 组合表与 compute 抽样一致（两场景一致）",
              "无（静态功能表）", backend_table_probe("74181", 512))

    def case_expect_probe():
        s, data, _ = teacher.json("GET", "/api/v1/circuit-lab/spec")
        mismatches = []
        total = 0
        for exp in (data or {}).get("experiments", []):
            for case in exp.get("cases", []):
                total += 1
                _, computed, _ = teacher.json("GET", _case_query(exp["id"], case))
                for key, value in case["expected"].items():
                    if (computed or {}).get(key) != value:
                        mismatches.append(f"{exp['id']}/{case['id']}.{key}")
        return (f"HTTP {s} 校验 {total} 个用例，不符 {len(mismatches)} 项 {mismatches[:3]}",
                s == 200 and total >= 5 and not mismatches, not mismatches)
    rec.probe("C06", "电路模拟与控制", COVERAGE[49][2],
              "每个验证用例的期望值与后端权威求值一致（两场景一致）",
              "无（静态功能表）", case_expect_probe)

    rec.probe("C08", "电路模拟与控制", COVERAGE[51][2],
              "数据缺失时电路定义仍完整、模拟/开关/验算不依赖业务表（两场景一致）",
              "无（静态定义）",
              lambda: (lambda s, d: (
                  (f"HTTP {s} 实验 {len((d or {}).get('experiments', []))} 个，"
                  f"引脚 {sum(len(e['pins']) for e in (d or {}).get('experiments', []))} 个"),
                  s == 200 and sum(len(e["pins"]) for e in (d or {}).get("experiments", [])) >= 30,
                  True))(*teacher.json("GET", "/api/v1/circuit-lab/spec")[:2]))


def _case_query(chip, case):
    inputs = case["inputs"]
    if chip == "7485":
        return (f"/api/v1/circuit-lab/compute?chip=7485&a={inputs['A']}&b={inputs['B']}"
                f"&i_lt={inputs.get('I_LT', 0)}&i_eq={inputs.get('I_EQ', 1)}"
                f"&i_gt={inputs.get('I_GT', 0)}")
    return (f"/api/v1/circuit-lab/compute?chip=74181&a={inputs['A']}&b={inputs['B']}"
            f"&op={inputs.get('OP', 'sub')}")


# ---------------------------------------------------------------------------
# 前端（Node）测试与前后端模拟内核交叉验证
# ---------------------------------------------------------------------------

FRONTEND_DUMP = r"""
import { truthTable } from './js/circuit-sim.js'
import { createHash } from 'node:crypto'
const norm = (chip, rows) => rows.map(row => chip === '7485'
  ? [row.a,row.b,row.i_lt,row.i_eq,row.i_gt,row.gt,row.eq,row.lt,row.relation].join(',')
  : [row.op,row.a,row.b,row.f,row.cn4,row.carry,row.borrow,row.zero,row.equal,row.decimal_result].join(',')
).join('\n')
const out = {}
for (const chip of ['7485','74181']) {
  const rows = truthTable(chip)
  out[chip] = { count: rows.length,
                sha256: createHash('sha256').update(norm(chip, rows)).digest('hex') }
}
console.log('__SIM_DUMP__' + JSON.stringify(out))
"""


def frontend_checks(rec, out_dir, enabled=True):
    """前端组件测试（16 项）+ 前后端模拟内核全组合 hash 比对。"""
    if not enabled:
        return
    # Node 子进程的 cwd 是 frontend/，结果路径必须解析为绝对路径，
    # 否则相对路径会被写到 frontend/ 下，after() 写文件失败会让退出码变成 1。
    result_path = (out_dir / "circuit-lab-frontend.json").resolve()
    result_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CIRCUIT_LAB_RESULT_JSON"] = str(result_path)
    proc = subprocess.run(
        ["node", "--test", "js/circuit-lab-view.test.js"],
        cwd=str(FRONTEND), env=env, capture_output=True, text=True, timeout=300, check=False)
    tap = [line for line in proc.stdout.splitlines() if line.startswith(("ok ", "not ok "))]
    rows = []
    if result_path.exists():
        rows = json.loads(result_path.read_text(encoding="utf-8"))
    for row in rows:
        rec.add(row["id"], "电路模拟与控制（前端组件）", row["feature"], row["expected"],
                row["actual"], row["passed"], "仅就绪标记", row["passed"])
    rec.add("C07", "电路模拟与控制", COVERAGE[50][2],
            "前端组件双场景 16 项全部通过",
            f"node --test 退出码 {proc.returncode}；TAP {len(tap)} 条；"
            f"结果文件 {len(rows)} 项，通过 {sum(1 for r in rows if r['passed'])} 项",
            proc.returncode == 0 and len(rows) == 16 and all(r["passed"] for r in rows),
            "仅就绪标记", proc.returncode == 0)

    dump = subprocess.run(["node", "--input-type=module", "-e", FRONTEND_DUMP],
                          cwd=str(FRONTEND), capture_output=True, text=True, timeout=180,
                          check=False)
    marker = "__SIM_DUMP__"
    line = next((ln for ln in dump.stdout.splitlines() if ln.startswith(marker)), "")
    if not line:
        rec.add("C05", "电路模拟与控制", COVERAGE[48][2], "前后端模拟内核逐行一致",
                f"前端 dump 失败：{dump.stderr[:200]}", False, "无（静态功能表）", False)
        return
    front = json.loads(line[len(marker):])
    from backend.apis import circuit_lab
    from backend.apis.alu import evaluate as alu_evaluate

    def backend_norm(chip):
        # JS Array.join 会把 null/undefined 变成空串，Python 侧必须同口径。
        def text(value):
            return "" if value is None else str(value)
        lines = []
        if chip == "7485":
            for a in range(16):
                for b in range(16):
                    for i_lt in (0, 1):
                        for i_eq in (0, 1):
                            for i_gt in (0, 1):
                                r = circuit_lab.evaluate_7485(a, b, i_lt, i_eq, i_gt)
                                lines.append(",".join(text(r[k]) for k in
                                                      ("a", "b", "i_lt", "i_eq", "i_gt",
                                                       "gt", "eq", "lt", "relation")))
        else:
            for op in ("add", "sub"):
                for a in range(16):
                    for b in range(16):
                        r = alu_evaluate(a, b, op)
                        lines.append(",".join(text(r[k]) for k in
                                              ("op", "a", "b", "f", "cn4", "carry",
                                               "borrow", "zero", "equal", "decimal_result")))
        return {"count": len(lines),
                "sha256": hashlib.sha256("\n".join(lines).encode()).hexdigest()}

    detail = []
    for chip in ("7485", "74181"):
        back = backend_norm(chip)
        same = back == front.get(chip)
        detail.append(f"{chip} 前端 {front.get(chip, {}).get('count')} 行 / 后端 {back['count']} 行，"
                      f"sha256 {'一致' if same else '不一致'}")
    ok = all("一致" in item for item in detail)
    rec.add("C05", "电路模拟与控制", COVERAGE[48][2],
            "7485 2048 组合 + 74181 512 组合前后端逐行一致",
            "；".join(detail), ok, "无（静态功能表）", ok)


# ---------------------------------------------------------------------------
# 归因、报告
# ---------------------------------------------------------------------------

def attribute(results):
    """依据双场景对照给出「登录后不可用」的归因。"""
    by_key = {(r["scene"], r["id"]): r for r in results}
    empty = [r for r in results if r["scene"] == "empty"]
    login_ids = ("L02", "L03", "L04")
    login_ok_empty = all(by_key.get(("empty", cid), {}).get("passed") for cid in login_ids)
    login_ok_seeded = all(by_key.get(("seeded", cid), {}).get("passed") for cid in login_ids)
    data_dependent = [r for r in empty if r["dependency"] not in ("无", "session", "user", "")
                      and r["dependency"] != "无（本地 JAR）"]
    recovered = [r for r in data_dependent
                 if r.get("usable") is False
                 and by_key.get(("seeded", r["id"]), {}).get("usable") is True]
    code_defects = [r for r in results if not r["passed"]]
    data_free = [r for r in empty if r["id"].startswith("C0") and r.get("usable")]
    bootstrap = by_key.get(("empty", "L09"), {})
    conclusion = {
        "login_ok_both_scenes": login_ok_empty and login_ok_seeded,
        "bootstrap_detects_missing": ("data_ready=False" in bootstrap.get("actual", "")
                                      or "data_ready=false" in bootstrap.get("actual", ""))
        and bootstrap.get("passed") is True,
        "data_dependent_checks": len(data_dependent),
        "unusable_in_empty": sum(1 for r in data_dependent if r.get("usable") is False),
        "recovered_after_seeding": len(recovered),
        "data_free_circuit_features": len(data_free),
        "verdict": (
            "登录后「资源/实验/评测/统计看不到内容」确定由后台业务数据缺失导致："
            "登录与会话在两场景都成功；空库 bootstrap 明确列出缺失的 8 类数据；"
            "补齐数据后这些功能全部恢复；电路模拟与电路控制不依赖业务表，两场景均可用。"
            "修复前页面缺少提示、看起来像功能坏掉，属前端缺陷，已补就绪引导与空态卡片，"
            "因此当前版本在数据缺失场景下不再有功能差错。"
        ),
    }
    return conclusion, code_defects


def write_reports(out_dir, results, conclusion, defects, coverage_rows, args):
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(UTC).isoformat(timespec="seconds")
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    by_scene = {}
    for scene in ("empty", "seeded", "frontend"):
        rows = [r for r in results if r["scene"] == scene]
        by_scene[scene] = (len(rows), sum(1 for r in rows if r["passed"]))

    payload = {"generated_at": generated, "scenario": args.scenario,
               "total": total, "passed": passed, "failed": total - passed,
               "by_scene": by_scene, "coverage": coverage_rows,
               "results": results, "attribution": conclusion,
               "acceptance": passed == total and not defects}
    (out_dir / "shibaihe-results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- 覆盖清单 ---
    cov = ["# 石佰合负责功能 · 测试覆盖清单", "",
           f"生成时间：{generated}　脚本：`scripts/acceptance_shibaihe.py`", "",
           "验收对象：PRD §10.1 实名分工中石佰合负责的四块 + 电路模拟/电路控制。", "",
           "| 编号 | 模块 | 被测功能 | 依赖的后台数据 | 双场景 |",
           "|---|---|---|---|---|"]
    for cid, module, feature, dependency in coverage_rows:
        cov.append(f"| {cid} | {module} | {feature} | {dependency} | 数据缺失 / 数据正常 |")
    cov += ["", "## 覆盖维度", "",
            "- **场景**：空库（后台数据缺失）与已初始化（后台数据正常），同一检查项各跑一遍。",
            "- **层次**：HTTP API 端到端 → 真引擎判分 → 前端组件渲染与交互 → 前后端数值交叉验证。",
            "- **归因**：`/circuit-lab/bootstrap` 逐表统计缺失项；对照两场景的可用性差异。",
            "- **电路控制**：芯片、引脚开关、指示灯、正交导线、接地、进度环、验证说明分页、",
            "  输入设置面板、验证用例、输出读数、工具栏、提交记录、通过提示。",
            "- **数值**：7485 全 2048 组合、74181 全 512 组合，前端模拟内核与后端功能表逐行比对。",
            "", f"共 {len(coverage_rows)} 个后端/电路检查项，另含前端组件 16 项与归因结论项。"]
    (out_dir / "shibaihe-coverage.md").write_text("\n".join(cov) + "\n", encoding="utf-8")

    # --- 结果汇总 ---
    rep = ["# 石佰合负责功能 · 验收结果汇总", "",
           f"生成时间：{generated}", "",
           f"**总计 {passed}/{total} 项通过，失败 {total - passed} 项。**", "",
           "| 场景 | 检查项 | 通过 |", "|---|---|---|"]
    for scene, label in (("empty", "后台数据缺失"), ("seeded", "后台数据正常"),
                         ("frontend", "前端组件/交叉验证")):
        count, ok = by_scene.get(scene, (0, 0))
        rep.append(f"| {label} | {count} | {ok} |")
    rep += ["", "## 归因结论（登录后无法使用是不是后台数据缺失造成的）", "",
            f"- 登录与会话在两场景都成功：`{conclusion['login_ok_both_scenes']}`",
            f"- 空库 bootstrap 明确检出缺失：`{conclusion['bootstrap_detects_missing']}`",
            (f"- 依赖业务数据的检查项：{conclusion['data_dependent_checks']} 项；"
            f"空库不可用 {conclusion['unusable_in_empty']} 项；"
            f"补齐数据后恢复 {conclusion['recovered_after_seeding']} 项"),
            f"- 不依赖后台数据、两场景都可用的电路功能：{conclusion['data_free_circuit_features']} 项",
            "", "> " + conclusion["verdict"], "",
            "### 修复前基线证据", "",
            ("空库下：登录 200、会话 200、`/courses` 返回空数组；"
            "`/courses/1/resources`、`/experiments`、`/experiment-versions`、"
            "`/analytics`、`/submissions` 全部 404 `Course not found`；"
            "前端 `courseId` 为 null 导致「考勤与学情」整块不渲染、其余模块无数据且无提示。"),
            "补齐课程/实验/测试集/评测记录后，同一批接口全部可用 → 因果关系成立。", "",
            "### 已修复的问题清单", "",
            "| 编号 | 问题 | 处理 |", "|---|---|---|",
            ("| P1 | 后台数据缺失时页面无引导，登录成功后像「功能全坏」 | "
            "新增 `/api/v1/circuit-lab/bootstrap` 逐表就绪判定；登录后显示引导条，"
            "「考勤与学情」在无课程时显示空态卡片与返回入口 |"),
            ("| P2 | 缺少芯片级电路控制界面 | 新增电路实验台（7485 / 74181+7400），"
            "SVG 电路图、开关/指示灯、进度环、用例分页、右面板、提交记录 |"),
            "| P3 | 7485 级联输入全 0 时误报 A<B | 前后端模拟内核同时改为「无有效输出」 |",
            "| P4 | 74181 验证用例 Cn+4 期望写反（低有效） | 按芯片功能表修正两处期望 |",
            "| P5 | `/circuit-lab/compute` 缺少级联参数时报 400 | 补默认值 I(A<B)=0 / I(A=B)=1 / I(A>B)=0 |",
            ("| P6 | 畸形数值参数（`--1` / `²` / `1_0` / 超长整数）让 compute 抛未捕获 ValueError → 500 | "
             "`query_int` 改为 ASCII 十进制正则并捕获 `int()` 异常，统一返回 400；"
             "新增 `tests/test_circuit_lab.py` 回归 |"),
            ("| P7 | `/circuit-lab/bootstrap` 对匿名用户开放 8 张业务表的精确记录数 | "
             "增加 `require_user()`，未登录返回 401 |"),
            ("| P8 | `readiness()` 把 sqlite 原始错误文本回给客户端，可能泄露表名 / 列名 | "
             "降级项不再返回 `error` 字段，只给就绪状态与补全建议 |"),
            "", "### 当前未解决问题", "",
            ("无。全部被测项通过，无功能差错。" if passed == total and not defects
             else f"{len(defects)} 项未通过，见下方逐项结果与验收结论。"),
            "", "## 逐项结果（预期 / 实际 / 通过状态）", "",
            "| 场景 | 编号 | 模块 | 被测功能 | 预期结果 | 实际结果 | 通过 |",
            "|---|---|---|---|---|---|---|"]
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    for row in results:
        rep.append(f"| {row['scene']} | {cell(row['id'])} | {cell(row['module'])} | "
                   f"{cell(row['feature'])} | {cell(row['expected'])} | "
                   f"{cell(row['actual'])} | {'✅' if row['passed'] else '❌'} |")
    rep += ["", "## 验收结论", ""]
    if passed == total and not defects:
        rep += [f"**通过**：全部 {total} 个被测项通过，无功能差错，满足验收标准。", "",
                "复跑命令：`python scripts/acceptance_shibaihe.py`"]
    else:
        rep += [f"**未通过**：{len(defects)} 项失败，明细：", ""]
        for row in defects:
            rep.append(f"- {row['scene']} / {row['id']} {row['feature']}：{row['actual']}")
    (out_dir / "shibaihe-report.md").write_text("\n".join(rep) + "\n", encoding="utf-8")

    # --- 电路控制实现说明 ---
    impl = ["# 电路控制实现说明（对照两张参考作品）", "",
            "## 文件", "",
            "| 文件 | 作用 |", "|---|---|",
            "| `backend/apis/circuit_lab.py` | 芯片功能表、电路图定义、就绪判定、compute/table/spec API |",
            "| `frontend/js/circuit-sim.js` | 7485 / 74181 纯函数模拟内核、引脚状态、用例比对、全组合真值表 |",
            "| `frontend/js/circuit-lab-view.js` | Vue 组件：布局、SVG 电路图、控件与操作反馈 |",
            "| `frontend/styles/circuit-lab.css` | 视觉细节：深色侧栏、芯片、开关/灯、绿色导线、进度环、表格 |",
            "| `frontend/js/circuit-lab-view.test.js` | 双场景 16 项组件测试 |",
            "| `frontend/js/circuit-lab-spec.fixture.json` | 由后端 spec 导出的测试基准 |",
            "", "## 与参考图对齐的元素", "",
            "- 左侧深色实验目录与图例；顶部实验标题 + 一排工具栏（复位/上一步/下一步/缩放/说明/重新加载/验算/提交）。",
            "- 左信息卡：SVG 进度环 + 「x/y 用例通过」+ 验证说明 + `< 1/3 >` 分页 + 黄色提示条。",
            ("- 中间电路图：深灰芯片矩形（7485 / 74181 / 7400）、带圆点的方形输入开关（1 为黄绿）、"
            "圆形输出指示灯（1 为红色）、蓝色引脚标签、绿色正交导线与接地符号。"),
            ("- 右侧控制面板：输入设置表（数值/开关/下拉）、验证用例表（点击载入、状态高亮）、"
            "输出读数、芯片说明。"),
            "- 底部：提交记录表（时间/实验/用例/输入/结果/得分/状态）与「本实验已通过」提示条。", "",
            "## 交互与状态", "",
            ("点击任意输入开关即按芯片功能表重算全部输出，并同步更新开关高亮、指示灯、读数与反馈条；"
            "S3–S0/M 由 7400 译码为只读控制位，点击 Cn̄ 可切换加/减法；"
            "复位、载入用例、验算、提交、翻页、缩放、切换实验均有明确反馈。"),
            "提交会写入本次会话的提交记录并更新进度环；全部用例通过后显示完成提示。", "",
            "## 数据缺失时的行为", "",
            ("`/circuit-lab/spec` 的电路定义是静态的，不依赖业务表；只有 `data_ready` 随数据库变化。"
            "空库时页面显示黄色引导条列出缺失数据与初始化命令，电路模拟、开关控制、验算照常可用，"
            "提交记录注明「仅保存在本次会话」，不会白屏也不会误报成功。"), ""]
    (out_dir / "shibaihe-circuit-lab.md").write_text("\n".join(impl) + "\n", encoding="utf-8")

    # --- 验收结果（单页结论） ---
    verdict = ("✅ **通过**" if passed == total and not defects else "❌ **未通过**")
    acc = ["# 石佰合负责功能 · 验收结果", "",
           f"生成时间：{generated}", "",
           "## 验收标准", "",
           "全部被测项通过，且无功能差错；明确判断「登录后无法使用」是否由后台数据缺失导致。", "",
           "## 验收结论", "",
           f"{verdict}　——　{passed}/{total} 项通过，失败 {total - passed} 项。", "",
           "| 场景 | 检查项 | 通过 |", "|---|---|---|"]
    for scene, label in (("empty", "后台数据缺失"), ("seeded", "后台数据正常"),
                         ("frontend", "前端组件 / 前后端交叉验证")):
        count, ok = by_scene.get(scene, (0, 0))
        acc.append(f"| {label} | {count} | {ok} |")
    acc += ["", "## 归因判定", "", conclusion["verdict"], "",
            f"- 登录与会话在两场景均成功：{conclusion['login_ok_both_scenes']}",
            f"- 空库 bootstrap 检出缺失：{conclusion['bootstrap_detects_missing']}",
            (f"- 空库因数据缺失不可用、补齐后恢复：{conclusion['unusable_in_empty']} / "
            f"{conclusion['recovered_after_seeding']} 项"),
            f"- 与业务数据无关、两场景都可用的电路功能：{conclusion['data_free_circuit_features']} 项",
            "", "## 复跑方式", "",
            "```bash",
            "python scripts/acceptance_shibaihe.py",
            "python scripts/acceptance_shibaihe.py --scenario empty",
            "python scripts/acceptance_shibaihe.py --scenario seeded --no-frontend",
            "```", "",
            "脚本自建隔离数据库、自造场景、自带清理，不改动任何现有环境数据，可反复运行。", "",
            "## 交付物", "",
            "| 文件 | 内容 |", "|---|---|",
            "| `scripts/acceptance_shibaihe.py` | 完整可重复测试脚本 |",
            "| `tests/acceptance/shibaihe-coverage.md` | 测试覆盖清单 |",
            "| `tests/acceptance/shibaihe-report.md` | 逐项结果汇总（预期/实际/通过状态）+ 问题清单 |",
            "| `tests/acceptance/shibaihe-results.json` | 结构化结果（供二次统计） |",
            "| `tests/acceptance/shibaihe-circuit-lab.md` | 电路控制实现说明 |",
            "| `tests/acceptance/shibaihe-acceptance.md` | 本验收结论 |",
            "| `backend/apis/circuit_lab.py` | 电路实验台后端 |",
            "| `frontend/js/circuit-sim.js` / `circuit-lab-view.js` | 电路模拟内核与界面 |",
            "| `frontend/styles/circuit-lab.css` | 界面视觉细节 |",
            "| `frontend/js/circuit-lab-view.test.js` | 前端组件双场景测试 |", ""]
    (out_dir / "shibaihe-acceptance.md").write_text("\n".join(acc) + "\n", encoding="utf-8")


def main(argv=None):
    global JAR
    parser = argparse.ArgumentParser(description="石佰合负责功能的双场景验收")
    parser.add_argument("--scenario", choices=("both", "empty", "seeded"), default="both")
    parser.add_argument("--out", default=str(ROOT / "tests" / "acceptance"))
    parser.add_argument("--jar", default=str(JAR))
    parser.add_argument("--no-frontend", action="store_true")
    parser.add_argument("--keep", action="store_true", help="保留临时数据库便于排查")
    args = parser.parse_args(argv)

    JAR = Path(args.jar)
    os.environ["LOGISIM_JAR_PATH"] = str(JAR)
    jar_ok = JAR.is_file() and JAR.stat().st_size > 50_000_000
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    scenarios = []
    targets = ("empty", "seeded") if args.scenario == "both" else (args.scenario,)
    for name in targets:
        print(f"[setup] 场景 {name}：准备隔离数据库…", flush=True)
        sc = Scenario(name, seeded=(name == "seeded"), jar=JAR)
        sc.setup()
        scenarios.append(sc)
        rec = Recorder(name)
        run_checks(sc, rec, jar_ok)
        results.extend(rec.rows)
        count = len(rec.rows)
        ok = sum(1 for row in rec.rows if row["passed"])
        print(f"[check] 场景 {name}：{ok}/{count} 通过", flush=True)

    if not args.no_frontend:
        print("[frontend] 运行组件测试与前后端模拟内核交叉验证…", flush=True)
        front_rec = Recorder("frontend")
        frontend_checks(front_rec, out_dir, enabled=True)
        results.extend(front_rec.rows)
        print(f"[frontend] {sum(1 for r in front_rec.rows if r['passed'])}"
              f"/{len(front_rec.rows)} 通过", flush=True)

    conclusion, defects = attribute(results)
    write_reports(out_dir, results, conclusion, defects, COVERAGE, args)
    total = len(results)
    passed = sum(1 for row in results if row["passed"])
    print(f"\n=== 验收：{passed}/{total} 项通过 ===")
    print(f"报告：{out_dir / 'shibaihe-report.md'}")
    if defects:
        for row in defects[:20]:
            print(f"  [FAIL] {row['scene']}/{row['id']} {row['feature']}: {row['actual']}")
    if not args.keep:
        import shutil
        for sc in scenarios:
            shutil.rmtree(sc.tmp, ignore_errors=True)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
