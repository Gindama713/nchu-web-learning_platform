"""T005 SQLite module/HTTP isolation tests; NOT SPEC-001 login integration evidence."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from flask import Flask, request

from backend.apis.knowledge import blueprint
from backend.models.knowledge import KnowledgeError, KnowledgeStore
from backend.models.knowledge_migration import CHECKSUM, VERSION, apply


class FixtureSecurity:
    """HTTP test double only. Never registered by production app."""
    user_id = 1

    def current_user_id(self):
        return self.user_id

    def verify_write_request(self):
        if request.headers.get("X-CSRF-Token") != "fixture" or request.headers.get("Origin") != "http://localhost":
            raise KnowledgeError(403, "CSRF_FAILED", "测试 CSRF/Origin 拒绝")


class KnowledgeTest(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.path = Path(self.temporary.name)/"fixture.db"
        with closing(sqlite3.connect(self.path)) as db, db:
            # Minimal SPEC-001 contract fixture, not an implemented identity module.
            db.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE user(id INTEGER PRIMARY KEY,role TEXT,active INTEGER);
                CREATE TABLE course(id INTEGER PRIMARY KEY,teacher_id INTEGER,chapters_revision INTEGER DEFAULT 0);
                CREATE TABLE course_member(course_id INTEGER,user_id INTEGER,member_role TEXT,active INTEGER);
                CREATE TABLE schema_migration(version TEXT PRIMARY KEY,checksum TEXT,applied_at TEXT);
                INSERT INTO user VALUES(1,'teacher',1),(2,'student',1),(3,'student',1),(4,'teacher',1),(5,'admin',1);
                INSERT INTO course(id,teacher_id) VALUES(1,1),(2,4);
                INSERT INTO course_member VALUES(1,1,'teacher',1),(1,2,'student',1),(1,3,'student',1),(2,4,'teacher',1);
            """)
            db.execute("BEGIN IMMEDIATE")
            apply(db)
            db.execute("INSERT INTO schema_migration VALUES(?,?,?)", (VERSION, CHECKSUM, "2026-10-13T00:00:00Z"))
        self.store = KnowledgeStore(self.path)
        self.chapter = self.store.add_chapter(1, 1, {"title": "CPU"})["id"]
        self.item = self.create("程序计数器", True)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, DATABASE_PATH=str(self.path))
        self.app.register_blueprint(blueprint)
        self.security = FixtureSecurity()
        self.app.extensions["course_security"] = self.security
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary.cleanup()

    def create(self, title, published):
        return self.store.save_knowledge(1, self.chapter, {
            "title": title, "content": "<p>PC 保存下一条指令地址</p>",
            "example": "PC ← PC + 1", "published": published, "is_foundational": True,
        }, True)["id"]

    def assert_error(self, status, action):
        with self.assertRaises(KnowledgeError) as result:
            action()
        self.assertEqual(result.exception.status, status)

    def test_ac01_search_pagination_and_visibility(self):
        self.create("隐私草稿", False)
        empty_chapter = self.store.add_chapter(1, 1, {"title": "空章节"})
        items, total = self.store.list_knowledge(2, 1, 1, 20, "程序计数器")
        self.assertEqual(total, 1)
        self.assertEqual(items[0]["id"], self.item)
        self.assertEqual(self.store.list_knowledge(2, 1, 1, 20, "%")[1], 0)
        self.assertEqual(self.store.list_knowledge(2, 1, 99, 20)[0], [])
        self.assertEqual(self.store.list_knowledge(1, 1, 1, 20)[1], 2)
        student_chapters = self.store.chapters(2, 1, 1, 20)[0]
        self.assertNotIn(empty_chapter["id"], [row["id"] for row in student_chapters])

    def test_ac02_bookmark_idempotency_reopen_and_user_isolation(self):
        for _ in range(2):
            self.store.personal_state(2, self.item, {"bookmarked": True}, "bookmark")
        reopened = KnowledgeStore(self.path)
        self.assertTrue(reopened.detail(2, self.item)["is_bookmarked"])
        self.assertFalse(reopened.detail(3, self.item)["is_bookmarked"])
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute("SELECT count(*) FROM bookmark").fetchone()[0], 1)
        reopened.personal_state(2, self.item, {"bookmarked": False}, "bookmark")
        self.assertFalse(reopened.detail(2, self.item)["is_bookmarked"])

    def test_ac03_progress_is_durable_idempotent_and_resettable(self):
        self.store.personal_state(2, self.item, {"completed": True}, "progress")
        first = self.store.detail(2, self.item)["progress"]
        self.store.personal_state(2, self.item, {"completed": True}, "progress")
        self.assertEqual(KnowledgeStore(self.path).detail(2, self.item)["progress"], first)
        self.assertTrue(first["completed_at"].endswith("Z"))
        self.assertFalse(self.store.detail(3, self.item)["progress"]["completed"])
        self.store.personal_state(2, self.item, {"completed": False}, "progress")
        self.assertEqual(self.store.detail(2, self.item)["progress"], {"completed": False, "completed_at": None})

    def test_ac04_unpublish_all_student_entry_points_and_keep_history(self):
        self.store.personal_state(2, self.item, {"completed": True}, "progress")
        self.store.personal_state(2, self.item, {"bookmarked": True}, "bookmark")
        self.store.save_knowledge(1, self.item, {"published": False})
        self.assertEqual(self.store.list_knowledge(2, 1, 1, 20)[1], 0)
        self.assert_error(404, lambda: self.store.detail(2, self.item))
        for kind, field in (("bookmark", "bookmarked"), ("progress", "completed")):
            self.assert_error(404, lambda field=field, kind=kind: self.store.personal_state(2, self.item, {field: True}, kind))
        self.store.save_knowledge(1, self.item, {"published": True})
        self.assertTrue(self.store.detail(2, self.item)["progress"]["completed"])
        self.assertTrue(self.store.detail(2, self.item)["is_bookmarked"])

    def test_r20_revision_and_safe_markup(self):
        original = self.store.detail(1, self.item)
        same = self.store.save_knowledge(1, self.item, {"title": original["title"]})
        self.assertEqual(same["content_revision"], original["content_revision"])
        for field, value in (("title", "寄存器"), ("content", "新的正文"), ("example", "例题"),
                             ("published", False), ("is_foundational", False)):
            updated = self.store.save_knowledge(1, self.item, {field: value})
            self.assertEqual(updated["content_revision"], same["content_revision"]+1)
            same = updated
        safe = self.store.save_knowledge(1, self.item, {"content": '<p onclick="x()">公式<sup>2</sup></p><img src=x onerror=x()><script>alert(1)</script>'})
        self.assertNotIn("onclick", safe["content"])
        self.assertNotIn("<script", safe["content"])
        self.assertNotIn("<img", safe["content"])
        self.assertIn("<sup>2</sup>", safe["content"])

    def test_r32_atomic_complete_order_revision_and_rename(self):
        second = self.store.add_chapter(1, 1, {"title": "ALU"})["id"]
        before = self.store.chapters(1, 1, 1, 20)
        rev = before[2]
        for ids in ([second], [second, second], [second, self.chapter, 999], [True, second]):
            self.assert_error(400, lambda ids=ids: self.store.reorder(1, 1, {"chapters_revision": rev, "chapter_ids": ids}))
            self.assertEqual(self.store.chapters(1, 1, 1, 20), before)
        self.assert_error(409, lambda: self.store.reorder(1, 1, {"chapters_revision": rev-1, "chapter_ids": [second, self.chapter]}))
        result = self.store.reorder(1, 1, {"chapters_revision": rev, "chapter_ids": [second, self.chapter]})
        self.assertEqual([row["position"] for row in result["items"]], [0, 1])
        self.assertEqual(result["items"][0]["id"], second)
        self.store.rename_chapter(1, second, {"title": "算术逻辑单元"})
        self.assertEqual(self.store.chapters(1, 1, 1, 20)[2], rev+1)

    def test_r32_concurrent_add_vs_order_cannot_lose_new_chapter(self):
        revision = self.store.chapters(1, 1, 1, 20)[2]
        def order():
            try:
                self.store.reorder(1, 1, {"chapters_revision": revision, "chapter_ids": [self.chapter]})
                return 200
            except KnowledgeError as error:
                return error.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            added = pool.submit(self.store.add_chapter, 1, 1, {"title": "并发新增"})
            ordered = pool.submit(order)
            added.result()
            self.assertIn(ordered.result(), (200, 409))
        rows, total, _ = self.store.chapters(1, 1, 1, 20)
        self.assertEqual(total, 2)
        self.assertEqual([row["position"] for row in rows], [0, 1])

    def test_r38_current_published_set_and_retained_facts(self):
        other, last = self.create("ALU", True), self.create("IR", True)
        for item in (self.item, other):
            self.store.personal_state(2, item, {"completed": True}, "progress")
        def facts():
            rows = self.store.progress_facts(2, 1)
            return sum(row["completed"] for row in rows), len(rows)
        self.assertEqual(facts(), (2, 3))
        self.store.save_knowledge(1, self.item, {"published": False})
        self.assertEqual(facts(), (1, 2))
        self.store.save_knowledge(1, self.item, {"published": True})
        self.store.save_knowledge(1, last, {"published": False})
        self.assertEqual(facts(), (2, 2))
        for item in (self.item, other):
            self.store.save_knowledge(1, item, {"published": False})
        self.assertEqual(facts(), (0, 0))
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute("SELECT count(*) FROM learning_progress WHERE completed=1").fetchone()[0], 2)

    def test_permission_revocation_global_role_and_admin_no_teacher_privilege(self):
        self.assert_error(404, lambda: self.store.detail(4, self.item))
        self.assert_error(403, lambda: self.store.save_knowledge(2, self.item, {"title": "越权"}))
        self.assert_error(403, lambda: self.store.save_knowledge(5, self.item, {"title": "管理员越权"}))
        self.assert_error(403, lambda: self.store.personal_state(1, self.item, {"completed": True}, "progress"))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE course_member SET active=0 WHERE user_id=1")
        self.assert_error(404, lambda: self.store.add_chapter(1, 1, {"title": "负责人不绕授权"}))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE user SET active=0 WHERE id=2")
        self.assert_error(401, lambda: self.store.detail(2, self.item))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE user SET role='student' WHERE id=4")
        self.assert_error(404, lambda: self.store.chapters(4, 2, 1, 20))

    def test_http_closed_security_csrf_and_validation(self):
        del self.app.extensions["course_security"]
        self.assertEqual(self.client.get("/api/v1/knowledge-points/1").status_code, 503)
        self.app.extensions["course_security"] = self.security
        self.security.user_id = None
        self.assertEqual(self.client.get("/api/v1/knowledge-points/1").status_code, 401)
        self.security.user_id = 2
        url = f"/api/v1/knowledge-points/{self.item}/progress"
        self.assertEqual(self.client.put(url, json={"completed": True}).status_code, 403)
        headers = {"X-CSRF-Token": "fixture", "Origin": "http://localhost"}
        for body in ({"completed": 1}, {"completed": "true"}, {"completed": True, "user_id": 3}, [], {}):
            response = self.client.put(url, json=body, headers=headers)
            self.assertEqual(response.status_code, 400)
            self.assertIn("request_id", response.json)
        self.assertEqual(self.client.put(url, data="{", content_type="application/json", headers=headers).status_code, 400)
        self.assertEqual(self.client.put(url, data="x", headers=headers).status_code, 415)
        self.assertEqual(self.client.put(url, json={"completed": True}, headers=headers).status_code, 200)
        for suffix in ("?page_size=101", "?page=0", "?published=false", "?page=1&page=2", "?chapter_id=true"):
            self.assertEqual(self.client.get("/api/v1/courses/1/knowledge-points"+suffix).status_code, 400)
        response = self.client.get("/api/v1/courses/1/knowledge-points?page=99")
        self.assertEqual(response.json["data"], [])
        self.assertEqual(response.json["total"], 1)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_migration_preconditions_rollback_checksum_and_no_silent_init(self):
        missing = KnowledgeStore(Path(self.temporary.name)/"absent.db")
        self.assert_error(503, lambda: missing.detail(2, self.item))
        self.assertFalse(missing.path.exists())
        with closing(sqlite3.connect(":memory:")) as db, db:
            with self.assertRaises(RuntimeError):
                apply(db)
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN")
            with self.assertRaises(RuntimeError):
                apply(db)
            db.rollback()
            self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0], 0)
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO chapter(course_id,title,position) VALUES(1,'冲突',0)")
            db.execute("UPDATE schema_migration SET checksum='invalid'")
        self.assert_error(503, lambda: self.store.detail(2, self.item))

