"""Exercise the public identity and attendance flow, including access revocation."""

from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import TestCase
from unittest.mock import patch

import cv2
import numpy as np
from werkzeug.security import generate_password_hash

from backend.apis.recognition import gate_mask
from backend.app import create_app
from backend.shared.db import connect, migrate

ORIGIN = "http://127.0.0.1:5173"
PASSWORD = "Long-test-password-42"


class FlowTest(TestCase):
    def setUp(self):
        with NamedTemporaryFile(dir=Path(__file__).parent, delete=False) as temporary:
            self.path = Path(temporary.name)
        migrate(self.path)
        self.at = datetime(2026, 10, 13, 8, tzinfo=UTC)
        self.app = create_app({"TESTING": True, "DATABASE_PATH": str(self.path),
                               "SECRET_KEY": "test-secret-for-csrf", "TEST_NOW": self.at})
        self.admin = self.app.test_client()
        self.teacher = self.app.test_client()
        self.student = self.app.test_client()
        self.other = self.app.test_client()
        db = connect(self.path)
        try:
            for number, name, role in (("ADMIN0001", "Admin", "admin"),
                                       ("TEACH0001", "Teacher", "teacher")):
                db.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                           "VALUES(?,?,?,?,1,?,?)", (number, name, generate_password_hash(PASSWORD), role,
                                                       self.at.isoformat(), self.at.isoformat()))
        finally:
            db.close()
        self.auth(self.admin, "ADMIN0001")
        self.auth(self.teacher, "TEACH0001")

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def call(self, client, method, path, data=None):
        headers = {"Origin": ORIGIN, "X-CSRF-Token": getattr(client, "csrf", "")}
        return client.open(path, method=method, json=data, headers=headers)

    def auth(self, client, number):
        response = self.call(client, "POST", "/api/v1/auth/login",
                             {"student_no": number, "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.json)
        client.csrf = response.json["data"]["csrf_token"]

    def register(self, client, number):
        response = self.call(client, "POST", "/api/v1/auth/register",
                             {"student_no": number, "name": number, "password": PASSWORD})
        self.assertEqual(response.status_code, 201, response.json)
        self.auth(client, number)
        return response.json["data"]["user"]["id"]

    def advance(self, minutes):
        self.at += timedelta(minutes=minutes)
        self.app.config["TEST_NOW"] = self.at

    def test_identity_attendance_and_frozen_participants(self):
        student_id = self.register(self.student, "STUDENT01")
        other_id = self.register(self.other, "STUDENT02")
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        created = self.call(self.admin, "POST", "/api/v1/courses",
                            {"title": "CPU", "teacher_id": teacher_id})
        self.assertEqual(created.status_code, 201, created.json)
        course_id = created.json["data"]["id"]
        self.assertEqual(self.call(self.student, "POST", f"/api/v1/courses/{course_id}/attendance-tasks",
                                   {"title": "X", "start_at": self.at.isoformat(),
                                    "late_at": self.at.isoformat(),
                                    "end_at": (self.at + timedelta(minutes=1)).isoformat()}).status_code, 404)
        self.assertEqual(self.call(self.teacher, "POST", f"/api/v1/courses/{course_id}/members",
                                   {"user_id": student_id, "member_role": "student"}).status_code, 201)
        start = self.at - timedelta(minutes=1)
        late = self.at + timedelta(minutes=5)
        end = self.at + timedelta(minutes=30)
        task = self.call(self.teacher, "POST", f"/api/v1/courses/{course_id}/attendance-tasks",
                         {"title": "CPU lab", "start_at": start.isoformat(),
                          "late_at": late.isoformat(), "end_at": end.isoformat()})
        self.assertEqual(task.status_code, 201, task.json)
        task_id, old_code = task.json["data"]["id"], task.json["data"]["code"]
        self.assertNotIn('"code":', self.teacher.get(f"/api/v1/courses/{course_id}/attendance-tasks").get_data(as_text=True))
        self.assertEqual(self.call(self.teacher, "POST", f"/api/v1/courses/{course_id}/members",
                                   {"user_id": other_id, "member_role": "student"}).status_code, 201)
        self.assertEqual(self.call(self.other, "POST", f"/api/v1/attendance-tasks/{task_id}/check-ins",
                                   {"code": old_code}).status_code, 404)
        rotated = self.call(self.teacher, "POST", f"/api/v1/attendance-tasks/{task_id}/rotate-code", {})
        self.assertEqual(rotated.status_code, 200, rotated.json)
        new_code = rotated.json["data"]["code"]
        self.assertNotEqual(old_code, new_code)
        self.assertEqual(self.call(self.student, "POST", f"/api/v1/attendance-tasks/{task_id}/check-ins",
                                   {"code": old_code}).status_code, 422)
        first = self.call(self.student, "POST", f"/api/v1/attendance-tasks/{task_id}/check-ins",
                          {"code": new_code})
        self.assertEqual(first.status_code, 201, first.json)
        second = self.call(self.student, "POST", f"/api/v1/attendance-tasks/{task_id}/check-ins",
                           {"code": new_code})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json["data"]["id"], second.json["data"]["id"])
        closed = self.call(self.teacher, "POST", f"/api/v1/attendance-tasks/{task_id}/close", {})
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.json["data"]["counts"]["present"], 1)
        self.assertEqual(closed.json["data"]["counts"]["absent"], 0)
        self.assertEqual(self.call(self.admin, "PATCH", f"/api/v1/users/{student_id}",
                                   {"active": False}).status_code, 200)
        self.assertEqual(self.student.get("/api/v1/auth/session").status_code, 401)

    def test_last_admin_cannot_be_deactivated(self):
        admin_id = self.admin.get("/api/v1/auth/session").json["data"]["user"]["id"]
        response = self.call(self.admin, "PATCH", f"/api/v1/users/{admin_id}", {"active": False})
        self.assertEqual(response.status_code, 409)

    def test_uc01_leave_rejection_resubmission_close_and_correction(self):
        students = [self.student, self.other, self.app.test_client()]
        student_ids = [self.register(client, f"STUDENT0{index}")
                       for index, client in enumerate(students, 1)]
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        course_id = self.call(self.admin, "POST", "/api/v1/courses",
                              {"title": "CPU", "teacher_id": teacher_id}).json["data"]["id"]
        for student_id in student_ids:
            self.assertEqual(self.call(self.teacher, "POST", f"/api/v1/courses/{course_id}/members",
                                       {"user_id": student_id, "member_role": "student"}).status_code, 201)
        with patch("backend.apis.attendance.secrets.randbelow", return_value=12345):
            created = self.call(self.teacher, "POST", f"/api/v1/courses/{course_id}/attendance-tasks",
                                {"title": "Lab", "start_at": self.at.isoformat(),
                                 "late_at": (self.at + timedelta(minutes=10)).isoformat(),
                                 "end_at": (self.at + timedelta(minutes=30)).isoformat()})
        self.assertEqual(created.status_code, 201, created.json)
        task_id = created.json["data"]["id"]
        self.assertEqual(created.json["data"]["code"], "012345")
        self.assertNotIn("code", self.teacher.get(
            f"/api/v1/courses/{course_id}/attendance-tasks").json["data"][0])
        self.advance(5)
        first = self.call(students[0], "POST", f"/api/v1/attendance-tasks/{task_id}/check-ins",
                          {"code": "012345"})
        self.assertEqual(first.status_code, 201, first.json)
        self.assertEqual(self.call(students[0], "POST", f"/api/v1/attendance-tasks/{task_id}/check-ins",
                                   {"code": "012345"}).json["data"]["id"], first.json["data"]["id"])
        leave = self.call(students[1], "POST", f"/api/v1/attendance-tasks/{task_id}/leave-requests",
                          {"reason": "ill"})
        self.assertEqual(leave.status_code, 201, leave.json)
        leave_id = leave.json["data"]["id"]
        self.assertEqual(self.call(students[0], "PATCH", f"/api/v1/leave-requests/{leave_id}",
                                   {"status": "approved", "note": "not allowed"}).status_code, 403)
        self.assertEqual(self.call(self.teacher, "PATCH", f"/api/v1/leave-requests/{leave_id}",
                                   {"status": "rejected", "note": "need detail"}).status_code, 200)
        self.assertEqual(self.call(students[1], "PUT", f"/api/v1/leave-requests/{leave_id}",
                                   {"reason": "medical leave"}).status_code, 200)
        self.assertEqual(self.call(self.teacher, "PATCH", f"/api/v1/leave-requests/{leave_id}",
                                   {"status": "approved", "note": "verified"}).status_code, 200)
        self.assertEqual(self.call(students[1], "POST", f"/api/v1/attendance-tasks/{task_id}/check-ins",
                                   {"code": "012345"}).json["data"]["status"], "leave")
        closed = self.call(self.teacher, "POST", f"/api/v1/attendance-tasks/{task_id}/close", {})
        self.assertEqual(closed.json["data"]["counts"],
                         {"present": 1, "late": 0, "leave": 1, "absent": 1})
        self.assertEqual(self.call(students[0], "POST", f"/api/v1/attendance-tasks/{task_id}/check-ins",
                                   {"code": "012345"}).json["data"]["id"], first.json["data"]["id"])
        self.assertEqual(self.call(students[2], "POST", f"/api/v1/attendance-tasks/{task_id}/check-ins",
                                   {"code": "012345"}).status_code, 409)
        records = self.teacher.get(f"/api/v1/courses/{course_id}/attendance-records").json["data"]
        self.assertEqual(len(records), 3)
        self.assertEqual({row["status"] for row in records}, {"present", "leave", "absent"})
        corrected = self.call(self.teacher, "PATCH", f"/api/v1/leave-requests/{leave_id}",
                              {"status": "rejected", "note": "correction", "restore_status": "absent"})
        self.assertEqual(corrected.status_code, 200, corrected.json)
        db = connect(self.path)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM leave_review_event WHERE leave_id=?",
                                        (leave_id,)).fetchone()[0], 4)
            self.assertEqual(db.execute("SELECT status FROM attendance_record WHERE task_id=? AND student_id=?",
                                        (task_id, student_ids[1])).fetchone()[0], "absent")
            self.assertTrue(db.execute("SELECT 1 FROM audit_event WHERE action='leave.review' ").fetchone())
            self.assertTrue(db.execute("SELECT 1 FROM notification WHERE user_id=? AND target_type='leave_request'",
                                       (student_ids[1],)).fetchone())
        finally:
            db.close()

    def test_warning_run_is_atomic_idempotent_and_teacher_only(self):
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        course_id = self.call(self.admin, "POST", "/api/v1/courses",
                              {"title": "CPU", "teacher_id": teacher_id}).json["data"]["id"]
        facts = [{"student_id": 2, "answers": 6, "correct": 2, "due": 0, "completed": 0,
                  "expected": 2, "attended": 0, "last_two": ["late", "absent"]}]
        with patch("backend.apis.warnings.read_facts", return_value=facts) as reader:
            headers = {"Origin": ORIGIN, "X-CSRF-Token": self.teacher.csrf, "Idempotency-Key": "run-1"}
            first = self.teacher.post(f"/api/v1/courses/{course_id}/warning-runs", headers=headers)
            self.assertEqual(first.status_code, 201, first.json)
            self.assertEqual(first.json["data"]["warning_count"], 1)
            repeat = self.teacher.post(f"/api/v1/courses/{course_id}/warning-runs", headers=headers)
            self.assertEqual(repeat.status_code, 201, repeat.json)
            self.assertEqual(repeat.json["data"]["analysis_run_id"], first.json["data"]["analysis_run_id"])
            self.assertEqual(reader.call_count, 1)
        listed = self.teacher.get(f"/api/v1/courses/{course_id}/warnings").json["data"]
        self.assertEqual(len(listed), 1)
        warning_id = listed[0]["id"]
        self.assertEqual(self.call(self.admin, "PATCH", f"/api/v1/warnings/{warning_id}",
                                   {"status": "handled", "note": "contacted"}).status_code, 404)
        handled = self.call(self.teacher, "PATCH", f"/api/v1/warnings/{warning_id}",
                            {"status": "handled", "note": "contacted"})
        self.assertEqual(handled.status_code, 200, handled.json)

    def test_recognition_confirmation_cannot_change_grades(self):
        student_id = self.register(self.student, "STUDENT01")
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        course_id = self.call(self.admin, "POST", "/api/v1/courses",
                              {"title": "CPU", "teacher_id": teacher_id}).json["data"]["id"]
        self.call(self.teacher, "POST", f"/api/v1/courses/{course_id}/members",
                  {"user_id": student_id, "member_role": "student"})
        self.app.config["UPLOAD_ROOT"] = str(self.path.parent / (self.path.name + "-uploads"))
        image = np.full((240, 640), 255, np.uint8)
        image[60:180, 80:240] = 255 - cv2.resize(gate_mask("AND"), (160, 120),
                                                  interpolation=cv2.INTER_NEAREST)
        png = cv2.imencode(".png", image)[1].tobytes()
        created = self.student.post(f"/api/v1/courses/{course_id}/recognitions",
                                    headers={"Origin": ORIGIN, "X-CSRF-Token": self.student.csrf},
                                    data={"image": (BytesIO(png), "diagram.png")})
        self.assertEqual(created.status_code, 201, created.json)
        recognition_id = created.json["data"]["id"]
        unchanged = self.call(self.student, "POST", f"/api/v1/recognitions/{recognition_id}/confirm",
                              {"items": [{"symbol": "AND", "bbox": created.json["data"]["items"][0]["bbox"]}]})
        self.assertEqual(unchanged.status_code, 400)
        self.assertEqual(self.call(self.teacher, "POST", f"/api/v1/recognitions/{recognition_id}/confirm",
                                   {"items": []}).status_code, 404)
        invalid = self.call(self.student, "POST", f"/api/v1/recognitions/{recognition_id}/confirm",
                            {"items": [{"symbol": "AND", "bbox": [0, 0, 900, 100]}]})
        self.assertEqual(invalid.status_code, 400)
        added = self.call(self.student, "POST", f"/api/v1/recognitions/{recognition_id}/confirm",
                          {"items": [{"symbol": "AND", "bbox": [80, 60, 160, 120], "label": "A"}] * 2})
        self.assertEqual(added.status_code, 400)
        confirmed = self.call(self.student, "POST", f"/api/v1/recognitions/{recognition_id}/confirm",
                              {"items": [{"symbol": "AND", "bbox": [80, 60, 160, 120], "label": "A"}]})
        self.assertEqual(confirmed.status_code, 200, confirmed.json)
        self.assertEqual(self.call(self.student, "POST", f"/api/v1/recognitions/{recognition_id}/confirm",
                                   {"items": []}).status_code, 409)
        db = connect(self.path)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM recognition WHERE status='confirmed'").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM analysis_run").fetchone()[0], 0)
        finally:
            db.close()
        upload = Path(self.app.config["UPLOAD_ROOT"])
        for file in upload.iterdir():
            file.unlink()
        upload.rmdir()

    def test_analytics_export_keeps_original_snapshot_after_correction(self):
        student_id = self.register(self.student, "STUDENT01")
        teacher_id = self.teacher.get("/api/v1/auth/session").json["data"]["user"]["id"]
        course_id = self.call(self.admin, "POST", "/api/v1/courses",
                              {"title": "CPU", "teacher_id": teacher_id}).json["data"]["id"]
        self.call(self.teacher, "POST", f"/api/v1/courses/{course_id}/members",
                  {"user_id": student_id, "member_role": "student"})
        beginning = (self.at - timedelta(minutes=2)).isoformat()
        ending = (self.at + timedelta(minutes=2)).isoformat()
        task = self.call(self.teacher, "POST", f"/api/v1/courses/{course_id}/attendance-tasks",
                         {"title": "Lab", "start_at": beginning,
                          "late_at": (self.at + timedelta(minutes=1)).isoformat(),
                          "end_at": (self.at + timedelta(minutes=2)).isoformat()}).json["data"]
        record = self.call(self.student, "POST", f"/api/v1/attendance-tasks/{task['id']}/check-ins",
                           {"code": task["code"]}).json["data"]
        self.call(self.teacher, "POST", f"/api/v1/attendance-tasks/{task['id']}/close", {})
        db = connect(self.path)
        try:
            # Assessment tables are owned by SPEC-006; retain this analytics fact setup.
            db.execute("INSERT INTO question(id,course_id) VALUES(1,?)", (course_id,))
            db.execute("INSERT INTO question_version(id,question_id,version,type,stem,options_json,answer_json,difficulty) "
                       "VALUES(1,1,1,'boolean','fixture','[]','true','easy')")
            db.execute("INSERT INTO paper(id,course_id,title,kind,confidential) VALUES(1,?,'fixture','quiz',0)", (course_id,))
            db.execute("INSERT INTO paper_item VALUES(1,1,1,1,5000)")
            db.execute("INSERT INTO paper_participant VALUES(1,?)", (student_id,))
            db.execute("UPDATE paper SET status='published',start_at=?,end_at=?,review_at=? WHERE id=1",
                       (beginning, ending, ending))
            db.execute("INSERT INTO attempt(id,paper_id,student_id,status,score_hundredths,partial_score_hundredths,submitted_at) "
                       "VALUES(1,1,?,'graded',2500,2500,?)", (student_id, beginning))
        finally:
            db.close()
        endpoint = f"/api/v1/courses/{course_id}/analytics?dimension=attendance&performance_paper_ids=1"
        first = self.teacher.get(endpoint)
        self.assertEqual(first.status_code, 200, first.json)
        run_id = first.json["data"]["analysis_run_id"]
        self.assertEqual(first.json["data"]["metrics"]["attendance_rate"], 1)
        self.assertEqual(first.json["data"]["metrics"]["performance_mean_percentage"], 50)
        student = self.student.get(f"/api/v1/courses/{course_id}/analytics?dimension=attendance")
        self.assertEqual(student.status_code, 200, student.json)
        self.assertIsNone(student.json["data"]["metrics"]["candidate_count"])
        self.assertEqual(student.json["data"]["metrics"]["correlation_reason"], "personal_scope")
        corrected = self.call(self.teacher, "PATCH", f"/api/v1/attendance-records/{record['id']}",
                              {"status": "absent", "reason": "paper roll correction"})
        self.assertEqual(corrected.status_code, 200, corrected.json)
        old = self.teacher.get(f"/api/v1/courses/{course_id}/analytics?analysis_run_id={run_id}")
        self.assertEqual(old.json["data"]["metrics"]["attendance_rate"], 1)
        export = self.teacher.get(f"/api/v1/courses/{course_id}/analytics/export?analysis_run_id={run_id}&format=csv")
        self.assertEqual(export.status_code, 200)
        self.assertIn(f"analysis_run_id,{run_id}", export.get_data(as_text=True))
        self.assertIn(",1.0,", export.get_data(as_text=True))
        current = self.teacher.get(endpoint)
        self.assertEqual(current.json["data"]["metrics"]["attendance_rate"], 0)
