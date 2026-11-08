"""Roster import checks: validation, idempotency, default passwords and demo accounts."""

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.shared.db import connect, migrate
from scripts.seed_rosters import RosterError, import_rosters

ORIGIN = "http://127.0.0.1:5173"
PASSWORD = "Long-test-password-42"


class RosterImportTest(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.database = self.folder / "app.db"
        migrate(self.database)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.database),
                               "SECRET_KEY": "test-secret-for-csrf"})
        self.client = self.app.test_client()

    def roster(self, name, text):
        path = self.folder / name
        path.write_text(text, encoding="utf-8")
        return path

    def count(self, sql, params=()):
        db = connect(self.database)
        try:
            return db.execute(sql, params).fetchone()[0]
        finally:
            db.close()

    def execute(self, sql, params=()):
        db = connect(self.database)
        try:
            db.execute(sql, params)
        finally:
            db.close()

    def login(self, number, password):
        return self.client.post("/api/v1/auth/login", json={"student_no": number, "password": password},
                                headers={"Origin": ORIGIN})

    def test_import_is_idempotent_and_default_password_logs_in(self):
        path = self.roster("class.csv", "班级,学号,姓名\n242017班,24209001,测试甲\n242017班,24209002,测试乙\n")
        first = import_rosters(self.database, [path], ensure_demo=False)
        self.assertEqual((first["created"], first["updated"], first["unchanged"]), (2, 0, 0))
        self.assertEqual(self.count("SELECT COUNT(*) FROM user WHERE role='student'"), 2)
        second = import_rosters(self.database, [path], ensure_demo=False)
        self.assertEqual((second["created"], second["updated"], second["unchanged"]), (0, 0, 2))
        self.assertEqual(self.count("SELECT COUNT(*) FROM user WHERE role='student'"), 2)
        self.assertEqual(self.count("SELECT COUNT(*) FROM user WHERE class_name='242017班'"), 2)
        self.assertEqual(self.login("24209001", "24209001").status_code, 200)
        self.assertEqual(self.login("24209001", "wrong-password").status_code, 401)

    def test_demo_student_and_teacher_accounts_are_ready_for_one_click_login(self):
        path = self.roster("class.csv", "student_no,name\n24209001,测试甲\n")
        result = import_rosters(self.database, [path])
        self.assertEqual(result["roster_students"], 1)
        self.assertTrue(result["demo_student"])
        self.assertEqual(result["demo_teacher"], "created")
        self.assertEqual(self.count("SELECT COUNT(*) FROM user WHERE role='student'"), 2)
        self.assertEqual(self.login("24200000", "24200000").status_code, 200)
        teacher = self.login("teacher", "teacher")
        self.assertEqual(teacher.status_code, 200, teacher.json)
        self.assertEqual(teacher.json["data"]["user"]["role"], "teacher")
        repeat = import_rosters(self.database, [path])
        self.assertEqual(repeat["demo_teacher"], "exists")
        self.assertEqual(self.count("SELECT COUNT(*) FROM user WHERE role='student'"), 2)

    def test_invalid_roster_is_rejected_before_any_insert(self):
        path = self.roster("class.csv", "学号,姓名\n24209001,测试甲\nshort,测试乙\n")
        with self.assertRaises(RosterError):
            import_rosters(self.database, [path], ensure_demo=False)
        self.assertEqual(self.count("SELECT COUNT(*) FROM user"), 0)

    def test_conflicting_names_for_same_student_are_rejected(self):
        first = self.roster("a.csv", "student_no,name\n24209001,测试甲\n")
        second = self.roster("b.csv", "student_no,name\n24209001,测试乙\n")
        with self.assertRaises(RosterError):
            import_rosters(self.database, [first, second], ensure_demo=False)

    def test_reset_password_scopes_cover_roster_and_existing_demo_students(self):
        path = self.roster("class.csv", "student_no,name\n24209001,测试甲\n")
        import_rosters(self.database, [path], ensure_demo=False)
        self.execute("UPDATE user SET password_hash=? WHERE student_no='24209001'",
                     (generate_password_hash(PASSWORD),))
        self.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                     "VALUES('24209009','旧演示学生',?,'student',1,?,?)",
                     (generate_password_hash(PASSWORD), datetime.now(UTC).isoformat(),
                      datetime.now(UTC).isoformat()))

        roster_only = import_rosters(self.database, [path], reset_passwords="roster", ensure_demo=False)
        self.assertEqual(roster_only["password_reset"], 1)
        self.assertEqual(self.login("24209001", "24209001").status_code, 200)
        self.assertEqual(self.login("24209009", PASSWORD).status_code, 200)

        all_students = import_rosters(self.database, [path], reset_passwords="all", ensure_demo=False)
        self.assertEqual(all_students["password_reset"], 2)
        self.assertEqual(self.login("24209009", "24209009").status_code, 200)
        self.assertEqual(self.login("24209009", PASSWORD).status_code, 401)
