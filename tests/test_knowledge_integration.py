"""T005 real SPEC-001 session/course/CSRF/SQL-runner integration in a controlled DB.

Only account bootstrap is seeded. All course, member and learning operations
use actual API handlers and cookies; no auth, CSRF or migration mocks.
"""

import secrets
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.models.knowledge_migration import CHECKSUM, VERSION
from backend.shared.db import connect, migrate

ORIGIN = "http://127.0.0.1:5173"


class KnowledgeIntegrationTest(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.path = Path(self.temporary.name)/"course.db"
        self.password = secrets.token_urlsafe(24)
        migrate(self.path)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.path),
                               "SECRET_KEY": secrets.token_hex(32), "APP_ORIGIN": ORIGIN})
        with closing(connect(self.path)) as db:
            for number, role in (("T005ADMIN", "admin"), ("T005TEACH", "teacher")):
                db.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                           "VALUES(?,?,?,?,1,?,?)", (number, number, generate_password_hash(self.password),
                                                    role, "2026-10-13T00:00:00Z", "2026-10-13T00:00:00Z"))
        self.admin, self.teacher, self.student, self.outsider = [self.app.test_client() for _ in range(4)]
        self.login(self.admin, "T005ADMIN")
        self.login(self.teacher, "T005TEACH")
        for client, number in ((self.student, "T005STUD1"), (self.outsider, "T005STUD2")):
            self.call(client, "POST", "/auth/register", {
                "student_no": number, "name": number, "password": self.password}, 201)
            self.login(client, number)
        self.student_id = self.student.get("/api/v1/auth/session").json["data"]["user"]["id"]
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        course = self.call(self.admin, "POST", "/courses", {"title": "T005 controlled CPU", "teacher_id": teacher_id}, 201)
        self.course_id = course.json["data"]["id"]
        self.course = f"/courses/{self.course_id}"
        self.call(self.teacher, "POST", self.course+"/members", {"user_id": self.student_id, "member_role": "student"}, 201)
        chapter = self.call(self.teacher, "POST", self.course+"/chapters", {"title": "CPU"}, 201)
        self.chapter_id = chapter.json["data"]["id"]
        self.point = self.call(self.teacher, "POST", f"/chapters/{self.chapter_id}/knowledge-points", {
            "title": "程序计数器", "content": "<p>PC 指向下一条指令</p>", "published": True,
            "is_foundational": True}, 201).json["data"]["id"]
        self.detail = f"/knowledge-points/{self.point}"

    def tearDown(self):
        self.temporary.cleanup()

    def call(self, client, method, path, data=None, status=200):
        response = client.open("/api/v1"+path, method=method, json=data,
                               headers={"Origin": ORIGIN, "X-CSRF-Token": getattr(client, "csrf", "")})
        self.assertEqual(response.status_code, status, response.json)
        return response

    def login(self, client, number):
        data = self.call(client, "POST", "/auth/login", {"student_no": number, "password": self.password}).json["data"]
        client.csrf = data["csrf_token"]

    def test_real_login_course_publish_bookmark_progress_and_relogin(self):
        draft = self.call(self.teacher, "POST", f"/chapters/{self.chapter_id}/knowledge-points", {
            "title": "未发布", "content": "草稿正文", "published": False}, 201).json["data"]["id"]
        searched = self.call(self.student, "GET", self.course+"/knowledge-points?q=程序计数器")
        self.assertEqual([item["id"] for item in searched.json["data"]], [self.point])
        self.call(self.student, "GET", f"/knowledge-points/{draft}", status=404)
        self.call(self.student, "PUT", self.detail+"/bookmark", {"bookmarked": True})
        self.call(self.student, "PUT", self.detail+"/bookmark", {"bookmarked": True})
        self.call(self.student, "PUT", self.detail+"/progress", {"completed": True})
        before = self.call(self.student, "GET", self.detail).json["data"]
        self.call(self.student, "POST", "/auth/logout", status=204)
        self.call(self.student, "GET", self.detail, status=401)
        self.login(self.student, "T005STUD1")
        after = self.call(self.student, "GET", self.detail).json["data"]
        self.assertTrue(after["is_bookmarked"])
        self.assertEqual(after["progress"], before["progress"])
        self.call(self.teacher, "PATCH", self.detail, {"published": False})
        self.call(self.student, "GET", self.detail, status=404)
        self.call(self.student, "PUT", self.detail+"/progress", {"completed": True}, 404)
        self.assertEqual(self.call(self.student, "GET", self.course+"/knowledge-points").json["total"], 0)
        self.call(self.teacher, "PATCH", self.detail, {"published": True})
        restored = self.call(self.student, "GET", self.detail).json["data"]
        self.assertEqual(restored["progress"], before["progress"])
        self.assertTrue(restored["is_bookmarked"])
        second = self.call(self.teacher, "POST", self.course+"/chapters", {"title": "ALU"}, 201).json["data"]["id"]
        revision = self.call(self.teacher, "GET", self.course+"/chapters").json["chapters_revision"]
        self.call(self.teacher, "PUT", self.course+"/chapter-order", {
            "chapters_revision": revision, "chapter_ids": [second, self.chapter_id]})
        self.call(self.teacher, "PUT", self.course+"/chapter-order", {
            "chapters_revision": revision, "chapter_ids": [self.chapter_id, second]}, 409)

    def test_real_csrf_origin_course_revocation_and_deactivation(self):
        self.call(self.outsider, "GET", self.detail, status=404)
        self.call(self.student, "PATCH", self.detail, {"title": "越权"}, 403)
        self.call(self.student, "PUT", self.detail+"/bookmark", {"bookmarked": True, "user_id": 999}, 400)
        response = self.student.put("/api/v1"+self.detail+"/progress", json={"completed": True},
                                    headers={"Origin": ORIGIN})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json["error"]["code"], "CSRF_FAILED")
        response = self.student.put("/api/v1"+self.detail+"/progress", json={"completed": True},
                                    headers={"Origin": "https://foreign.example", "X-CSRF-Token": self.student.csrf})
        self.assertEqual(response.status_code, 403)
        self.call(self.teacher, "DELETE", self.course+f"/members/{self.student_id}", status=204)
        self.call(self.student, "GET", self.detail, status=404)
        self.call(self.admin, "PATCH", f"/users/{self.student_id}", {"active": False})
        self.call(self.student, "GET", "/auth/session", status=401)
        self.call(self.student, "GET", self.detail, status=401)

    def test_actual_runner_replay_backup_restore_and_checksum_rejection(self):
        self.call(self.student, "PUT", self.detail+"/bookmark", {"bookmarked": True})
        migrate(self.path)
        restored_path = Path(self.temporary.name)/"restored.db"
        with closing(connect(self.path)) as source, closing(connect(restored_path)) as target:
            source.backup(target)
            self.assertEqual(target.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(target.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        migrated_app = create_app({"TESTING": True, "DATABASE_PATH": str(restored_path),
                                   "SECRET_KEY": self.app.config["SECRET_KEY"], "APP_ORIGIN": ORIGIN})
        client = migrated_app.test_client()
        cookie = self.student.get_cookie("cpu_session")
        client.set_cookie("cpu_session", cookie.value)
        self.assertTrue(self.call(client, "GET", self.detail).json["data"]["is_bookmarked"])
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT checksum FROM schema_migration WHERE version=?", (VERSION,)).fetchone()[0], CHECKSUM)
            db.execute("UPDATE schema_migration SET checksum='invalid' WHERE version=?", (VERSION,))
        with self.assertRaises(RuntimeError):
            migrate(self.path)
        self.call(self.student, "GET", self.detail, status=503)
