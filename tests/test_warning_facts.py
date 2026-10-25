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
            # submission/grading_run 由 SPEC-018 迁移提供真实表，直接插入。
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
            db.execute("INSERT INTO practice_attempt(id,student_id,question_version_id,answer_json,answered,"
                       "correct,score_hundredths,created_at) VALUES(5,1,1,'null',0,0,0,?)", (AT,))
            for task_id, status in ((1, "late"), (2, "absent")):
                db.execute("INSERT INTO attendance_task(id,course_id,title,start_at,late_at,end_at,"
                           "code_hash,code_expires_at,status,created_at,updated_at) "
                           "VALUES(?,1,'Lab',?,?,?,'x',?,'closed',?,?)",
                           (task_id, START, START, AT, AT, AT, AT))
                db.execute("INSERT INTO attendance_participant VALUES(?,1)", (task_id,))
                db.execute("INSERT INTO attendance_record(task_id,student_id,status,source,created_at,updated_at) "
                           "VALUES(?,1,?,'close',?,?)", (task_id, status, AT, AT))
            # SPEC-009 owns experiment definitions; SPEC-017 owns wiring attempts.
            db.execute("INSERT INTO experiment(id,course_id,code,title,created_at,updated_at) "
                       "VALUES(1,1,'EXP-01','fixture',?,?)", (AT, AT))
            db.execute("INSERT INTO experiment_version(id,experiment_id,version,title,objectives,instructions,"
                       "submission_modes_json,status,published_at,start_at,end_at,definition_sha256,"
                       "created_at,updated_at) "
                       "VALUES(1,1,1,'fixture','o','i','[\"wiring\",\"circuit\"]','published',?,?,?,'x',?,?)",
                       (AT, START, AT, AT, AT))
            db.execute("INSERT INTO experiment_participant VALUES(1,1)")
            db.execute("INSERT INTO wiring_attempt(experiment_version_id,student_id,status,completed,submitted_at,"
                       "state_json,created_at,updated_at) VALUES(1,1,'submitted',1,?,'{}',?,?)", (AT, AT, AT))
            # SPEC-018 拥有 submission/grading_run；按真实表结构插入验收数据。
            db.execute("INSERT INTO file_object(id,owner_id,storage_key,original_name,media_type,"
                       "size_bytes,sha256,purpose,created_at) VALUES(1,2,'k','f.circ','application/xml',"
                       "10,'x','grading_submission',?)", (AT,))
            db.execute("INSERT INTO submission(id,experiment_version_id,student_id,file_id,file_sha256,"
                       "size_bytes,filename,created_at) VALUES(1,1,1,1,'x',10,'f.circ',?)", (AT,))
            db.execute("INSERT INTO test_suite(id,experiment_version_id,version,status,content_sha256,"
                       "scoring_groups_json,created_at) VALUES(1,1,1,'published','x','{}',?)", (AT,))
            db.execute("INSERT INTO grading_run(id,submission_id,suite_id,engine_version,jar_sha256,status,"
                       "score_hundredths,passed_count,executed_count,total_count,finished_at,"
                       "profile_snapshot_json,profile_sha256,suite_sha256,created_at) "
                       "VALUES(1,1,1,'fixture',NULL,'accepted',10000,1,1,1,?,'{}','x','x',?)", (AT, AT))
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
