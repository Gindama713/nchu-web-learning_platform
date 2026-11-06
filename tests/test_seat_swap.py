"""学生自助换位的接口测试。

覆盖：空位直接坐过去、点在别人座位上生成申请、一次只能挂一条 pending、
不能和自己换、接受后两边座位（含点到快照）真正对调、拒绝、撤回、
超过 15 分钟自动失效、以及「答复前有人挪过座位」这条竞态保护。
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
TTL = 15


class SeatSwapTest(TestCase):
    def setUp(self):
        with NamedTemporaryFile(dir=Path(__file__).parent, delete=False) as temporary:
            self.path = Path(temporary.name)
        migrate(self.path)
        self.at = datetime(2026, 11, 7, 2, tzinfo=UTC)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.path),
                               "SECRET_KEY": "test-secret-for-csrf", "TEST_NOW": self.at})
        self.admin = self.app.test_client()
        self.teacher = self.app.test_client()
        self.auth(self.admin, self.install("ADMIN0001", "Admin", "admin", None))
        self.auth(self.teacher, self.install("TEACH0001", "Teacher", "teacher", None))
        self.course_id = self.make_course()

        self.numbers = self.enroll("计科2401", ["甲", "乙", "丙"])
        placed = self.call(self.teacher, "POST",
                           f"/api/v1/courses/{self.course_id}/classroom/auto-seat")
        self.assertEqual(placed.status_code, 200, placed.json)
        # 按 user_id 顺序整排起排：甲 1排1座、乙 1排2座、丙 1排3座
        self.assertEqual(self.seat_of(self.numbers[0]), (1, 1))
        self.assertEqual(self.seat_of(self.numbers[1]), (1, 2))

        self.task_id = self.make_task()
        self.jia = self.client_for(self.numbers[0])
        self.yi = self.client_for(self.numbers[1])
        self.bing = self.client_for(self.numbers[2])

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
        finally:
            db.close()
        return number

    def call(self, client, method, path, data=None):
        headers = {"Origin": ORIGIN, "X-CSRF-Token": getattr(client, "csrf", "")}
        return client.open(path, method=method, json=data, headers=headers)

    def auth(self, client, number):
        response = self.call(client, "POST", "/api/v1/auth/login",
                             {"student_no": number, "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.json)
        client.csrf = response.json["data"]["csrf_token"]

    def client_for(self, number):
        client = self.app.test_client()
        self.auth(client, number)
        return client

    def make_course(self):
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        created = self.call(self.admin, "POST", "/api/v1/courses",
                            {"title": "计算机组成原理", "teacher_id": teacher_id})
        self.assertEqual(created.status_code, 201, created.json)
        return created.json["data"]["id"]

    def user_id(self, student_no=None, *, number=None):
        db = connect(self.path)
        try:
            return db.execute("SELECT id FROM user WHERE student_no=?",
                              (number or student_no,)).fetchone()["id"]
        finally:
            db.close()

    def enroll(self, class_name, names):
        numbers = []
        for index, name in enumerate(names):
            number = f"242010{index:02d}"
            self.install(number, name, "student", class_name)
            added = self.call(self.teacher, "POST", f"/api/v1/courses/{self.course_id}/members",
                              {"user_id": self.user_id(number), "member_role": "student"})
            self.assertEqual(added.status_code, 201, added.json)
            numbers.append(number)
        return numbers

    def make_task(self):
        start = self.at
        made = self.call(self.teacher, "POST", f"/api/v1/courses/{self.course_id}/attendance-tasks",
                         {"title": "第10周 · 课堂点到", "start_at": start.isoformat(),
                          "late_at": (start + timedelta(minutes=15)).isoformat(),
                          "end_at": (start + timedelta(hours=2)).isoformat()})
        self.assertEqual(made.status_code, 201, made.json)
        return made.json["data"]["id"]

    def seat_of(self, number):
        db = connect(self.path)
        try:
            row = db.execute("SELECT group_no,seat_no FROM class_seat WHERE course_id=? AND student_id=?",
                             (self.course_id, self.user_id(number))).fetchone()
            return (row["group_no"], row["seat_no"]) if row else None
        finally:
            db.close()

    def snapshot_of(self, number):
        db = connect(self.path)
        try:
            row = db.execute("SELECT group_no,seat_no FROM attendance_seat WHERE task_id=? AND student_id=?",
                             (self.task_id, self.user_id(number))).fetchone()
            return (row["group_no"], row["seat_no"]) if row else None
        finally:
            db.close()

    def swap_row(self, swap_id):
        db = connect(self.path)
        try:
            return db.execute("SELECT * FROM seat_swap_request WHERE id=?", (swap_id,)).fetchone()
        finally:
            db.close()

    def ask(self, client, target_number):
        response = self.call(client, "POST", f"/api/v1/courses/{self.course_id}/seat-swaps",
                             {"target_student_id": self.user_id(target_number)})
        self.assertEqual(response.status_code, 201, response.json)
        return response.json["data"]

    def advance(self, minutes):
        self.app.config["TEST_NOW"] = self.at + timedelta(minutes=minutes)

    # ---- 占空位 -----------------------------------------------------------

    def test_move_to_empty_seat_syncs_snapshot(self):
        moved = self.call(self.bing, "PUT", f"/api/v1/courses/{self.course_id}/me/seat",
                          {"group_no": 2, "seat_no": 1})
        self.assertEqual(moved.status_code, 200, moved.json)
        self.assertTrue(moved.json["data"]["moved"])
        self.assertEqual(self.seat_of(self.numbers[2]), (2, 1))
        # 点到快照也要跟着走，否则座位图停在旧位置
        self.assertEqual(self.snapshot_of(self.numbers[2]), (2, 1))

    def test_move_to_taken_seat_is_rejected(self):
        taken = self.call(self.jia, "PUT", f"/api/v1/courses/{self.course_id}/me/seat",
                          {"group_no": 1, "seat_no": 2})
        self.assertEqual(taken.status_code, 409, taken.json)
        self.assertEqual(taken.json["error"]["code"], "SEAT_TAKEN")
        self.assertEqual(self.seat_of(self.numbers[0]), (1, 1))

    def test_move_out_of_range_is_rejected(self):
        far = self.call(self.jia, "PUT", f"/api/v1/courses/{self.course_id}/me/seat",
                        {"group_no": 99, "seat_no": 1})
        self.assertEqual(far.status_code, 422, far.json)
        self.assertEqual(far.json["error"]["code"], "OUT_OF_RANGE")

    # ---- 发起申请 ---------------------------------------------------------

    def test_request_notifies_target(self):
        request = self.ask(self.jia, self.numbers[1])
        self.assertEqual(request["status"], "pending")
        self.assertEqual((request["to_group"], request["to_seat"]), (1, 2))
        self.assertEqual(request["ttl_minutes"], TTL)

        incoming = self.yi.get("/api/v1/seat-swaps/incoming").json["data"]
        self.assertEqual(len(incoming["items"]), 1)
        self.assertEqual(incoming["items"][0]["requester_name"], "甲")
        self.assertEqual(incoming["ttl_minutes"], TTL)

        listed = self.yi.get(f"/api/v1/courses/{self.course_id}/seat-swaps").json["data"]
        self.assertEqual(listed["pending_incoming"], 1)
        self.assertEqual(listed["pending_outgoing"], 0)

        db = connect(self.path)
        try:
            # 建考勤任务本身也会给每个人发一条通知，这里按 event_key 精确取换位那条
            note = db.execute("SELECT title,event_key FROM notification WHERE user_id=? AND event_key=?",
                              (self.user_id(self.numbers[1]),
                               f"seat_swap:{request['id']}")).fetchone()
            self.assertIsNotNone(note)
            self.assertIn("甲", note["title"])
            self.assertEqual(note["event_key"], f"seat_swap:{request['id']}")
        finally:
            db.close()

    def test_only_one_pending_request_at_a_time(self):
        self.ask(self.jia, self.numbers[1])
        second = self.call(self.jia, "POST", f"/api/v1/courses/{self.course_id}/seat-swaps",
                           {"target_student_id": self.user_id(self.numbers[2])})
        self.assertEqual(second.status_code, 409, second.json)
        self.assertEqual(second.json["error"]["code"], "SWAP_PENDING_EXISTS")

    def test_cannot_swap_with_self(self):
        response = self.call(self.jia, "POST", f"/api/v1/courses/{self.course_id}/seat-swaps",
                             {"target_student_id": self.user_id(self.numbers[0])})
        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(response.json["error"]["code"], "CANNOT_SWAP_SELF")

    def test_teacher_cannot_use_student_swap(self):
        response = self.call(self.teacher, "POST", f"/api/v1/courses/{self.course_id}/seat-swaps",
                             {"target_student_id": self.user_id(self.numbers[1])})
        self.assertEqual(response.status_code, 403, response.json)

    # ---- 答复 -------------------------------------------------------------

    def test_accept_swaps_both_sides(self):
        request = self.ask(self.jia, self.numbers[1])
        accepted = self.call(self.yi, "POST",
                             f"/api/v1/courses/{self.course_id}/seat-swaps/{request['id']}/accept")
        self.assertEqual(accepted.status_code, 200, accepted.json)
        self.assertEqual(accepted.json["data"]["status"], "accepted")

        # 甲换到乙原来的 1排2座，乙换到甲原来的 1排1座
        self.assertEqual(self.seat_of(self.numbers[0]), (1, 2))
        self.assertEqual(self.seat_of(self.numbers[1]), (1, 1))
        self.assertEqual(self.snapshot_of(self.numbers[0]), (1, 2))
        self.assertEqual(self.snapshot_of(self.numbers[1]), (1, 1))
        self.assertEqual(self.swap_row(request["id"])["status"], "accepted")

    def test_decline_keeps_seats(self):
        request = self.ask(self.jia, self.numbers[1])
        declined = self.call(self.yi, "POST",
                             f"/api/v1/courses/{self.course_id}/seat-swaps/{request['id']}/decline")
        self.assertEqual(declined.status_code, 200, declined.json)
        self.assertEqual(self.seat_of(self.numbers[0]), (1, 1))
        self.assertEqual(self.seat_of(self.numbers[1]), (1, 2))
        self.assertEqual(self.swap_row(request["id"])["status"], "declined")

    def test_requester_can_cancel(self):
        request = self.ask(self.jia, self.numbers[1])
        cancelled = self.call(self.jia, "DELETE",
                              f"/api/v1/courses/{self.course_id}/seat-swaps/{request['id']}")
        self.assertEqual(cancelled.status_code, 200, cancelled.json)
        self.assertEqual(self.swap_row(request["id"])["status"], "cancelled")
        self.assertEqual(self.yi.get("/api/v1/seat-swaps/incoming").json["data"]["items"], [])
        # 撤掉之后能重新申请
        self.ask(self.jia, self.numbers[2])

    def test_only_target_can_accept(self):
        request = self.ask(self.jia, self.numbers[1])
        response = self.call(self.bing, "POST",
                             f"/api/v1/courses/{self.course_id}/seat-swaps/{request['id']}/accept")
        self.assertEqual(response.status_code, 403, response.json)

    # ---- 超时与竞态 -------------------------------------------------------

    def test_expires_after_fifteen_minutes(self):
        request = self.ask(self.jia, self.numbers[1])
        self.advance(TTL + 1)

        incoming = self.yi.get("/api/v1/seat-swaps/incoming").json["data"]
        self.assertEqual(incoming["items"], [])
        self.assertEqual(self.swap_row(request["id"])["status"], "expired")

        late = self.call(self.yi, "POST",
                         f"/api/v1/courses/{self.course_id}/seat-swaps/{request['id']}/accept")
        self.assertEqual(late.status_code, 409, late.json)
        self.assertEqual(late.json["error"]["code"], "SWAP_NOT_PENDING")
        # 座位一个都没动
        self.assertEqual(self.seat_of(self.numbers[0]), (1, 1))
        self.assertEqual(self.seat_of(self.numbers[1]), (1, 2))

    def test_still_valid_just_before_deadline(self):
        self.ask(self.jia, self.numbers[1])
        self.advance(TTL - 1)
        incoming = self.yi.get("/api/v1/seat-swaps/incoming").json["data"]
        self.assertEqual(len(incoming["items"]), 1)

    def test_accept_fails_when_seat_changed_meanwhile(self):
        request = self.ask(self.jia, self.numbers[1])
        # 老师手动把乙挪走（不走学生换位接口，所以不会自动撤销申请）
        moved = self.call(self.teacher, "PATCH",
                          f"/api/v1/courses/{self.course_id}/seats/{self.user_id(self.numbers[1])}",
                          {"group_no": 3, "seat_no": 3})
        self.assertEqual(moved.status_code, 200, moved.json)

        response = self.call(self.yi, "POST",
                             f"/api/v1/courses/{self.course_id}/seat-swaps/{request['id']}/accept")
        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(response.json["error"]["code"], "SEAT_CHANGED")
        self.assertEqual(self.swap_row(request["id"])["status"], "cancelled")

    def test_moving_cancels_my_pending_request(self):
        request = self.ask(self.jia, self.numbers[1])
        moved = self.call(self.jia, "PUT", f"/api/v1/courses/{self.course_id}/me/seat",
                          {"group_no": 2, "seat_no": 5})
        self.assertEqual(moved.status_code, 200, moved.json)
        self.assertEqual(moved.json["data"]["cancelled"], 1)
        self.assertEqual(self.swap_row(request["id"])["status"], "cancelled")
        # 旧坐标作废后可以马上重新申请
        self.ask(self.jia, self.numbers[1])
