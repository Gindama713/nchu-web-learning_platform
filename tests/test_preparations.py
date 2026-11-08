"""SPEC-004 备课单元接口测试。"""

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


class PreparationApiBase(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "preparation.db"
        migrate(self.path)
        self.password = secrets.token_urlsafe(24)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.path),
                               "SECRET_KEY": secrets.token_hex(32), "APP_ORIGIN": ORIGIN,
                               "TEST_NOW": datetime(2026, 10, 13, 12, tzinfo=UTC)})
        with closing(connect(self.path)) as db:
            for number, role in (("P004ADMIN", "admin"), ("P004TEACH", "teacher")):
                db.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                           "VALUES(?,?,?,?,1,?,?)", (number, number, generate_password_hash(self.password), role,
                                                    "2026-10-13T00:00:00Z", "2026-10-13T00:00:00Z"))
        self.admin, self.teacher, self.student, self.outsider = [self.app.test_client() for _ in range(4)]
        self.login(self.admin, "P004ADMIN")
        self.login(self.teacher, "P004TEACH")
        for client, number in ((self.student, "P004STUD1"), (self.outsider, "P004STUD2")):
            self.call(client, "POST", "/auth/register",
                      {"student_no": number, "name": number, "password": self.password}, 201)
            self.login(client, number)
        self.teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        self.student_id = self.student.get("/api/v1/auth/session").json["data"]["user"]["id"]
        self.course_id = self.call(self.admin, "POST", "/courses",
                                   {"title": "C02d CPU", "teacher_id": self.teacher_id}, 201).json["data"]["id"]
        self.call(self.teacher, "POST", f"/courses/{self.course_id}/members",
                  {"user_id": self.student_id, "member_role": "student"}, 201)
        self.base = f"/courses/{self.course_id}/preparations"

    def call(self, client, method, path, data=None, status=200):
        response = client.open("/api/v1" + path, method=method, json=data,
                               headers={"Origin": ORIGIN, "X-CSRF-Token": getattr(client, "csrf", "")})
        self.assertEqual(response.status_code, status, response.json)
        return response

    def login(self, client, number):
        data = self.call(client, "POST", "/auth/login",
                         {"student_no": number, "password": self.password}).json["data"]
        client.csrf = data["csrf_token"]

    def knowledge_fixture(self):
        chapter = self.call(self.teacher, "POST", f"/courses/{self.course_id}/chapters",
                            {"title": "CPU"}, 201).json["data"]["id"]
        ids = []
        for i in range(2):
            kid = self.call(self.teacher, "POST", f"/chapters/{chapter}/knowledge-points",
                            {"title": f"知识点{i}", "content": "正文", "published": True}, 201).json["data"]["id"]
            ids.append(kid)
        return ids

    def draft(self, **overrides):
        payload = {"title": "备课A", "knowledge_ids": [], "resource_version_ids": [],
                   "question_version_ids": [], "quiz_ids": []}
        payload.update(overrides)
        return self.call(self.teacher, "POST", self.base, payload, 201).json["data"]


class PreparationCreateTest(PreparationApiBase):
    def test_empty_links_and_permissions(self):
        for client in (self.teacher, self.student):
            response = self.call(client, "GET", self.base)
            self.assertEqual(response.json["data"], [])
        self.call(self.outsider, "GET", self.base, status=404)
        self.call(self.admin, "GET", self.base, status=404)
        self.call(self.student, "POST", self.base,
                  {"title": "x", "knowledge_ids": [], "resource_version_ids": [],
                   "question_version_ids": [], "quiz_ids": []}, 403)
        self.call(self.teacher, "POST", self.base,
                  {"title": "x"}, 400)

    def test_create_draft_with_knowledge(self):
        kids = self.knowledge_fixture()
        item = self.draft(knowledge_ids=kids)
        self.assertEqual(item["status"], "draft")
        self.assertEqual(item["knowledge_ids"], sorted(kids))
        self.assertEqual(item["resource_version_ids"], [])
        self.assertEqual(item["question_version_ids"], [])
        self.assertEqual(item["quiz_ids"], [])

    def test_cross_course_knowledge_rejected(self):
        other_course = self.call(self.admin, "POST", "/courses",
                                 {"title": "其他", "teacher_id": self.teacher_id}, 201).json["data"]["id"]
        other_chapter = self.call(self.teacher, "POST", f"/courses/{other_course}/chapters",
                                  {"title": "X"}, 201).json["data"]["id"]
        other_kid = self.call(self.teacher, "POST", f"/chapters/{other_chapter}/knowledge-points",
                              {"title": "外", "content": "x", "published": True}, 201).json["data"]["id"]
        self.call(self.teacher, "POST", self.base,
                  {"title": "x", "knowledge_ids": [other_kid], "resource_version_ids": [],
                   "question_version_ids": [], "quiz_ids": []}, 404)

    def test_invalid_id_lists(self):
        for field in ("knowledge_ids", "resource_version_ids", "question_version_ids", "quiz_ids"):
            payload = {"title": "x", "knowledge_ids": [], "resource_version_ids": [],
                       "question_version_ids": [], "quiz_ids": []}
            payload[field] = [1, 1]
            self.call(self.teacher, "POST", self.base, payload, 400)
            payload[field] = "not-a-list"
            self.call(self.teacher, "POST", self.base, payload, 400)


