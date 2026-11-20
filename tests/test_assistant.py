"""SPEC-020 教学助手：只答真实事实、角色隔离、空数据不编数字。"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import TestCase

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.shared.db import connect, migrate

ORIGIN = "http://127.0.0.1:5173"
PASSWORD = "Long-test-password-42"


class AssistantTest(TestCase):
    def setUp(self):
        with NamedTemporaryFile(dir=Path(__file__).parent, delete=False) as temporary:
            self.path = Path(temporary.name)
        migrate(self.path)
        self.at = datetime(2026, 11, 20, 8, tzinfo=UTC)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.path),
                               "SECRET_KEY": "test-secret-for-csrf", "TEST_NOW": self.at})
        self.admin = self.app.test_client()
        self.teacher = self.app.test_client()
        self.student = self.app.test_client()
        db = connect(self.path)
        try:
            for number, name, role in (("ADMIN0001", "Admin", "admin"),
                                       ("TEACH0001", "Teacher", "teacher")):
                db.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                           "VALUES(?,?,?,?,1,?,?)",
                           (number, name, generate_password_hash(PASSWORD), role,
                            self.at.isoformat(), self.at.isoformat()))
        finally:
            db.close()
        self.auth(self.admin, "ADMIN0001")
        self.auth(self.teacher, "TEACH0001")
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        self.course_id = self.call(self.admin, "POST", "/api/v1/courses",
                                   {"title": "CPU", "teacher_id": teacher_id}).json["data"]["id"]
        self.student_id = self.register("STUDENT01")
        self.other_id = self.register("STUDENT02")
        for user_id in (self.student_id, self.other_id):
            self.assertEqual(self.call(self.teacher, "POST", f"/api/v1/courses/{self.course_id}/members",
                                       {"user_id": user_id, "member_role": "student"}).status_code, 201)

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

    def register(self, number):
        response = self.call(self.student, "POST", "/api/v1/auth/register",
                             {"student_no": number, "name": number, "password": PASSWORD})
        self.assertEqual(response.status_code, 201, response.json)
        return response.json["data"]["user"]["id"]

    def ask(self, client, question, **extra):
        return self.call(client, "POST", f"/api/v1/courses/{self.course_id}/assistant/ask",
                         {"question": question, **extra})

    def close_one_task_with_one_present(self):
        """1 人签到、1 人缺勤的已关闭任务：到勤率应为 50%，不是 100%。"""
        task = self.call(self.teacher, "POST", f"/api/v1/courses/{self.course_id}/attendance-tasks",
                         {"title": "第11周点名",
                          "start_at": (self.at - timedelta(minutes=1)).isoformat(),
                          "late_at": (self.at + timedelta(minutes=5)).isoformat(),
                          "end_at": (self.at + timedelta(minutes=30)).isoformat()}).json["data"]
        self.auth(self.student, "STUDENT01")
        self.assertEqual(self.call(self.student, "POST", f"/api/v1/attendance-tasks/{task['id']}/check-ins",
                                   {"code": task["code"]}).status_code, 201)
        self.assertEqual(self.call(self.teacher, "POST", f"/api/v1/attendance-tasks/{task['id']}/close",
                                   {}).status_code, 200)

    def test_teacher_attendance_answer_uses_frozen_denominator(self):
        self.close_one_task_with_one_present()
        response = self.ask(self.teacher, "这周考勤情况怎么样？")
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json["data"]
        self.assertEqual(data["intent"], "attendance")
        self.assertEqual(data["facts"][0]["value"], 50.0)
        self.assertIn("应到 2 人次", data["answer"])
        self.assertEqual(data["role"], "teacher")
        # 只读：提问不能新增统计快照或写业务表
        db = connect(self.path)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM analysis_run").fetchone()[0], 0)
        finally:
            db.close()

    def test_student_sees_only_own_attendance(self):
        self.close_one_task_with_one_present()
        response = self.ask(self.student, "我这段时间考勤怎么样？")
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json["data"]
        self.assertEqual(data["intent"], "my_attendance")
        self.assertEqual(data["facts"][0]["value"], 100.0)
        self.assertIn("应到 1 人次", data["answer"])

    def test_student_cannot_ask_about_someone_else(self):
        self.auth(self.student, "STUDENT01")
        response = self.ask(self.student, "我哪里薄弱？", student_id=self.other_id)
        self.assertEqual(response.status_code, 403, response.json)

    def test_empty_samples_do_not_invent_numbers(self):
        response = self.ask(self.teacher, "哪个知识点最薄弱？")
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json["data"]
        self.assertEqual(data["intent"], "weak_knowledge")
        self.assertEqual(data["facts"], [])
        self.assertIn("没有形成有效的客观题作答记录", data["answer"])

    def test_knowledge_question_cites_published_point(self):
        db = connect(self.path)
        try:
            db.execute("INSERT INTO chapter(id,course_id,title,position) VALUES(1,?,?,0)",
                       (self.course_id, "中央处理器"))
            db.execute("INSERT INTO knowledge_point(id,chapter_id,title,content,example,published,content_revision) "
                       "VALUES(1,1,?,?,?,?,1)", ("程序计数器", "程序计数器 PC 存放当前要执行的指令地址。",
                                                 "取指后 PC 指向下一条指令。", 1))
        finally:
            db.close()
        self.auth(self.student, "STUDENT01")
        response = self.ask(self.student, "程序计数器是什么？")
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json["data"]
        self.assertEqual(data["intent"], "knowledge_qa")
        self.assertTrue(data["matches"])
        self.assertEqual(data["matches"][0]["title"], "程序计数器")
        self.assertGreater(data["matches"][0]["similarity"], 0)

    def test_course_isolation_is_404(self):
        self.auth(self.student, "STUDENT01")
        foreign = self.call(self.admin, "POST", "/api/v1/courses",
                            {"title": "Other", "teacher_id": self.teacher.get(
                                "/api/v1/auth/session").json["data"]["user"]["id"]}).json["data"]["id"]
        response = self.call(self.student, "POST", f"/api/v1/courses/{foreign}/assistant/ask",
                             {"question": "考勤怎么样"})
        self.assertEqual(response.status_code, 404, response.json)

    def test_question_length_and_fields_are_validated(self):
        self.assertEqual(self.ask(self.teacher, "").status_code, 400)
        self.assertEqual(self.ask(self.teacher, "考勤", unknown=1).status_code, 400)

    def seed_knowledge(self):
        db = connect(self.path)
        try:
            db.execute("INSERT INTO chapter(id,course_id,title,position) VALUES(1,?,?,0)",
                       (self.course_id, "中央处理器"))
            db.execute("INSERT INTO knowledge_point(id,chapter_id,title,content,example,published,content_revision) "
                       "VALUES(1,1,?,?,?,1,1)", ("ALU 的运算选择", "ALU 根据控制信号选择运算。", ""))
            db.execute("INSERT INTO knowledge_point(id,chapter_id,title,content,example,published,content_revision) "
                       "VALUES(2,1,?,?,?,1,1)", ("程序计数器", "PC 存放当前指令地址。", ""))
        finally:
            db.close()

    def test_teacher_reads_one_student_attendance(self):
        self.close_one_task_with_one_present()
        response = self.ask(self.teacher, "STUDENT02 到了吗？")
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json["data"]
        self.assertEqual(data["intent"], "student_attendance")
        self.assertEqual(data["facts"][0]["value"], 0.0)
        self.assertIn("缺勤 1", data["answer"])

    def test_teacher_lists_absent_names_for_latest_task(self):
        self.close_one_task_with_one_present()
        response = self.ask(self.teacher, "上次点名谁没到？")
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json["data"]
        self.assertEqual(data["intent"], "session_absence")
        self.assertIn("STUDENT02", data["answer"])
        self.assertTrue(any(fact["label"] == "应到 / 缺勤 / 请假" for fact in data["facts"]))

    def test_student_reads_own_exam_score(self):
        self.seed_knowledge()
        db = connect(self.path)
        try:
            db.execute("INSERT INTO question(id,course_id) VALUES(1,?),(2,?)", (self.course_id, self.course_id))
            db.execute("INSERT INTO question_version(id,question_id,version,type,stem,options_json,answer_json,difficulty) "
                       "VALUES(1,1,1,'boolean','ALU 的运算选择','[]','true','easy')")
            db.execute("INSERT INTO question_version(id,question_id,version,type,stem,options_json,answer_json,difficulty) "
                       "VALUES(2,2,1,'boolean','PC 的作用','[]','true','easy')")
            db.execute("INSERT INTO paper(id,course_id,title,kind,confidential,status,start_at,end_at,review_at) "
                       "VALUES(1,?,'期中考试','exam',0,'draft','2026-11-18T08:00:00.000Z',"
                       "'2026-11-19T08:00:00.000Z','2026-11-20T08:00:00.000Z')", (self.course_id,))
            db.execute("INSERT INTO paper_item VALUES(1,1,1,1,5000)")
            db.execute("INSERT INTO paper_item VALUES(1,2,2,2,5000)")
            db.execute("INSERT INTO paper_participant VALUES(1,?)", (self.student_id,))
            db.execute("UPDATE paper SET status='published' WHERE id=1")
            db.execute("INSERT INTO attempt(id,paper_id,student_id,status,score_hundredths,partial_score_hundredths,"
                       "revision,submitted_at) VALUES(1,1,?,'graded',5000,5000,0,'2026-11-18T09:00:00.000Z')",
                       (self.student_id,))
            db.execute("INSERT INTO answer(attempt_id,question_version_id,value_json,score_hundredths,answered) "
                       "VALUES(1,1,'true',5000,1)")
            db.execute("INSERT INTO answer(attempt_id,question_version_id,value_json,score_hundredths,answered) "
                       "VALUES(1,2,'false',0,1)")
        finally:
            db.close()
        self.auth(self.student, "STUDENT01")
        response = self.ask(self.student, "我考试成绩怎么样？")
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json["data"]
        self.assertEqual(data["intent"], "my_scores")
        self.assertIn(50.0, [fact["value"] for fact in data["facts"]])
        self.assertIn("期中考试", data["answer"])
        self.assertIn("50.0%", data["answer"])

    def test_student_reads_own_practice_records(self):
        self.seed_knowledge()
        db = connect(self.path)
        try:
            db.execute("INSERT INTO question(id,course_id) VALUES(1,?)", (self.course_id,))
            db.execute("INSERT INTO question_version(id,question_id,version,type,stem,options_json,answer_json,"
                       "difficulty,practice_available) VALUES(1,1,1,'boolean','ALU 的运算选择','[]','true','easy',1)")
            db.execute("INSERT INTO question_knowledge VALUES(1,1)")
            db.execute("INSERT INTO practice_attempt(student_id,question_version_id,answer_json,answered,correct,"
                       "score_hundredths,created_at) VALUES(?,1,'true',1,1,10000,'2026-11-19T08:00:00.000Z')",
                       (self.student_id,))
            db.execute("INSERT INTO practice_attempt(student_id,question_version_id,answer_json,answered,correct,"
                       "score_hundredths,created_at) VALUES(?,1,'false',1,0,0,'2026-11-19T09:00:00.000Z')",
                       (self.student_id,))
        finally:
            db.close()
        self.auth(self.student, "STUDENT01")
        response = self.ask(self.student, "我做了多少题？")
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json["data"]
        self.assertEqual(data["intent"], "my_attempts")
        self.assertEqual(data["facts"][0]["value"], 2)
        self.assertIn("50.0", data["answer"])
        self.assertTrue(any(fact["label"] == "错得最多的知识点" for fact in data["facts"]))

    def test_student_asking_about_a_name_still_gets_own_data(self):
        self.close_one_task_with_one_present()
        self.auth(self.student, "STUDENT01")
        response = self.ask(self.student, "STUDENT02 考了多少分？")
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json["data"]
        self.assertEqual(data["intent"], "my_scores")
        self.assertNotIn("STUDENT02", data["answer"])

    def test_class_scores_without_graded_papers_never_says_none(self):
        self.seed_knowledge()
        db = connect(self.path)
        try:
            db.execute("INSERT INTO question(id,course_id) VALUES(1,?)", (self.course_id,))
            db.execute("INSERT INTO question_version(id,question_id,version,type,stem,options_json,answer_json,difficulty) "
                       "VALUES(1,1,1,'boolean','ALU 的运算选择','[]','true','easy')")
            db.execute("INSERT INTO paper(id,course_id,title,kind,confidential,status,start_at,end_at,review_at) "
                       "VALUES(1,?,'期中考试','exam',0,'draft','2026-11-18T08:00:00.000Z',"
                       "'2026-11-19T08:00:00.000Z','2026-11-20T08:00:00.000Z')", (self.course_id,))
            db.execute("INSERT INTO paper_item VALUES(1,1,1,1,5000)")
            db.execute("INSERT INTO paper_participant VALUES(1,?)", (self.student_id,))
            db.execute("UPDATE paper SET status='published' WHERE id=1")
        finally:
            db.close()
        response = self.ask(self.teacher, "这次考试平均分多少？")
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json["data"]
        self.assertEqual(data["intent"], "class_scores")
        self.assertNotIn("None", data["answer"])
        self.assertIn("没有已评分答卷", data["answer"])
