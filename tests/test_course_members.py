"""课程成员列表的回归测试。

历史 bug：member_json 对 sqlite3.Row 调用了 .get("class_name", None)。
sqlite3.Row 只支持 keys() 和下标取值，没有 .get()，于是 GET
/courses/<id>/members 恒抛 AttributeError → 500。前端课程页用
Promise.all 并行拉课程详情 / 成员 / 考勤任务，成员接口一挂就整批
reject，表现为"课程数据全不加载、考勤任务 0、座位图按钮不出现"，
看起来像功能没做。

这里同时覆盖 class_name 有值（导入过名单）与为空（老账号）两种情况，
防止以后有人为了"简化"再换回 .get()。
"""

from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import TestCase

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.shared.db import connect, migrate

ORIGIN = "http://127.0.0.1:5173"
PASSWORD = "Long-test-password-42"


class MemberListTest(TestCase):
    def setUp(self):
        with NamedTemporaryFile(dir=Path(__file__).parent, delete=False) as temporary:
            self.path = Path(temporary.name)
        migrate(self.path)
        self.at = datetime(2026, 11, 6, 8, tzinfo=UTC)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.path),
                               "SECRET_KEY": "test-secret-for-csrf", "TEST_NOW": self.at})
        self.admin = self.app.test_client()
        self.teacher = self.app.test_client()
        db = connect(self.path)
        try:
            rows = (("ADMIN0001", "Admin", "admin", None),
                    ("TEACH0001", "Teacher", "teacher", None),
                    ("24201710", "姜苏豪", "student", "计科2401"),
                    ("24201711", "无班组员", "student", None))
            for number, name, role, class_name in rows:
                db.execute("INSERT INTO user(student_no,name,password_hash,role,class_name,active,"
                           "created_at,updated_at) VALUES(?,?,?,?,?,1,?,?)",
                           (number, name, generate_password_hash(PASSWORD), role, class_name,
                            self.at.isoformat(), self.at.isoformat()))
        finally:
            db.close()
        self.auth(self.admin, "ADMIN0001")
        self.auth(self.teacher, "TEACH0001")

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def call(self, client, method, path, data=None):
        headers = {"Origin": ORIGIN, "X-CSRF-Token": getattr(client, "csrf", "")}
        return client.open(path, method=method, json=data, headers=headers)

    def auth(self, client, number):
        response = self.call(client, "POST", "/api/v1/auth/login",
                             {"student_no": number, "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.json)
        client.csrf = response.json["data"]["csrf_token"]

    def test_members_serialize_with_and_without_class_name(self):
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        created = self.call(self.admin, "POST", "/api/v1/courses",
                            {"title": "计算机组成原理", "teacher_id": teacher_id})
        self.assertEqual(created.status_code, 201, created.json)
        course_id = created.json["data"]["id"]

        for student_no in ("24201710", "24201711"):
            added = self.call(self.teacher, "POST", f"/api/v1/courses/{course_id}/members",
                              {"user_id": self.user_id(student_no), "member_role": "student"})
            self.assertEqual(added.status_code, 201, added.json)

        listed = self.teacher.get(f"/api/v1/courses/{course_id}/members")
        self.assertEqual(listed.status_code, 200, listed.get_data(as_text=True))
        # 建课时教师会自动成为成员，这里只看学生
        members = {item["student_no"]: item for item in listed.json["data"]
                   if item["member_role"] == "student"}
        self.assertEqual(set(members), {"24201710", "24201711"})
        # 有名单的带上班级，没有的必须是 None 而不是缺字段或报错
        self.assertEqual(members["24201710"]["class_name"], "计科2401")
        self.assertIsNone(members["24201711"]["class_name"])
        for item in members.values():
            self.assertIn("class_name", item)

    def test_members_filter_and_search_still_work(self):
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        created = self.call(self.admin, "POST", "/api/v1/courses",
                            {"title": "计算机组成原理", "teacher_id": teacher_id})
        course_id = created.json["data"]["id"]
        self.call(self.teacher, "POST", f"/api/v1/courses/{course_id}/members",
                  {"user_id": self.user_id("24201710"), "member_role": "student"})

        filtered = self.teacher.get(f"/api/v1/courses/{course_id}/members?member_role=student&q=姜")
        self.assertEqual(filtered.status_code, 200, filtered.get_data(as_text=True))
        self.assertEqual([item["student_no"] for item in filtered.json["data"]], ["24201710"])

        empty = self.teacher.get(f"/api/v1/courses/{course_id}/members?q=查无此人")
        self.assertEqual(empty.status_code, 200, empty.get_data(as_text=True))
        self.assertEqual(empty.json["data"], [])

    def user_id(self, student_no):
        db = connect(self.path)
        try:
            return db.execute("SELECT id FROM user WHERE student_no=?", (student_no,)).fetchone()["id"]
        finally:
            db.close()