class PreparationUpdateTest(PreparationApiBase):
    def setUp(self):
        super().setUp()
        self.kids = self.knowledge_fixture()
        self.prep = self.draft(knowledge_ids=self.kids)

    def test_patch_draft_fields(self):
        updated = self.call(self.teacher, "PATCH", f"/preparations/{self.prep['id']}",
                            {"title": "备课B", "scheduled_at": "2026-10-20T08:00:00Z"}).json["data"]
        self.assertEqual(updated["title"], "备课B")
        self.assertEqual(updated["scheduled_at"], "2026-10-20T08:00:00.000Z")
        self.assertEqual(updated["knowledge_ids"], sorted(self.kids))

    def test_patch_replaces_links(self):
        updated = self.call(self.teacher, "PATCH", f"/preparations/{self.prep['id']}",
                            {"knowledge_ids": [self.kids[0]]}).json["data"]
        self.assertEqual(updated["knowledge_ids"], [self.kids[0]])

    def test_patch_published_rejected(self):
        self.call(self.teacher, "POST", f"/preparations/{self.prep['id']}/publish", {})
        self.call(self.teacher, "PATCH", f"/preparations/{self.prep['id']}",
                  {"title": "改"}, 409)


class PreparationPublishTest(PreparationApiBase):
    def setUp(self):
        super().setUp()
        self.kids = self.knowledge_fixture()
        self.prep = self.draft(knowledge_ids=self.kids)

    def test_publish_draft(self):
        published = self.call(self.teacher, "POST", f"/preparations/{self.prep['id']}/publish", {}).json["data"]
        self.assertEqual(published["status"], "published")
        self.assertIsNotNone(published["published_at"])

    def test_publish_with_replaces(self):
        self.call(self.teacher, "POST", f"/preparations/{self.prep['id']}/publish", {})
        copy = self.call(self.teacher, "POST", f"/preparations/{self.prep['id']}/copy",
                         {"title": "备课A新版"}, 201).json["data"]
        replaced = self.call(self.teacher, "POST", f"/preparations/{copy['id']}/publish",
                             {"replaces_id": self.prep["id"]}).json["data"]
        self.assertEqual(replaced["status"], "published")
        self.assertEqual(replaced["replaces_id"], self.prep["id"])
        old = self.call(self.teacher, "GET", f"/preparations/{self.prep['id']}").json["data"]
        self.assertEqual(old["status"], "withdrawn")

    def test_publish_unpublished_quiz_rejected(self):
        with closing(connect(self.path)) as db:
            cursor = db.execute("INSERT INTO paper(course_id,title,kind,status,confidential) "
                                "VALUES(?,?, 'quiz','draft',0)", (self.course_id, "未发布随堂测"))
            paper_id = cursor.lastrowid
            db.commit()
        prep = self.draft(quiz_ids=[paper_id])
        response = self.call(self.teacher, "POST", f"/preparations/{prep['id']}/publish", {}, 409)
        self.assertEqual(response.json["error"]["code"], "QUIZ_NOT_PUBLISHED")

    def test_student_sees_only_published(self):
        self.call(self.teacher, "POST", f"/preparations/{self.prep['id']}/publish", {})
        student_list = self.call(self.student, "GET", self.base).json["data"]
        self.assertEqual(len(student_list), 1)
        self.call(self.student, "GET", f"/preparations/{self.prep['id']}")

    def test_withdraw(self):
        self.call(self.teacher, "POST", f"/preparations/{self.prep['id']}/publish", {})
        withdrawn = self.call(self.teacher, "POST", f"/preparations/{self.prep['id']}/withdraw",
                              {"reason": "内容有误"}).json["data"]
        self.assertEqual(withdrawn["status"], "withdrawn")
        self.assertIsNotNone(withdrawn["withdrawn_at"])
        again = self.call(self.teacher, "POST", f"/preparations/{self.prep['id']}/withdraw",
                          {"reason": "再撤"})
        self.assertEqual(again.json["data"]["status"], "withdrawn")


class PreparationCopyTest(PreparationApiBase):
    def setUp(self):
        super().setUp()
        self.kids = self.knowledge_fixture()
        self.prep = self.draft(knowledge_ids=self.kids)

    def test_copy_preserves_links(self):
        copy = self.call(self.teacher, "POST", f"/preparations/{self.prep['id']}/copy",
                         {"title": "副本"}, 201).json["data"]
        self.assertEqual(copy["status"], "draft")
        self.assertEqual(copy["knowledge_ids"], sorted(self.kids))
        self.assertEqual(copy["source_id"], self.prep["id"])
        original = self.call(self.teacher, "GET", f"/preparations/{self.prep['id']}").json["data"]
        self.assertEqual(original["status"], "draft")
