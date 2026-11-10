"""SPEC-009 电路实验台：参数边界、登录权限与信息泄露回归。

对应本轮验收发现的三处问题：
* 畸形数值参数（``--1`` / ``²`` / ``1_0``）曾让 compute 抛未捕获 ValueError → 500；
* bootstrap 曾对匿名用户开放逐表记录数；
* readiness 曾把 sqlite 原始错误文本回给客户端。
"""

import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.shared.db import connect, migrate

ORIGIN = "http://127.0.0.1:5173"
PASSWORD = "circuit-lab-test-password"
AT = "2026-11-09T00:00:00Z"
BASE = "/api/v1/circuit-lab"


class CircuitLabApiTest(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.path = Path(self.temporary.name) / "circuit_lab.db"
        migrate(self.path)
        self.app = create_app({
            "TESTING": True,
            "DATABASE_PATH": str(self.path),
            "UPLOAD_ROOT": str(Path(self.temporary.name) / "uploads"),
            "SECRET_KEY": "circuit-lab-test-secret",
            "APP_ORIGIN": ORIGIN,
        })
        with closing(connect(self.path)) as db:
            db.execute(
                "INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                "VALUES(?,?,?,'student',1,?,?)",
                ("CLAB0001", "电路实验台", generate_password_hash(PASSWORD), AT, AT))
            db.commit()
        self.anonymous = self.app.test_client()
        self.logged_in = self.app.test_client()
        response = self.logged_in.post(
            "/api/v1/auth/login",
            json={"student_no": "CLAB0001", "password": PASSWORD},
            headers={"Origin": ORIGIN})
        self.assertEqual(response.status_code, 200, response.json)

    def tearDown(self):
        self.temporary.cleanup()

    # ---------- 输入边界：任何畸形参数都必须是 400，不能是 500 ----------

    def test_compute_rejects_malformed_operands_without_500(self):
        queries = (
            "chip=7485&a=--1&b=3",            # 旧写法 isdigit() 通过、int() 抛错
            "chip=7485&a=%C2%B2&b=3",         # 上标 ²：isdigit() True、int() 抛错
            "chip=7485&a=1_0&b=3",            # Python 字面量下划线
            "chip=7485&a=%EF%BC%91&b=3",      # 全角数字不应被静默接受
            "chip=7485&a=" + "9" * 4400 + "&b=3",  # 超过 CPython 整数位数上限
            "chip=7485&a=16&b=3",
            "chip=7485&a=-1&b=3",
            "chip=7485&a=9&b=3&i_lt=2",
            "chip=74181&a=9&b=4&op=mul",
            "chip=nope&a=9&b=3",
            "chip=7485&b=3",                  # 缺少必填参数 a
        )
        for query in queries:
            with self.subTest(query=query[:64]):
                response = self.anonymous.get(f"{BASE}/compute?{query}")
                self.assertEqual(response.status_code, 400, query[:64])
                self.assertEqual(response.json["error"]["code"], "VALIDATION_ERROR")

    def test_compute_still_accepts_plain_values_and_defaults(self):
        compare = self.anonymous.get(f"{BASE}/compute?chip=7485&a=9&b=3")
        self.assertEqual(compare.status_code, 200)
        self.assertEqual(compare.json["data"]["relation"], "A>B")
        self.assertEqual((compare.json["data"]["gt"], compare.json["data"]["eq"]), (1, 0))

        subtract = self.anonymous.get(f"{BASE}/compute?chip=74181&a=9&b=4&op=sub")
        self.assertEqual(subtract.status_code, 200)
        self.assertEqual((subtract.json["data"]["f"], subtract.json["data"]["cn4"]), (5, 0))

    # ---------- 与 SPEC-019 一致：纯计算的演示端点公开 ----------

    def test_spec_and_table_answer_without_login(self):
        spec = self.anonymous.get(f"{BASE}/spec")
        self.assertEqual(spec.status_code, 200)
        experiments = spec.json["data"]["experiments"]
        self.assertEqual([item["id"] for item in experiments], ["7485", "74181"])
        self.assertEqual([len(item["cases"]) for item in experiments], [3, 2])

        for chip, count in (("7485", 2048), ("74181", 512)):
            with self.subTest(chip=chip):
                table = self.anonymous.get(f"{BASE}/table?chip={chip}")
                self.assertEqual(table.status_code, 200)
                self.assertEqual(table.json["data"]["count"], count)
                self.assertEqual(len(table.json["data"]["rows"]), count)

    # ---------- 权限与信息泄露 ----------

    def test_bootstrap_requires_login(self):
        denied = self.anonymous.get(f"{BASE}/bootstrap")
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(denied.json["error"]["code"], "UNAUTHENTICATED")

        allowed = self.logged_in.get(f"{BASE}/bootstrap")
        self.assertEqual(allowed.status_code, 200)
        data = allowed.json["data"]
        self.assertEqual(data["total_items"], 8)
        self.assertFalse(data["data_ready"])  # 空库：8 类业务数据都缺失
        self.assertEqual(len(data["missing"]), 8)
        self.assertEqual(data["ready_items"], 0)

    def test_missing_table_does_not_leak_sqlite_details(self):
        with closing(connect(self.path)) as db:
            db.execute("DROP TABLE resource")
            db.commit()
        response = self.logged_in.get(f"{BASE}/bootstrap")
        self.assertEqual(response.status_code, 200)
        data = response.json["data"]
        self.assertTrue(all("error" not in item for item in data["items"]))
        self.assertNotIn("no such table", json.dumps(response.json, ensure_ascii=False).lower())
        broken = [item for item in data["items"] if item["key"] == "resource"]
        self.assertEqual(len(broken), 1)
        self.assertFalse(broken[0]["ready"])
        self.assertIsNone(broken[0]["count"])
