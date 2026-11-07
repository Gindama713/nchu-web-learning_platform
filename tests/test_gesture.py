"""手势图案签到：录入、校验、与签到码并存互不干扰。"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import TestCase

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.shared.db import connect, migrate

ORIGIN = "http://127.0.0.1:5173"
PASSWORD = "Long-test-password-42"
PATTERN = [0, 1, 2, 5, 8]


class GestureTest(TestCase):
    def setUp(self):
        with NamedTemporaryFile(dir=Path(__file__).parent, delete=False) as temporary:
            self.path = Path(temporary.name)
        migrate(self.path)
        self.at = datetime(2026, 11, 13, 8, tzinfo=UTC)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.path),
                               "SECRET_KEY": "test-secret-for-csrf", "TEST_NOW": self.at})
        self.admin = self.app.test_client()
        self.teacher = self.app.test_client()
        self.student = self.app.test_client()
        db = connect(self.path)
        try:
            for number, name, role in (("ADMIN0001", "Admin", "admin"),
                                       ("TEACH0001", "Teacher", "teacher"),
                                       ("24201718", "姜苏豪", "student")):
                db.execute("INSERT INTO user(student_no,name,password_hash,role,class_name,active,"
                           "created_at,updated_at) VALUES(?,?,?,?,?,1,?,?)",
                           (number, name, generate_password_hash(PASSWORD), role,
                            "242017" if role == "student" else None,
                            self.at.isoformat(), self.at.isoformat()))
        finally:
            db.close()
        self.auth(self.admin, "ADMIN0001")
        self.auth(self.teacher, "TEACH0001")
        self.auth(self.student, "24201718")
        self.course_id, self.task_id, self.code = self.make_task()

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

    def user_id(self, number):
        db = connect(self.path)
        try:
            return db.execute("SELECT id FROM user WHERE student_no=?", (number,)).fetchone()["id"]
        finally:
            db.close()

    def make_task(self):
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        created = self.call(self.admin, "POST", "/api/v1/courses",
                            {"title": "计算机组成原理", "teacher_id": teacher_id})
        course_id = created.json["data"]["id"]
        self.call(self.teacher, "POST", f"/api/v1/courses/{course_id}/members",
                  {"user_id": self.user_id("24201718"), "member_role": "student"})
        task = self.call(self.teacher, "POST", f"/api/v1/courses/{course_id}/attendance-tasks",
                         {"title": "课堂点到", "start_at": (self.at - timedelta(minutes=1)).isoformat(),
                          "late_at": (self.at + timedelta(minutes=5)).isoformat(),
                          "end_at": (self.at + timedelta(minutes=30)).isoformat()})
        self.assertEqual(task.status_code, 201, task.json)
        return course_id, task.json["data"]["id"], task.json["data"]["code"]

    def enroll(self, pattern=PATTERN):
        return self.call(self.student, "PUT", "/api/v1/auth/gesture", {"pattern": pattern})

    # ---- 用例 -------------------------------------------------------------

    def test_enroll_and_query_gesture(self):
        before = self.student.get("/api/v1/auth/gesture")
        self.assertEqual(before.status_code, 200)
        self.assertFalse(before.json["data"]["enrolled"])

        enrolled = self.enroll()
        self.assertEqual(enrolled.status_code, 200, enrolled.json)
        after = self.student.get("/api/v1/auth/gesture").json["data"]
        self.assertTrue(after["enrolled"])
        self.assertIsNotNone(after["updated_at"])

        cleared = self.call(self.student, "DELETE", "/api/v1/auth/gesture")
        self.assertEqual(cleared.status_code, 200)
        self.assertFalse(self.student.get("/api/v1/auth/gesture").json["data"]["enrolled"])

    def test_pattern_rules_are_enforced(self):
        for bad, why in (([0, 1, 2], "少于 4 个点"),
                         ([0, 1, 2, 3, 4, 5, 6, 7, 8, 0], "超过 9 个点"),
                         ([0, 1, 1, 2], "同一个点走两次"),
                         ([0, 1, 2, 9], "点超出 0-8"),
                         ("0125", "不是数组"),
                         ([0, True, 2, 3], "布尔当整数")):
            response = self.enroll(bad)
            self.assertEqual(response.status_code, 422, f"{why}: {response.json}")

    def test_check_in_with_gesture(self):
        self.assertEqual(self.enroll().status_code, 200)
        response = self.call(self.student, "POST", f"/api/v1/attendance-tasks/{self.task_id}/check-ins",
                             {"pattern": PATTERN})
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(response.json["data"]["status"], "present")
        self.assertEqual(response.json["data"]["source"], "gesture")

    def test_wrong_gesture_is_rejected(self):
        self.assertEqual(self.enroll().status_code, 200)
        response = self.call(self.student, "POST", f"/api/v1/attendance-tasks/{self.task_id}/check-ins",
                             {"pattern": [8, 7, 6, 3]})
        self.assertEqual(response.status_code, 422, response.json)
        self.assertEqual(response.json["error"]["code"], "INVALID_GESTURE")
        # 失败不写记录，学生仍可以用签到码完成签到
        ok = self.call(self.student, "POST", f"/api/v1/attendance-tasks/{self.task_id}/check-ins",
                       {"code": self.code})
        self.assertEqual(ok.status_code, 201, ok.json)
        self.assertEqual(ok.json["data"]["source"], "checkin")

    def test_gesture_not_enrolled(self):
        response = self.call(self.student, "POST", f"/api/v1/attendance-tasks/{self.task_id}/check-ins",
                             {"pattern": PATTERN})
        self.assertEqual(response.status_code, 422, response.json)
        self.assertEqual(response.json["error"]["code"], "GESTURE_NOT_ENROLLED")

    def test_code_and_pattern_are_mutually_exclusive(self):
        self.assertEqual(self.enroll().status_code, 200)
        both = self.call(self.student, "POST", f"/api/v1/attendance-tasks/{self.task_id}/check-ins",
                         {"code": self.code, "pattern": PATTERN})
        self.assertEqual(both.status_code, 422, both.json)
        neither = self.call(self.student, "POST", f"/api/v1/attendance-tasks/{self.task_id}/check-ins", {})
        self.assertEqual(neither.status_code, 422, neither.json)

    def test_code_check_in_still_marks_checkin_source(self):
        response = self.call(self.student, "POST", f"/api/v1/attendance-tasks/{self.task_id}/check-ins",
                             {"code": self.code})
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(response.json["data"]["source"], "checkin")
