"""Check the SPEC-014 adapter against the DBD table contract."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import TestCase

from backend.apis.warnings import analyze, read_facts
from backend.shared.db import connect, migrate

AT = "2026-10-13T08:00:00.000Z"
START = "2026-10-01T00:00:00.000Z"
END = "2026-10-20T00:00:00.000Z"


class WarningFactsTest(TestCase):
    def test_real_fact_joins_and_required_modes(self):
        with NamedTemporaryFile(dir=Path(__file__).parent, delete=False) as temporary:
            path = Path(temporary.name)
        db = None
        try:
            migrate(path)
            db = connect(path)
            db.executescript("""
                CREATE TABLE experiment(id INTEGER PRIMARY KEY,course_id INTEGER);
                CREATE TABLE experiment_version(id INTEGER PRIMARY KEY,experiment_id INTEGER,
                    submission_modes_json TEXT,status TEXT,end_at TEXT);
                CREATE TABLE experiment_participant(experiment_version_id INTEGER,student_id INTEGER);
                CREATE TABLE wiring_attempt(experiment_version_id INTEGER,student_id INTEGER,
                    status TEXT,completed INTEGER,submitted_at TEXT);
                CREATE TABLE submission(id INTEGER PRIMARY KEY,experiment_version_id INTEGER,
                    student_id INTEGER,created_at TEXT);
                CREATE TABLE grading_run(id INTEGER PRIMARY KEY,submission_id INTEGER,status TEXT,finished_at TEXT);
            """)
            db.execute("INSERT INTO user(id,student_no,name,password_hash,role,created_at,updated_at) "
                       "VALUES(1,'STUDENT01','S','x','student',?,?)", (AT, AT))
            db.execute("INSERT INTO user(id,student_no,name,password_hash,role,created_at,updated_at) "
                       "VALUES(2,'TEACH0001','T','x','teacher',?,?)", (AT, AT))
            db.execute("INSERT INTO course(id,title,teacher_id,created_at,updated_at) VALUES(1,'CPU',2,?,?)", (AT, AT))
            db.execute("INSERT INTO course_member(course_id,user_id,member_role,created_at,updated_at) "
                       "VALUES(1,1,'student',?,?)", (AT, AT))
            # SPEC-006 now owns these tables; keep other missing modules as fixtures.
            db.execute("INSERT INTO question(id,course_id) VALUES(1,1)")
            db.execute("INSERT INTO question_version(id,question_id,version,type,stem,options_json,answer_json,difficulty,practice_available) "
                       "VALUES(1,1,1,'single','fixture','[]','\"A\"','easy',1)")
            db.execute("INSERT INTO paper(id,course_id,title,kind,confidential) VALUES(1,1,'fixture','homework',0)")
            db.execute("INSERT INTO paper_item VALUES(1,1,1,1,1000)")
            db.execute("INSERT INTO paper_participant VALUES(1,1)")
            db.execute("UPDATE paper SET status='published',start_at=?,end_at=?,review_at=? WHERE id=1",
                       (START, END, END))
            db.execute("INSERT INTO attempt(id,paper_id,student_id,status,score_hundredths,partial_score_hundredths,submitted_at) "
                       "VALUES(1,1,1,'graded',0,0,?)", (AT,))
            db.execute("INSERT INTO answer(id,attempt_id,question_version_id,value_json,score_hundredths,answered) "
                       "VALUES(1,1,1,'\"B\"',0,1)")
            for identifier, correct in enumerate((0, 0, 1, 0), 1):
                db.execute("INSERT INTO practice_attempt(id,student_id,question_version_id,answer_json,answered,"
                           "correct,score_hundredths,created_at) VALUES(?,1,1,?,1,?,?,?)",
                           (identifier, '"A"' if correct else '"B"', correct, correct*10000, AT))
            for task_id, status in ((1, "late"), (2, "absent")):
                db.execute("INSERT INTO attendance_task(id,course_id,title,start_at,late_at,end_at,"
                           "code_hash,code_expires_at,status,created_at,updated_at) "
                           "VALUES(?,1,'Lab',?,?,?,'x',?,'closed',?,?)",
                           (task_id, START, START, AT, AT, AT, AT))
                db.execute("INSERT INTO attendance_participant VALUES(?,1)", (task_id,))
                db.execute("INSERT INTO attendance_record(task_id,student_id,status,source,created_at,updated_at) "
                           "VALUES(?,1,?,'close',?,?)", (task_id, status, AT, AT))
            db.execute("INSERT INTO experiment VALUES(1,1)")
            db.execute("INSERT INTO experiment_version VALUES(1,1,'[\"wiring\",\"circuit\"]','published',?)", (AT,))
            db.execute("INSERT INTO experiment_participant VALUES(1,1)")
            db.execute("INSERT INTO wiring_attempt VALUES(1,1,'submitted',1,?)", (AT,))
            db.execute("INSERT INTO submission VALUES(1,1,1,?)", (AT,))
            db.execute("INSERT INTO grading_run VALUES(1,1,'accepted',?)", (AT,))
            facts = read_facts(db, 1, START, END, END)
            self.assertEqual(facts[0]["answers"], 5)
            self.assertEqual(facts[0]["correct"], 1)
            self.assertEqual(facts[0]["due"], 1)
            self.assertEqual(facts[0]["completed"], 1)
            self.assertEqual(facts[0]["last_two"], ["late", "absent"])
            self.assertEqual(len(analyze(facts)["warnings"][0]["reasons"]), 2)
        finally:
            if db:
                db.close()
            path.unlink(missing_ok=True)
