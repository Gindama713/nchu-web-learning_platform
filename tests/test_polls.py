"""课堂即时投票的接口测试。

覆盖：只有已签到的学生能投、一人一票、单选/多选/判断题的选项目数与上限、
正确答案与对错统计、投票前看不到分布、关闭后不能再投、匿名与实名两种明细、
以及学生不能发起/结束投票。
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


class PollTest(TestCase):
    def setUp(self):
        with NamedTemporaryFile(dir=Path(__file__).parent, delete=False) as temporary:
            self.path = Path(temporary.name)
        migrate(self.path)
        self.at = datetime(2026, 11, 12, 8, tzinfo=UTC)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.path),
                               "SECRET_KEY": "test-secret-for-csrf", "TEST_NOW": self.at})
        self.admin = self.app.test_client()
        self.teacher = self.app.test_client()
        self.auth(self.admin, self.install("ADMIN0001", "Admin", "admin"))
        self.auth(self.teacher, self.install("TEACH0001", "Teacher", "teacher"))
        self.course_id = self.make_course()
        self.students = self.enroll(3)

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    # ---- 夹具 -------------------------------------------------------------

    def install(self, number, name, role):
        db = connect(self.path)
        try:
            db.execute(
                "INSERT INTO user(student_no,name,password_hash,role,class_name,active,created_at,updated_at) "
                "VALUES(?,?,?,?,?,1,?,?)",
                (number, name, generate_password_hash(PASSWORD), role, "计科2401",
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

    def user_id(self, student_no):
        db = connect(self.path)
        try:
            return db.execute("SELECT id FROM user WHERE student_no=?", (student_no,)).fetchone()["id"]
        finally:
            db.close()

    def make_course(self):
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        created = self.call(self.admin, "POST", "/api/v1/courses",
                            {"title": "计算机组成原理", "teacher_id": teacher_id})
        self.assertEqual(created.status_code, 201, created.json)
        return created.json["data"]["id"]

    def enroll(self, count):
        numbers = []
        for index in range(count):
            number = f"242100{index:02d}"
            self.install(number, f"学生{index:02d}", "student")
            added = self.call(self.teacher, "POST", f"/api/v1/courses/{self.course_id}/members",
                              {"user_id": self.user_id(number), "member_role": "student"})
            self.assertEqual(added.status_code, 201, added.json)
            numbers.append(number)
        return numbers

    def make_task(self):
        created = self.call(self.teacher, "POST", f"/api/v1/courses/{self.course_id}/attendance-tasks",
                            {"title": "课堂点到", "start_at": (self.at - timedelta(minutes=5)).isoformat(),
                             "late_at": (self.at + timedelta(minutes=10)).isoformat(),
                             "end_at": (self.at + timedelta(minutes=40)).isoformat()})
        self.assertEqual(created.status_code, 201, created.json)
        return created.json["data"]["id"]

    def check_in(self, task_id, student_no, status="present"):
        db = connect(self.path)
        try:
            db.execute("INSERT INTO attendance_record(task_id,student_id,status,checked_at,source,"
                       "created_at,updated_at) VALUES(?,?,?,?, 'checkin',?,?)",
                       (task_id, self.user_id(student_no), status, self.at.isoformat(),
                        self.at.isoformat(), self.at.isoformat()))
            db.commit()
        finally:
            db.close()

    def client_for(self, student_no):
        client = self.app.test_client()
        self.auth(client, student_no)
        return client

    def make_poll(self, **overrides):
        payload = {"task_id": self.task_id, "title": "这段流水线有几处数据冒险？",
                   "type": "single", "options": ["1 处", "2 处", "3 处"],
                   "correct_ordinals": [2]}
        payload.update(overrides)
        created = self.call(self.teacher, "POST", f"/api/v1/courses/{self.course_id}/polls", payload)
        return created

    # ---- 用例 -------------------------------------------------------------

    def test_only_checked_in_students_can_vote(self):
        self.task_id = self.make_task()
        first, second, third = self.students
        self.check_in(self.task_id, first)
        self.check_in(self.task_id, second, status="absent")
        poll = self.make_poll()
        self.assertEqual(poll.status_code, 201, poll.json)
        poll_id = poll.json["data"]["id"]
        self.assertEqual(poll.json["data"]["eligible"], 1, "应到人数只算已签到的")

        voter = self.client_for(first)
        mine = self.call(voter, "POST", f"/api/v1/polls/{poll_id}/ballots", {"option_ids": [1]})
        self.assertEqual(mine.status_code, 201, mine.json)

        # 缺勤：不算已签到
        absent = self.client_for(second)
        denied = self.call(absent, "POST", f"/api/v1/polls/{poll_id}/ballots", {"option_ids": [1]})
        self.assertEqual(denied.status_code, 403, denied.json)
        self.assertEqual(denied.json["error"]["code"], "NOT_CHECKED_IN")

        # 连签到记录都没有
        missing = self.client_for(third)
        denied = self.call(missing, "POST", f"/api/v1/polls/{poll_id}/ballots", {"option_ids": [1]})
        self.assertEqual(denied.status_code, 403, denied.json)

    def test_one_person_one_vote(self):
        self.task_id = self.make_task()
        student = self.students[0]
        self.check_in(self.task_id, student)
        poll_id = self.make_poll().json["data"]["id"]
        voter = self.client_for(student)
        first = self.call(voter, "POST", f"/api/v1/polls/{poll_id}/ballots", {"option_ids": [2]})
        self.assertEqual(first.status_code, 201, first.json)
        again = self.call(voter, "POST", f"/api/v1/polls/{poll_id}/ballots", {"option_ids": [1]})
        self.assertEqual(again.status_code, 409, again.json)
        self.assertEqual(again.json["error"]["code"], "ALREADY_VOTED")
        db = connect(self.path)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM poll_ballot").fetchone()[0], 1)
        finally:
            db.close()

    def test_multiple_choice_limit_and_empty(self):
        self.task_id = self.make_task()
        student = self.students[0]
        self.check_in(self.task_id, student)
        poll = self.make_poll(type="multiple", options=["A", "B", "C", "D"], max_choices=2,
                              correct_ordinals=[1, 3])
        self.assertEqual(poll.status_code, 201, poll.json)
        poll_id = poll.json["data"]["id"]
        voter = self.client_for(student)

        too_many = self.call(voter, "POST", f"/api/v1/polls/{poll_id}/ballots",
                             {"option_ids": [1, 2, 3]})
        self.assertEqual(too_many.status_code, 422, too_many.json)
        self.assertEqual(too_many.json["error"]["code"], "TOO_MANY_CHOICES")

        empty = self.call(voter, "POST", f"/api/v1/polls/{poll_id}/ballots", {"option_ids": []})
        self.assertEqual(empty.status_code, 422, empty.json)
        self.assertEqual(empty.json["error"]["code"], "EMPTY_CHOICE")

        # 不存在的选项
        bad = self.call(voter, "POST", f"/api/v1/polls/{poll_id}/ballots", {"option_ids": [999]})
        self.assertEqual(bad.status_code, 422, bad.json)
        self.assertEqual(bad.json["error"]["code"], "INVALID_OPTION")

        ok = self.call(voter, "POST", f"/api/v1/polls/{poll_id}/ballots", {"option_ids": [1, 3]})
        self.assertEqual(ok.status_code, 201, ok.json)

    def test_boolean_poll_has_fixed_options_and_accuracy(self):
        """判断题：选项自动是「正确/错误」，老师标了答案后能算出正确率。"""
        self.task_id = self.make_task()
        right, wrong, idle = self.students
        for number in (right, wrong):
            self.check_in(self.task_id, number)
        poll = self.make_poll(type="boolean", options=[], correct_ordinals=[1])
        self.assertEqual(poll.status_code, 201, poll.json)
        data = poll.json["data"]
        self.assertEqual([option["label"] for option in data["options"]], ["正确", "错误"])
        poll_id = data["id"]
        correct_id, wrong_id = [option["id"] for option in data["options"]]

        self.call(self.client_for(right), "POST", f"/api/v1/polls/{poll_id}/ballots",
                  {"option_ids": [correct_id]})
        self.call(self.client_for(wrong), "POST", f"/api/v1/polls/{poll_id}/ballots",
                  {"option_ids": [wrong_id]})

        results = self.teacher.get(f"/api/v1/polls/{poll_id}/results").json["data"]
        self.assertEqual(results["voted"], 2)
        self.assertEqual(results["eligible"], 2)
        self.assertEqual(results["correct"]["right"], 1)
        self.assertEqual(results["correct"]["wrong"], 1)
        self.assertAlmostEqual(results["correct"]["accuracy"], 0.5)
        self.assertEqual({item["option_id"] for item in results["counts"] if item["is_correct"]},
                         {correct_id})
        # 第三人没签到，既不进 eligible，也不进「未投名单」
        unvoted = [item["student_no"] for item in results["unvoted"]]
        self.assertEqual(unvoted, [], "两个签到的人都投了")
        self.assertNotIn(idle, unvoted)

    def test_student_cannot_see_results_before_voting(self):
        self.task_id = self.make_task()
        first, second, _third = self.students
        for number in (first, second):
            self.check_in(self.task_id, number)
        poll_id = self.make_poll().json["data"]["id"]
        self.call(self.client_for(first), "POST", f"/api/v1/polls/{poll_id}/ballots",
                  {"option_ids": [1]})

        before = self.client_for(second).get(f"/api/v1/polls/{poll_id}/results")
        self.assertEqual(before.status_code, 403, before.json)
        detail = self.client_for(second).get(f"/api/v1/polls/{poll_id}").json["data"]
        self.assertNotIn("counts", detail, "未投票时详情里不给分布")
        self.assertNotIn("correct_option_ids", detail, "未投票时也不泄露正确答案")

        voter = self.client_for(first)
        after = voter.get(f"/api/v1/polls/{poll_id}")
        self.assertEqual(after.status_code, 200)
        self.assertEqual(len(after.json["data"]["counts"]), 3)
        self.assertEqual(after.json["data"]["correct_option_ids"], [2])

    def test_close_and_task_window(self):
        self.task_id = self.make_task()
        student = self.students[0]
        self.check_in(self.task_id, student)
        poll_id = self.make_poll().json["data"]["id"]
        closed = self.call(self.teacher, "POST", f"/api/v1/polls/{poll_id}/close")
        self.assertEqual(closed.status_code, 200, closed.json)
        self.assertEqual(closed.json["data"]["status"], "closed")
        denied = self.call(self.client_for(student), "POST", f"/api/v1/polls/{poll_id}/ballots",
                           {"option_ids": [1]})
        self.assertEqual(denied.status_code, 409, denied.json)
        self.assertEqual(denied.json["error"]["code"], "POLL_CLOSED")
        # 再关一次是幂等的
        self.assertEqual(self.call(self.teacher, "POST", f"/api/v1/polls/{poll_id}/close").status_code, 200)

        # 考勤任务结束 → 投票自动失效（读时判定，不依赖定时任务）
        second_task = self.make_task()
        self.check_in(second_task, student)
        live = self.make_poll(task_id=second_task).json["data"]["id"]
        self.call(self.teacher, "POST", f"/api/v1/attendance-tasks/{second_task}/close")
        state = self.teacher.get(f"/api/v1/polls/{live}").json["data"]
        self.assertFalse(state["open"], "任务关了就投不了")
        denied = self.call(self.client_for(student), "POST", f"/api/v1/polls/{live}/ballots",
                           {"option_ids": [1]})
        self.assertEqual(denied.status_code, 409, denied.json)

    def test_anonymous_hides_details_but_keeps_unvoted_list(self):
        self.task_id = self.make_task()
        first, second, third = self.students
        for number in (first, second):
            self.check_in(self.task_id, number)
        poll_id = self.make_poll(anonymous=True).json["data"]["id"]
        self.call(self.client_for(first), "POST", f"/api/v1/polls/{poll_id}/ballots",
                  {"option_ids": [1]})
        results = self.teacher.get(f"/api/v1/polls/{poll_id}/results").json["data"]
        self.assertEqual(results["details"], [], "匿名投票不给逐人明细")
        # 未投名单只含「已签到但没投」的人：second 签到了没投，third 没签到不算
        self.assertEqual([item["student_no"] for item in results["unvoted"]], [second])
        self.assertNotIn(third, [item["student_no"] for item in results["unvoted"]])

        # 实名投票才有逐人明细
        named = self.make_poll(title="实名投票", anonymous=False).json["data"]
        # 选项 id 是全局自增的，必须用这一场投票自己的 id，不能想当然写 1/2
        self.assertNotEqual(named["options"][0]["id"], 1, "第二个投票的选项 id 应当接着往下排")
        second_option = named["options"][1]["id"]
        voted = self.call(self.client_for(first), "POST", f"/api/v1/polls/{named['id']}/ballots",
                          {"option_ids": [second_option]})
        self.assertEqual(voted.status_code, 201, voted.json)
        named_results = self.teacher.get(f"/api/v1/polls/{named['id']}/results").json["data"]
        self.assertEqual(len(named_results["details"]), 1)
        self.assertTrue(named_results["details"][0]["correct"], "选了正确项")
        self.assertEqual(named_results["details"][0]["labels"], ["2 处"])

    def test_students_cannot_manage_polls(self):
        self.task_id = self.make_task()
        student = self.students[0]
        self.check_in(self.task_id, student)
        poll_id = self.make_poll().json["data"]["id"]
        voter = self.client_for(student)
        created = self.call(voter, "POST", f"/api/v1/courses/{self.course_id}/polls",
                            {"task_id": self.task_id, "title": "学生发起的投票", "type": "single",
                             "options": ["A", "B"]})
        self.assertEqual(created.status_code, 403, created.json)
        closed = self.call(voter, "POST", f"/api/v1/polls/{poll_id}/close")
        self.assertEqual(closed.status_code, 403, closed.json)
        # 教师不能投票
        teacher_vote = self.call(self.teacher, "POST", f"/api/v1/polls/{poll_id}/ballots",
                                 {"option_ids": [1]})
        self.assertEqual(teacher_vote.status_code, 403, teacher_vote.json)

    def test_create_validation(self):
        self.task_id = self.make_task()
        too_few = self.make_poll(options=["只有一项"])
        self.assertEqual(too_few.status_code, 422, too_few.json)
        duplicate = self.make_poll(options=["A", "A"])
        self.assertEqual(duplicate.status_code, 422, duplicate.json)
        bad_type = self.make_poll(type="rank")
        self.assertEqual(bad_type.status_code, 422, bad_type.json)
        bad_correct = self.make_poll(correct_ordinals=[9])
        self.assertEqual(bad_correct.status_code, 422, bad_correct.json)
        # 任务已结束不能再发起
        self.call(self.teacher, "POST", f"/api/v1/attendance-tasks/{self.task_id}/close")
        late = self.make_poll()
        self.assertEqual(late.status_code, 409, late.json)
