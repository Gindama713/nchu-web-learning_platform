"""SPEC-005 knowledge image references over real SPEC-001/003 handlers."""

import os
from contextlib import closing
from io import BytesIO
from uuid import uuid4

import cv2
import numpy as np

from backend.shared.db import connect
from tests.test_knowledge_integration import ORIGIN, KnowledgeIntegrationTest


def encoded(extension):
    ok, buffer = cv2.imencode(extension, np.zeros((3, 5, 3), dtype=np.uint8))
    assert ok
    return buffer.tobytes()


PNG = encoded(".png")
JPEG = encoded(".jpg")


class KnowledgeImageTest(KnowledgeIntegrationTest):
    def setUp(self):
        super().setUp()
        self.upload_root = self.temporary.name + "/uploads"
        self.app.config["UPLOAD_ROOT"] = self.upload_root

    def upload(self, client, content, name, mime, title="知识配图"):
        response = client.open(
            "/api/v1" + self.course + "/resources", method="POST",
            data={"file": (BytesIO(content), name, mime), "title": title, "kind": "guide"},
            content_type="multipart/form-data",
            headers={"Origin": ORIGIN, "X-CSRF-Token": getattr(client, "csrf", "")})
        self.assertEqual(response.status_code, 201, response.json)
        return response.json["data"]

    def add_version(self, resource_id, content, name, mime):
        response = self.teacher.open(
            f"/api/v1/resources/{resource_id}/versions", method="POST",
            data={"file": (BytesIO(content), name, mime), "change_note": "v2"},
            content_type="multipart/form-data",
            headers={"Origin": ORIGIN, "X-CSRF-Token": self.teacher.csrf})
        self.assertEqual(response.status_code, 201, response.json)
        return response.json["data"]

    def image_content(self, client, image_id, event_id):
        return client.get(
            f"/api/v1/knowledge-points/{self.point}/images/{image_id}/content"
            f"?event_id={event_id}", headers={"Origin": ORIGIN})

    def image_count(self):
        with closing(connect(self.path)) as db:
            return db.execute("SELECT count(*) FROM resource_event").fetchone()[0]

    def attach(self, version_id, **overrides):
        image = {"resource_version_id": version_id, "placement": "content",
                 "alt": "程序计数器示意", "caption": "固定资源版本"}
        image.update(overrides)
        return self.call(self.teacher, "PATCH", self.detail, {"images": [image]})

    def test_teacher_saves_student_reads_fixed_version_and_relogin(self):
        png = self.upload(self.teacher, PNG, "pc.png", "image/png")
        jpeg = self.upload(self.teacher, JPEG, "pc.jpg", "image/jpeg")
        self.assertEqual((png["media_type"], png["width"], png["height"]), ("image/png", 5, 3))
        self.assertEqual((jpeg["media_type"], jpeg["width"], jpeg["height"]), ("image/jpeg", 5, 3))

        saved = self.attach(png["id"]).json["data"]
        self.assertEqual(saved["content_revision"], 2)
        self.assertEqual(saved["images"][0]["resource_version_id"], png["id"])
        self.assertEqual(saved["images"][0]["version"], 1)
        self.assertTrue(saved["images"][0]["available"])
        self.assertNotIn("storage_key", saved["images"][0])

        listed = self.call(self.student, "GET", self.course + "/knowledge-points").json["data"][0]
        self.assertNotIn("images", listed)

        detail = self.call(self.student, "GET", self.detail).json["data"]
        self.assertEqual(detail["images"][0]["alt"], "程序计数器示意")
        self.assertNotIn("storage_key", detail["images"][0])
        image_id = detail["images"][0]["id"]
        event = str(uuid4())
        first = self.image_content(self.student, image_id, event)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data, PNG)
        again = self.image_content(self.student, image_id, event)
        self.assertEqual(again.data, PNG)
        self.assertEqual(self.image_count(), 1)

        # A new resource version does not drift an already-fixed knowledge image.
        v2 = self.add_version(png["resource_id"], JPEG, "pc-v2.jpg", "image/jpeg")
        detail = self.call(self.student, "GET", self.detail).json["data"]
        self.assertEqual(detail["images"][0]["resource_version_id"], png["id"])
        self.assertEqual(self.image_content(self.student, image_id, str(uuid4())).data, PNG)
        self.assertEqual(v2["media_type"], "image/jpeg")

        self.call(self.student, "POST", "/auth/logout", status=204)
        self.login(self.student, "T005STUD1")
        after = self.call(self.student, "GET", self.detail).json["data"]
        self.assertEqual(after["images"][0]["resource_version_id"], png["id"])

    def test_cross_course_non_image_spoof_and_strict_fields_fail_atomically(self):
        other = self.call(self.admin, "POST", "/courses", {
            "title": "Other image course",
            "teacher_id": self.call(self.teacher, "GET", "/auth/session").json["data"]["user"]["id"]},
            201).json["data"]["id"]
        foreign = self.teacher.open(
            f"/api/v1/courses/{other}/resources", method="POST",
            data={"file": (BytesIO(JPEG), "foreign.jpg", "image/jpeg"), "title": "Foreign image",
                  "kind": "guide"}, content_type="multipart/form-data",
            headers={"Origin": ORIGIN, "X-CSRF-Token": self.teacher.csrf})
        self.assertEqual(foreign.status_code, 201, foreign.json)
        foreign_version = foreign.json["data"]
        pdf = self.upload(self.teacher, b"%PDF-1.4\n%%EOF", "guide.pdf", "application/pdf")

        before = self.call(self.teacher, "GET", self.detail).json["data"]
        bad = [
            {"images": [{"resource_version_id": foreign_version["id"], "placement": "content"}]},
            {"images": [{"resource_version_id": pdf["id"], "placement": "content"}]},
            {"images": [{"resource_version_id": pdf["id"], "placement": "content", "src": "https://x"}]},
            {"images": [{"resource_version_id": pdf["id"], "placement": "content",
                         "resource_version_ids": [1]}]},
            {"images": ["https://invalid.example/a.png"]},
            {"images": [{"resource_version_id": pdf["id"], "placement": "content"}] * 21},
        ]
        for body in bad:
            self.call(self.teacher, "PATCH", self.detail, body, 400)
        self.assertEqual(self.call(self.teacher, "GET", self.detail).json["data"], before)

        for mime, name, content in (("image/png", "fake.png", b"not an image"),
                                   ("image/jpeg", "fake.jpg", PNG),
                                   ("image/png", "fake.jpg", JPEG)):
            response = self.teacher.post(
                "/api/v1" + self.course + "/resources",
                data={"file": (BytesIO(content), name, mime), "title": "spoof", "kind": "guide"},
                content_type="multipart/form-data",
                headers={"Origin": ORIGIN, "X-CSRF-Token": self.teacher.csrf})
            self.assertEqual(response.status_code, 415, response.json)

    def test_draft_visibility_archive_missing_file_and_revocation_fail_closed(self):
        image = self.upload(self.teacher, PNG, "safe.png", "image/png")
        self.attach(image["id"])
        image_id = self.call(self.student, "GET", self.detail).json["data"]["images"][0]["id"]
        draft = self.call(self.teacher, "POST", f"/chapters/{self.chapter_id}/knowledge-points", {
            "title": "draft image", "content": "草稿", "published": False,
            "images": [{"resource_version_id": image["id"], "placement": "content"}]}, 201).json["data"]
        self.call(self.student, "GET", f"/knowledge-points/{draft['id']}", status=404)
        self.assertEqual(self.image_content(self.student, draft["images"][0]["id"], str(uuid4())).status_code, 404)
        self.assertTrue(self.call(self.teacher, "GET", f"/knowledge-points/{draft['id']}").json["data"]["images"][0]["available"])

        self.call(self.teacher, "PATCH", f"/resources/{image['resource_id']}",
                  {"visibility": "teacher_only"})
        self.assertEqual(self.call(self.student, "GET", self.detail).json["data"]["images"], [])
        self.assertEqual(self.image_content(self.student, image_id, str(uuid4())).status_code, 404)
        self.assertTrue(self.call(self.teacher, "GET", self.detail).json["data"]["images"][0]["available"])
        self.call(self.teacher, "PATCH", f"/resources/{image['resource_id']}",
                  {"visibility": "students"})

        with closing(connect(self.path)) as db:
            db.execute("UPDATE resource SET archived=1 WHERE id=?", (image["resource_id"],))
        self.assertEqual(self.call(self.student, "GET", self.detail).json["data"]["images"], [])
        self.assertEqual(self.image_content(self.student, image_id, str(uuid4())).status_code, 404)
        self.assertFalse(self.call(self.teacher, "GET", self.detail).json["data"]["images"][0]["available"])
        # 已存在的不可用图片可随文字保存保留，不能被强制删除才能改标题。
        self.call(self.teacher, "PATCH", self.detail, {
            "title": "程序计数器（图不可用）",
            "images": [{"resource_version_id": image["id"], "placement": "content",
                        "alt": "程序计数器示意", "caption": "固定资源版本"}]})
        with closing(connect(self.path)) as db:
            db.execute("UPDATE resource SET archived=0 WHERE id=?", (image["resource_id"],))
            key = db.execute("SELECT storage_key FROM file_object WHERE id=(SELECT file_id "
                             "FROM resource_version WHERE id=?)", (image["id"],)).fetchone()[0]
        os.remove(os.path.join(self.app.config["UPLOAD_ROOT"], key))
        self.assertEqual(self.call(self.student, "GET", self.detail).json["data"]["images"], [])
        self.assertEqual(self.image_content(self.student, image_id, str(uuid4())).status_code, 404)
        self.call(self.teacher, "PATCH", self.detail, {
            "images": [{"resource_version_id": image["id"], "placement": "content",
                        "alt": "程序计数器示意", "caption": "固定资源版本"}]})

        self.call(self.teacher, "DELETE", self.course + f"/members/{self.student_id}", status=204)
        self.call(self.student, "GET", self.detail, status=404)

    def test_event_id_validation_and_unsafe_urls_never_reach_storage(self):
        image = self.upload(self.teacher, PNG, "safe.png", "image/png")
        self.attach(image["id"])
        image_id = self.call(self.student, "GET", self.detail).json["data"]["images"][0]["id"]
        self.assertEqual(self.image_content(self.student, image_id, "not-a-uuid").status_code, 400)
        self.assertEqual(self.image_count(), 0)
