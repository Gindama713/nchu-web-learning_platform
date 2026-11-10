"""课堂手势签到：图案由老师开课时定在任务上，学生照着画。

原来的实现是每个学生给自己设一个图形密码（`PUT /auth/gesture`），教师无法统一
要求，学生也能随时换掉——放到课堂点到里等于自己给自己发口令。现在图案只存在
`attendance_task.gesture_hash` 上，学生端没有任何设置入口。
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import TestCase

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.shared.db import connect, migrate

ORIGIN = "http://127.0.0.1:5173"
PASSWORD = "Long-test-password-42"
# Z 字形：0-1-2 横，2-4-6 斜，6-7-8 横
PATTERN = [0, 1, 2, 4, 6, 7, 8]


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
        self.course_id = self.make_course()
        # 开了手势的任务 + 只发签到码的任务，两边都覆盖
        self.task_id, self.code = self.make_task(pattern=PATTERN)
        self.plain_task_id, self.plain_code = self.make_task()

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

    def make_course(self):
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        created = self.call(self.admin, "POST", "/api/v1/courses",
                            {"title": "计算机组成原理", "teacher_id": teacher_id})
        course_id = created.json["data"]["id"]
        self.call(self.teacher, "POST", f"/api/v1/courses/{course_id}/members",
                  {"user_id": self.user_id("24201718"), "member_role": "student"})
        return course_id

    def make_task(self, pattern=None, title="课堂点到"):
        payload = {"title": title,
                   "start_at": (self.at - timedelta(minutes=1)).isoformat(),
                   "late_at": (self.at + timedelta(minutes=5)).isoformat(),
                   "end_at": (self.at + timedelta(minutes=30)).isoformat()}
        if pattern is not None:
            payload["pattern"] = pattern
        task = self.call(self.teacher, "POST", f"/api/v1/courses/{self.course_id}/attendance-tasks",
                         payload)
        self.assertEqual(task.status_code, 201, task.json)
        return task.json["data"]["id"], task.json["data"]["code"]

    # ---- 用例 -------------------------------------------------------------

    def test_task_exposes_has_gesture_without_leaking_hash(self):
        """任务接口只暴露「开没开手势」，不能把图案或哈希带给学生。"""
        listed = self.student.get(f"/api/v1/courses/{self.course_id}/attendance-tasks").json["data"]
        by_id = {item["id"]: item for item in listed}
        self.assertTrue(by_id[self.task_id]["has_gesture"])
        self.assertFalse(by_id[self.plain_task_id]["has_gesture"])
        self.assertNotIn("gesture_hash", by_id[self.task_id])

    def test_pattern_rules_are_enforced_when_creating_task(self):
        for bad, why in (([0, 1, 2], "少于 4 个点"),
                         ([0, 1, 2, 3, 4, 5, 6, 7, 8, 0], "超过 9 个点"),
                         ([0, 1, 1, 2], "同一个点走两次"),
                         ([0, 1, 2, 9], "点超出 0-8"),
                         ("0125", "不是数组"),
                         ([0, True, 2, 3], "布尔当整数")):
            response = self.call(self.teacher, "POST",
                                 f"/api/v1/courses/{self.course_id}/attendance-tasks",
                                 {"title": "坏图案", "start_at": self.at.isoformat(),
                                  "late_at": (self.at + timedelta(minutes=5)).isoformat(),
                                  "end_at": (self.at + timedelta(minutes=30)).isoformat(),
                                  "pattern": bad})
            self.assertEqual(response.status_code, 422, f"{why}: {response.json}")

    def test_check_in_with_gesture(self):
        response = self.call(self.student, "POST", f"/api/v1/attendance-tasks/{self.task_id}/check-ins",
                             {"pattern": PATTERN})
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(response.json["data"]["status"], "present")
        self.assertEqual(response.json["data"]["source"], "gesture")

    def test_wrong_gesture_is_rejected(self):
        response = self.call(self.student, "POST", f"/api/v1/attendance-tasks/{self.task_id}/check-ins",
                             {"pattern": [8, 7, 6, 3]})
        self.assertEqual(response.status_code, 422, response.json)
        self.assertEqual(response.json["error"]["code"], "INVALID_GESTURE")
        # 失败不写记录，学生仍可以用签到码完成签到
        ok = self.call(self.student, "POST", f"/api/v1/attendance-tasks/{self.task_id}/check-ins",
                       {"code": self.code})
        self.assertEqual(ok.status_code, 201, ok.json)
        self.assertEqual(ok.json["data"]["source"], "checkin")

    def test_gesture_is_rejected_when_task_has_none(self):
        """这次课没开手势签到：画什么都不能签，提示改用签到码。"""
        response = self.call(self.student, "POST",
                             f"/api/v1/attendance-tasks/{self.plain_task_id}/check-ins",
                             {"pattern": PATTERN})
        self.assertEqual(response.status_code, 422, response.json)
        self.assertEqual(response.json["error"]["code"], "GESTURE_NOT_ENABLED")
        # 同一个任务用签到码是通的
        ok = self.call(self.student, "POST", f"/api/v1/attendance-tasks/{self.plain_task_id}/check-ins",
                       {"code": self.plain_code})
        self.assertEqual(ok.status_code, 201, ok.json)

    def test_student_can_no_longer_set_own_pattern(self):
        """旧的个人图案端点已移除，学生没有"自己设口令"的入口。"""
        for method, payload in (("GET", None), ("PUT", {"pattern": PATTERN}), ("DELETE", None)):
            response = self.call(self.student, method, "/api/v1/auth/gesture", payload)
            self.assertEqual(response.status_code, 404, f"{method}: {response.status_code}")

    def test_code_and_pattern_are_mutually_exclusive(self):
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
