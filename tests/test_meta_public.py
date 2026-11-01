"""SPEC-019: /help and /who are public, machine-readable and self-maintaining."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import TestCase

from backend.app import create_app
from backend.shared.db import migrate


class MetaPublicTest(TestCase):
    def setUp(self):
        with NamedTemporaryFile(dir=Path(__file__).parent, delete=False) as temporary:
            self.path = Path(temporary.name)
        migrate(self.path)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.path),
                               "SECRET_KEY": "test-secret-for-csrf"})
        self.client = self.app.test_client()

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_who_reports_group_without_login(self):
        response = self.client.get("/who")
        self.assertEqual(response.status_code, 200)
        data = response.json["data"]
        self.assertEqual(data["class_name"], "242017班")
        self.assertEqual(data["group_no"], "g24201710")
        self.assertEqual(data["leader"]["student_no"], "24201718")
        self.assertEqual(data["member_count"], 4)
        self.assertEqual(data["student_nos"],
                         ["24201718", "24201716", "24201723", "24201737"])

    def test_who_keeps_leader_consistent_with_members(self):
        data = self.client.get("/who").json["data"]
        leaders = [member for member in data["members"] if member["role"] == "组长"]
        self.assertEqual(len(leaders), 1)
        self.assertEqual(leaders[0]["student_no"], data["leader"]["student_no"])
        self.assertEqual(leaders[0]["name"], data["leader"]["name"])
        self.assertEqual(data["members"][0]["student_no"], data["leader"]["student_no"])

    def test_help_exposes_endpoint_inventory(self):
        response = self.client.get("/help")
        self.assertEqual(response.status_code, 200)
        data = response.json["data"]
        self.assertIn("/help", data["public_endpoints"])
        self.assertIn("/who", data["public_endpoints"])
        paths = {endpoint["path"]
                 for module in data["modules"] for endpoint in module["endpoints"]}
        self.assertIn("/api/v1/courses/{course_id}/attendance-tasks", paths)
        self.assertIn("/api/v1/attendance-tasks/{task_id}/check-ins", paths)
        self.assertIn("/api/v1/attendance-tasks/{task_id}/rotate-code", paths)
        self.assertIn("/api/v1/auth/login", paths)
        self.assertEqual(data["counts"]["endpoints"],
                         sum(len(module["endpoints"]) for module in data["modules"]))

    def test_help_documents_the_check_in_flow(self):
        data = self.client.get("/help").json["data"]
        names = [guide["name"] for guide in data["guides"]]
        self.assertIn("登录与 CSRF", names)
        self.assertIn("课堂点到（互测主流程）", names)
        flow = next(guide for guide in data["guides"] if guide["name"] == "课堂点到（互测主流程）")
        joined = " ".join(flow["points"])
        self.assertIn("check-ins", joined)
        self.assertIn("rotate-code", joined)
        self.assertIn("counts{present,late,leave,absent}", joined)
        self.assertEqual(data["accounts"]["teacher"], "teacher/teacher（学号输入 teacher，密码 teacher）")

    def test_declared_public_endpoints_open_without_cookie(self):
        for path in ("/help", "/who", "/api/v1/modules"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
