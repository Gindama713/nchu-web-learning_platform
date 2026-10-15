"""SPEC-003 resource tests. Each case maps to an acceptance criterion (T003-ACxx)."""

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile, mkdtemp
from unittest import TestCase

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.shared.db import connect, migrate

ORIGIN = "http://127.0.0.1:5173"
PASSWORD = "Long-test-password-42"
AT = datetime(2026, 10, 13, 8, tzinfo=UTC)


def make_pdf(name="test.pdf", size=100):
    """生成最小合法 PDF 字节流。"""
    header = b"%PDF-1.4\n"
    body = b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    tail = b"%%EOF"
    pad = b"X" * max(0, size - len(header) - len(body) - len(tail))
    bio = BytesIO(header + body + pad + tail)
    bio.name = name
    return bio


def make_json(name="bank.json", count=1):
    bio = BytesIO(b'[{"stem":"q"}]' * count)
    bio.name = name
    return bio


class ResourcesTest(TestCase):
    """SPEC-003 教学资源验收测试，覆盖 T003-AC01~AC05。"""

    def setUp(self):
        with NamedTemporaryFile(dir=Path(__file__).parent, delete=False) as temporary:
            self.path = Path(temporary.name)
        self.upload_dir = Path(mkdtemp())
        migrate(self.path)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.path),
                               "UPLOAD_ROOT": str(self.upload_dir),
                               "SECRET_KEY": "test-secret-for-csrf", "TEST_NOW": AT,
                               "APP_ORIGIN": ORIGIN})
        self.admin = self.app.test_client()
        self.teacher = self.app.test_client()
        self.student = self.app.test_client()
        db = connect(self.path)
        try:
            ts = AT.isoformat()
            db.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                       "VALUES(?,?,?,?,1,?,?)",
                       ("ADMIN001", "Admin", generate_password_hash(PASSWORD), "admin", ts, ts))
            db.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                       "VALUES(?,?,?,?,1,?,?)",
                       ("TEACH001", "Teacher", generate_password_hash(PASSWORD), "teacher", ts, ts))
            db.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                       "VALUES(?,?,?,?,1,?,?)",
                       ("STUD0001", "Student", generate_password_hash(PASSWORD), "student", ts, ts))
            db.commit()
        finally:
            db.close()
        self._auth(self.admin, "ADMIN001")
        self._auth(self.teacher, "TEACH001")
        self._auth(self.student, "STUD0001")
        # admin 创建课程并把 teacher/student 加入
        resp = self._call(self.admin, "POST", "/api/v1/courses",
                         {"title": "CPU课程", "teacher_id": self._uid("TEACH001")})
        self.course_id = resp.json["data"]["id"]
        self._add_member(self.course_id, self._uid("TEACH001"), "teacher")
        self._add_member(self.course_id, self._uid("STUD0001"), "student")

    def tearDown(self):
        self.path.unlink(missing_ok=True)
        for f in self.upload_dir.iterdir():
            f.unlink()

    # --- 辅助方法 ---
    def _auth(self, client, number):
        resp = client.open("/api/v1/auth/login", method="POST",
                           json={"student_no": number, "password": PASSWORD},
                           headers={"Origin": ORIGIN})
        self.assertEqual(resp.status_code, 200, resp.json)
        client.csrf = resp.json["data"]["csrf_token"]

    def _uid(self, student_no):
        resp = self.admin.open("/api/v1/users/lookup?student_no=" + student_no,
                               headers={"Origin": ORIGIN})
        return resp.json["data"]["id"]

    def _add_member(self, course_id, uid, role):
        self._call(self.admin, "POST", f"/api/v1/courses/{course_id}/members",
                   {"user_id": uid, "member_role": role})

    def _call(self, client, method, path, data=None):
        headers = {"Origin": ORIGIN, "X-CSRF-Token": getattr(client, "csrf", "")}
        return client.open(path, method=method, json=data, headers=headers)

    def _upload(self, client, course_id, file_io, title, kind, chapter_id=None):
        """multipart 文件上传请求。"""
        data = {"file": (file_io, file_io.name), "title": title, "kind": kind}
        if chapter_id:
            data["chapter_id"] = str(chapter_id)
        return client.open(f"/api/v1/courses/{course_id}/resources", method="POST",
                           data=data, content_type="multipart/form-data",
                           headers={"Origin": ORIGIN, "X-CSRF-Token": client.csrf})

    def _content(self, client, version_id, intent, event_id):
        return client.open(f"/api/v1/resource-versions/{version_id}/content?intent={intent}"
                           f"&event_id={event_id}", headers={"Origin": ORIGIN})

    # ===== T003-AC01：上传后按章节/类型检索 =====
    def test_ac01_list_by_kind_and_chapter(self):
        """覆盖 T003-AC01：上传后按章节/类型检索。"""
        # 先创建章节
        ch = self._call(self.teacher, "POST", f"/api/v1/courses/{self.course_id}/chapters",
                        {"title": "第1章 CPU基础"})
        chapter_id = ch.json["data"]["id"]
        # 上传 slides（关联章节）
        r1 = self._upload(self.teacher, self.course_id, make_pdf("a.pdf"), "课件A", "slides", chapter_id)
        self.assertEqual(r1.status_code, 201, r1.json)
        # 上传 guide（无章节）
        r2 = self._upload(self.teacher, self.course_id, make_pdf("b.pdf"), "实验指导", "guide")
        self.assertEqual(r2.status_code, 201, r2.json)
        # 按 kind=slides 检索
        resp = self._call(self.student, "GET", f"/api/v1/courses/{self.course_id}/resources?kind=slides")
        self.assertEqual(resp.json["total"], 1)
        self.assertEqual(resp.json["data"][0]["title"], "课件A")
        # 按 chapter_id 检索
        resp = self._call(self.student, "GET",
                          f"/api/v1/courses/{self.course_id}/resources?chapter_id={chapter_id}")
        self.assertEqual(resp.json["total"], 1)
        self.assertEqual(resp.json["data"][0]["title"], "课件A")

    # ===== T003-AC02：更新生成新版本且旧引用仍可访问 =====
    def test_ac02_new_version_old_accessible(self):
        """覆盖 T003-AC02：更新生成新版本且旧引用仍可访问。"""
        r = self._upload(self.teacher, self.course_id, make_pdf("v1.pdf"), "课件", "slides")
        rid = r.json["data"]["resource_id"]
        v1_id = r.json["data"]["id"]
        # multipart 上传新版本
        data = {"file": (make_pdf("v2.pdf"), "v2.pdf"), "change_note": "修订版"}
        rv = self.teacher.open(f"/api/v1/resources/{rid}/versions", method="POST",
                               data=data, content_type="multipart/form-data",
                               headers={"Origin": ORIGIN, "X-CSRF-Token": self.teacher.csrf})
        self.assertEqual(rv.status_code, 201, rv.json)
        self.assertEqual(rv.json["data"]["version"], 2)
        # 旧版本仍可访问
        resp = self._content(self.student, v1_id, "view", "evt-old-v1")
        self.assertIn(resp.status_code, (200, 206), resp.json if resp.json else resp.data[:200])

    # ===== T003-AC03：学生不能上传教师资源 =====
    def test_ac03_student_cannot_upload(self):
        """覆盖 T003-AC03：学生不能上传资源（403 FORBIDDEN）。"""
        r = self._upload(self.student, self.course_id, make_pdf("s.pdf"), "学生上传", "slides")
        self.assertEqual(r.status_code, 403, r.json)

    # ===== T003-AC04：大小和类型不合规被拒绝 =====
    def test_ac04_size_and_type_rejected(self):
        """覆盖 T003-AC04：文件大小超限和类型不合规被拒绝。"""
        # 类型不合规：对 slides 上传 JSON
        r = self._upload(self.teacher, self.course_id, make_json("x.json"), "错类型", "slides")
        self.assertEqual(r.status_code, 415, r.json)
        # 大小超限：构造超大文件
        big = BytesIO(b"X" * (20 * 1024 * 1024 + 1))
        big.name = "big.pdf"
        r2 = self._upload(self.teacher, self.course_id, big, "超大", "slides")
        self.assertEqual(r2.status_code, 413, r2.json)

    # ===== T003-AC05：重试按 event_id 去重 =====
    def test_ac05_event_id_dedup(self):
        """覆盖 T003-AC05：同 event_id 重试/Range 分片只记一次访问事件。"""
        r = self._upload(self.teacher, self.course_id, make_pdf("p.pdf"), "PDF课件", "slides")
        vid = r.json["data"]["id"]
        eid = "evt-dedup-001"
        # 第一次 view
        r1 = self._content(self.student, vid, "view", eid)
        self.assertIn(r1.status_code, (200, 206))
        # 同 event_id 重试 → 不冲突，仍成功返回内容
        r2 = self._content(self.student, vid, "view", eid)
        self.assertIn(r2.status_code, (200, 206))
        # 同 event_id 但 intent=download → 409 EVENT_CONFLICT
        r3 = self._content(self.student, vid, "download", eid)
        self.assertEqual(r3.status_code, 409, r3.json)
        # 验证数据库只记录了一条事件
        db = connect(self.path)
        count = db.execute("SELECT COUNT(*) FROM resource_event WHERE event_id=?", (eid,)).fetchone()[0]
        db.close()
        self.assertEqual(count, 1)
