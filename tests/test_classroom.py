"""教室规模配置与排座的接口测试。

覆盖：默认教室按人数选档、改尺寸时越界座位被清理、一键排座按班分段、
容量不足报 422、手动调座的三种失败路径（越界 / 撞座 / 非本课学生）。
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


class ClassroomTest(TestCase):
    def setUp(self):
        with NamedTemporaryFile(dir=Path(__file__).parent, delete=False) as temporary:
            self.path = Path(temporary.name)
        migrate(self.path)
        self.at = datetime(2026, 11, 6, 8, tzinfo=UTC)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.path),
                               "SECRET_KEY": "test-secret-for-csrf", "TEST_NOW": self.at})
        self.admin = self.app.test_client()
        self.teacher = self.app.test_client()
        self.student = self.app.test_client()
        self.auth(self.admin, self.install("ADMIN0001", "Admin", "admin", None))
        self.auth(self.teacher, self.install("TEACH0001", "Teacher", "teacher", None))
        self.course_id = self.make_course()

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    # ---- 夹具 -------------------------------------------------------------

    def install(self, number, name, role, class_name):
        db = connect(self.path)
        try:
            db.execute(
                "INSERT INTO user(student_no,name,password_hash,role,class_name,active,created_at,updated_at) "
                "VALUES(?,?,?,?,?,1,?,?)",
                (number, name, generate_password_hash(PASSWORD), role, class_name,
                 self.at.isoformat(), self.at.isoformat()))
            return number
        finally:
            db.close()

    def call(self, client, method, path, data=None):
        headers = {"Origin": ORIGIN, "X-CSRF-Token": getattr(client, "csrf", "")}
        return client.open(path, method=method, json=data, headers=headers)

    def auth(self, client, number):
        response = self.call(client, "POST", "/api/v1/auth/login",
                             {"student_no": number, "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.json)
        client.csrf = response.json["data"]["csrf_token"]

    def make_course(self):
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        created = self.call(self.admin, "POST", "/api/v1/courses",
                            {"title": "计算机组成原理", "teacher_id": teacher_id})
        self.assertEqual(created.status_code, 201, created.json)
        return created.json["data"]["id"]

    def user_id(self, student_no):
        db = connect(self.path)
        try:
            return db.execute("SELECT id FROM user WHERE student_no=?", (student_no,)).fetchone()["id"]
        finally:
            db.close()

    def enroll(self, class_name, count, prefix):
        """建 count 个学生并加入课程，返回学号列表。"""
        numbers = []
        for index in range(count):
            number = f"{prefix}{index:02d}"
            self.install(number, f"{class_name}学生{index:02d}", "student", class_name)
            added = self.call(self.teacher, "POST", f"/api/v1/courses/{self.course_id}/members",
                              {"user_id": self.user_id(number), "member_role": "student"})
            self.assertEqual(added.status_code, 201, added.json)
            numbers.append(number)
        return numbers

    def seats(self):
        listed = self.teacher.get(f"/api/v1/courses/{self.course_id}/seats")
        self.assertEqual(listed.status_code, 200, listed.get_data(as_text=True))
        return listed.json["data"]["seats"]

    # ---- 用例 -------------------------------------------------------------

    def test_default_classroom_follows_headcount(self):
        self.enroll("计科2401", 5, "242010")
        state = self.teacher.get(f"/api/v1/courses/{self.course_id}/classroom").json["data"]
        # 5 个人用最小一间就够：6 排 × 8 座
        self.assertEqual((state["rows"], state["cols"]), (6, 8))
        self.assertEqual(state["template"], "small")
        self.assertEqual(state["capacity"], 48)
        self.assertEqual(state["students"], 5)
        self.assertEqual(state["seated"], 0)
        self.assertEqual(state["unseated"], 5)
        self.assertEqual([preset["template"] for preset in state["presets"]],
                         ["small", "large", "lecture"])

    def test_update_size_and_drop_out_of_range_seats(self):
        self.enroll("计科2401", 90, "242020")
        big = self.call(self.teacher, "PUT", f"/api/v1/courses/{self.course_id}/classroom",
                        {"name": "教三 201", "template": "lecture", "rows": 12, "cols": 14,
                         "aisle_every": 2})
        self.assertEqual(big.status_code, 200, big.json)
        self.assertEqual(big.json["data"]["capacity"], 168)

        placed = self.call(self.teacher, "POST", f"/api/v1/courses/{self.course_id}/classroom/auto-seat")
        self.assertEqual(placed.status_code, 200, placed.json)
        self.assertEqual(placed.json["data"]["placed"], 90)

        # 缩到 4 排 × 4 座 = 16 个位置，多出来的座位必须被清掉
        shrunk = self.call(self.teacher, "PUT", f"/api/v1/courses/{self.course_id}/classroom",
                           {"rows": 4, "cols": 4})
        self.assertEqual(shrunk.status_code, 200, shrunk.json)
        self.assertEqual(shrunk.json["data"]["removed"], 74)
        self.assertEqual(shrunk.json["data"]["seated"], 16)
        for seat in self.seats():
            self.assertLessEqual(seat["group_no"], 4)
            self.assertLessEqual(seat["seat_no"], 4)

    def test_auto_seat_gives_each_class_its_own_block(self):
        self.enroll("计科2401", 6, "242030")
        self.enroll("计科2402", 6, "242031")
        self.call(self.teacher, "PUT", f"/api/v1/courses/{self.course_id}/classroom",
                  {"template": "custom", "rows": 4, "cols": 4})
        seated = self.call(self.teacher, "POST", f"/api/v1/courses/{self.course_id}/classroom/auto-seat")
        self.assertEqual(seated.status_code, 200, seated.json)

        seats = self.seats()
        self.assertEqual(len(seats), 12)
        occupied = {(seat["group_no"], seat["seat_no"]) for seat in seats}
        self.assertEqual(len(occupied), 12, "同一坐标不能坐两个人")
        # 4 列时每班 6 人占 2 排：2401 在 1-2 排，2402 在 3-4 排
        first = {seat["group_no"] for seat in seats if seat["class_name"] == "计科2401"}
        second = {seat["group_no"] for seat in seats if seat["class_name"] == "计科2402"}
        self.assertEqual(first, {1, 2})
        self.assertEqual(second, {3, 4})
        self.assertFalse(first & second)

    def test_capacity_exceeded_is_rejected(self):
        self.enroll("计科2401", 9, "242040")
        self.call(self.teacher, "PUT", f"/api/v1/courses/{self.course_id}/classroom",
                  {"rows": 2, "cols": 4})
        response = self.call(self.teacher, "POST",
                             f"/api/v1/courses/{self.course_id}/classroom/auto-seat")
        self.assertEqual(response.status_code, 422, response.json)
        self.assertEqual(response.json["error"]["code"], "CAPACITY_EXCEEDED")
        self.assertEqual(self.seats(), [])

    def test_move_seat_conflicts_and_ranges(self):
        numbers = self.enroll("计科2401", 2, "242050")
        first, second = (self.user_id(number) for number in numbers)
        base = f"/api/v1/courses/{self.course_id}/seats"
        moved = self.call(self.teacher, "PATCH", f"{base}/{first}", {"group_no": 2, "seat_no": 3})
        self.assertEqual(moved.status_code, 200, moved.json)
        self.assertEqual((moved.json["data"]["group_no"], moved.json["data"]["seat_no"]), (2, 3))

        taken = self.call(self.teacher, "PATCH", f"{base}/{second}", {"group_no": 2, "seat_no": 3})
        self.assertEqual(taken.status_code, 409, taken.json)
        self.assertEqual(taken.json["error"]["code"], "SEAT_TAKEN")

        outside = self.call(self.teacher, "PATCH", f"{base}/{second}", {"group_no": 99, "seat_no": 1})
        self.assertEqual(outside.status_code, 422, outside.json)
        self.assertEqual(outside.json["error"]["code"], "OUT_OF_RANGE")

        cleared = self.call(self.teacher, "PATCH", f"{base}/{first}", {"clear": True})
        self.assertEqual(cleared.status_code, 200, cleared.json)
        self.assertEqual(self.seats(), [])

    def test_student_cannot_edit_classroom(self):
        number = self.enroll("计科2401", 1, "242060")[0]
        self.auth(self.student, number)
        denied = self.call(self.student, "PUT", f"/api/v1/courses/{self.course_id}/classroom",
                           {"rows": 2, "cols": 2})
        self.assertEqual(denied.status_code, 403, denied.json)
        # 但学生可以看座位图
        self.assertEqual(self.student.get(f"/api/v1/courses/{self.course_id}/classroom").status_code, 200)

    def test_task_seatmap_is_one_flat_grid(self):
        """座位图接口给的是整张平面网格的坐标，四个班混在一起，不再按班分组。"""
        self.enroll("计科2401", 4, "242070")
        self.enroll("计科2402", 4, "242071")
        self.call(self.teacher, "PUT", f"/api/v1/courses/{self.course_id}/classroom",
                  {"name": "教三 201", "template": "custom", "rows": 4, "cols": 4, "aisle_every": 2})
        self.call(self.teacher, "POST", f"/api/v1/courses/{self.course_id}/classroom/auto-seat")
        task = self.call(self.teacher, "POST", f"/api/v1/courses/{self.course_id}/attendance-tasks",
                         {"title": "课堂点到", "start_at": self.at.isoformat(),
                          "late_at": (self.at + timedelta(minutes=5)).isoformat(),
                          "end_at": (self.at + timedelta(minutes=30)).isoformat()})
        self.assertEqual(task.status_code, 201, task.json)
        task_id = task.json["data"]["id"]

        mapped = self.teacher.get(f"/api/v1/attendance-tasks/{task_id}/seats")
        self.assertEqual(mapped.status_code, 200, mapped.get_data(as_text=True))
        data = mapped.json["data"]
        self.assertNotIn("classes", data, "不再按班分组返回")
        self.assertEqual(data["classroom"]["name"], "教三 201")
        self.assertEqual(data["classroom"]["aisle_every"], 2)
        self.assertEqual(data["grid"], {"rows": 4, "cols": 4})
        self.assertEqual(len(data["seats"]), 8)
        # 坐标全局唯一：四个班同处一张图，不能有两个人坐同一格
        self.assertEqual(len({(seat["group_no"], seat["seat_no"]) for seat in data["seats"]}), 8)
        self.assertEqual({seat["class_name"] for seat in data["seats"]}, {"计科2401", "计科2402"})
        for seat in data["seats"]:
            self.assertEqual(seat["status"], "pending")
            self.assertIsNone(seat["source"])
