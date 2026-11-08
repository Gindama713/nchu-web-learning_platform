"""021 迁移必须保留 020 已排好的座位，而不是直接丢掉。"""

from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import TestCase

from backend.shared.db import connect, migrate


class LegacySeatMigrationTest(TestCase):
    def setUp(self):
        with NamedTemporaryFile(dir=Path(__file__).parent, delete=False) as temporary:
            self.path = Path(temporary.name)
        migrate(self.path)
        self.at = "2026-11-08T08:00:00Z"

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_021_carries_legacy_seats_and_derives_class_name(self):
        db = connect(self.path)
        try:
            teacher = db.execute(
                "INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                "VALUES('TEACH0001','Teacher','x','teacher',1,?,?)", (self.at, self.at)).lastrowid
            course = db.execute(
                "INSERT INTO course(title,teacher_id,created_at,updated_at) VALUES('CPU',?,?,?)",
                (teacher, self.at, self.at)).lastrowid
            students = []
            for number, name, class_name in (
                    ("24201701", "A", "242017班"),
                    ("24201801", "B", "242018班"),
                    ("24201901", "C", None)):
                students.append(db.execute(
                    "INSERT INTO user(student_no,name,password_hash,role,class_name,active,created_at,updated_at) "
                    "VALUES(?,?,'x','student',?,1,?,?)", (number, name, class_name, self.at, self.at)).lastrowid)

            # 还原 020 的旧表形状，再让 021 从未应用状态重跑。
            db.execute("DROP TABLE class_seat")
            db.execute(
                "CREATE TABLE class_seat (id INTEGER PRIMARY KEY, "
                "course_id INTEGER NOT NULL REFERENCES course(id), "
                "student_id INTEGER NOT NULL REFERENCES user(id), "
                "group_no INTEGER NOT NULL CHECK(group_no BETWEEN 1 AND 12), "
                "seat_no INTEGER NOT NULL CHECK(seat_no BETWEEN 1 AND 20), "
                "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
                "UNIQUE(course_id, student_id))")
            db.execute("CREATE UNIQUE INDEX class_seat_position ON class_seat(course_id, group_no, seat_no)")
            for seat, student in enumerate(students, start=1):
                db.execute(
                    "INSERT INTO class_seat(id,course_id,student_id,group_no,seat_no,created_at,updated_at) "
                    "VALUES(?,?,?,1,?,?,?)", (10 + seat, course, student, seat, self.at, self.at))
            db.execute("DELETE FROM schema_migration WHERE version='021_week10_seat_class'")
        finally:
            db.close()

        migrate(self.path)

        db = connect(self.path)
        try:
            rows = db.execute(
                "SELECT id,student_id,class_name,group_no,seat_no FROM class_seat ORDER BY id").fetchall()
        finally:
            db.close()
        self.assertEqual([tuple(row) for row in rows], [
            (11, students[0], "242017班", 1, 1),
            (12, students[1], "242018班", 1, 2),
            (13, students[2], "未分班", 1, 3),
        ])
