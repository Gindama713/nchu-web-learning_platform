"""SPEC-002 attendance with frozen participants and one-use code responses."""

import hashlib
import hmac
import re
import secrets

from flask import Blueprint, current_app, make_response, request

from backend.shared.api import (
    ApiError,
    audit,
    body,
    notify,
    page_args,
    paged,
    parse_time,
    positive_int,
    rate_limit,
    result,
    stamp,
    text_field,
)
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db, write

bp = Blueprint("attendance", __name__)


def task_json(row):
    return {key: row[key] for key in
            ("id", "course_id", "title", "start_at", "late_at", "end_at", "status", "code_expires_at")}


def record_json(row):
    return {key: row[key] for key in ("id", "task_id", "student_id", "status", "checked_at", "source")}


def leave_json(row):
    return {key: row[key] for key in
            ("id", "task_id", "student_id", "reason", "status", "reviewer_id", "review_note", "reviewed_at")}


def task_for_user(task_id, teacher=False):
    task = get_db().execute("SELECT * FROM attendance_task WHERE id=?", (task_id,)).fetchone()
    if not task:
        raise ApiError(404, "NOT_FOUND", "Attendance task not found")
    course_access(task["course_id"], teacher=teacher)
    return task


def code_hash(code):
    return hmac.new(current_app.config["SECRET_KEY"].encode(), code.encode(), hashlib.sha256).hexdigest()


def new_code(previous=None):
    for _ in range(10):
        code = f"{secrets.randbelow(1_000_000):06d}"
        if code_hash(code) != previous:
            return code
    raise ApiError(503, "MAINTENANCE", "Could not rotate attendance code")


def one_time(data, status=200):
    response = make_response(result(data, status)[0], status)
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.post("/courses/<int:course_id>/attendance-tasks")
def create_task(course_id):
    data = body(("title", "start_at", "late_at", "end_at"))
    title = text_field(data["title"], "title")
    start, late, end = (parse_time(data[key], key) for key in ("start_at", "late_at", "end_at"))
    if not start <= late <= end or start == end:
        raise ApiError(400, "VALIDATION_ERROR", "Expected start_at <= late_at <= end_at and start_at < end_at")
    with write() as db:
        course_access(course_id, teacher=True)
        students = db.execute("SELECT m.user_id FROM course_member m JOIN user u ON u.id=m.user_id "
                              "WHERE m.course_id=? AND m.member_role='student' AND m.active=1 "
                              "AND u.role='student' AND u.active=1 ORDER BY m.user_id", (course_id,)).fetchall()
        if not students:
            raise ApiError(422, "EMPTY_PARTICIPANTS", "Course has no active students")
        code, timestamp = new_code(), stamp()
        cursor = db.execute("INSERT INTO attendance_task(course_id,title,start_at,late_at,end_at,"
                            "code_hash,code_expires_at,status,created_at,updated_at) "
                            "VALUES(?,?,?,?,?, ?,?,'open',?,?)",
                            (course_id, title, stamp(start), stamp(late), stamp(end),
                             code_hash(code), stamp(end), timestamp, timestamp))
        task_id = cursor.lastrowid
        db.executemany("INSERT INTO attendance_participant(task_id,student_id) VALUES(?,?)",
                       [(task_id, row["user_id"]) for row in students])
        for row in students:
            notify(row["user_id"], course_id, title, "attendance_task", task_id, f"attendance.created:{task_id}")
        audit("attendance.create", "attendance_task", task_id, after={"course_id": course_id, "participants": len(students)})
        task = db.execute("SELECT * FROM attendance_task WHERE id=?", (task_id,)).fetchone()
    return one_time({**task_json(task), "code": code}, 201)


@bp.get("/courses/<int:course_id>/attendance-tasks")
def list_tasks(course_id):
    course_access(course_id)
    status = request.args.get("status")
    if status and status not in ("open", "closed"):
        raise ApiError(400, "VALIDATION_ERROR", "Invalid status")
    page, size = page_args()
    where = " WHERE course_id=?" + (" AND status=?" if status else "")
    params = (course_id, status) if status else (course_id,)
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM attendance_task" + where, params).fetchone()[0]
    rows = db.execute("SELECT * FROM attendance_task" + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
                      (*params, size, (page - 1) * size)).fetchall()
    return paged([task_json(row) for row in rows], total, page, size)


@bp.post("/attendance-tasks/<int:task_id>/check-ins")
def check_in(task_id):
    user = require_user()
    data = body(("code",))
    if user["role"] != "student":
        raise ApiError(403, "FORBIDDEN", "Student required")
    supplied = data["code"]
    if not isinstance(supplied, str) or not re.fullmatch(r"[0-9]{6}", supplied):
        raise ApiError(422, "INVALID_ATTENDANCE_CODE", "Invalid attendance code")
    invalid = False
    with write() as db:
        task = task_for_user(task_id)
        participant = db.execute("SELECT 1 FROM attendance_participant WHERE task_id=? AND student_id=?",
                                 (task_id, user["id"])).fetchone()
        if not participant:
            raise ApiError(404, "NOT_FOUND", "Attendance task not found")
        existing = db.execute("SELECT * FROM attendance_record WHERE task_id=? AND student_id=?",
                              (task_id, user["id"])).fetchone()
        if existing:
            return result(record_json(existing))
        timestamp = stamp()
        if task["status"] != "open" or not task["start_at"] <= timestamp < task["end_at"]:
            raise ApiError(409, "STATE_CONFLICT", "Attendance window is closed")
        if not hmac.compare_digest(code_hash(supplied), task["code_hash"]):
            rate_limit(f"checkin:{task_id}:{user['id']}", 5)
            invalid = True
        else:
            status = "present" if timestamp < task["late_at"] else "late"
            cursor = db.execute("INSERT INTO attendance_record(task_id,student_id,status,checked_at,"
                                "source,created_at,updated_at) VALUES(?,?,?,?,'checkin',?,?)",
                                (task_id, user["id"], status, timestamp, timestamp, timestamp))
            audit("attendance.checkin", "attendance_record", cursor.lastrowid,
                  after={"status": status, "task_id": task_id})
            record = db.execute("SELECT * FROM attendance_record WHERE id=?", (cursor.lastrowid,)).fetchone()
    if invalid:
        raise ApiError(422, "INVALID_ATTENDANCE_CODE", "Invalid attendance code")
    return result(record_json(record), 201)


@bp.post("/attendance-tasks/<int:task_id>/close")
def close_task(task_id):
    with write() as db:
        task = task_for_user(task_id, teacher=True)
        if task["status"] == "open":
            timestamp = stamp()
            db.execute("INSERT INTO attendance_record(task_id,student_id,status,source,created_at,updated_at) "
                       "SELECT p.task_id,p.student_id,'absent','close',?,? FROM attendance_participant p "
                       "LEFT JOIN attendance_record r ON r.task_id=p.task_id AND r.student_id=p.student_id "
                       "WHERE p.task_id=? AND r.id IS NULL", (timestamp, timestamp, task_id))
            db.execute("UPDATE attendance_task SET status='closed',updated_at=? WHERE id=?", (timestamp, task_id))
            audit("attendance.close", "attendance_task", task_id)
            for row in db.execute("SELECT student_id,status FROM attendance_record WHERE task_id=? "
                                  "AND status IN ('late','absent')", (task_id,)):
                notify(row["student_id"], task["course_id"], "考勤结果", "attendance_task", task_id,
                       f"attendance.closed:{task_id}:{row['student_id']}")
        counts = {key: 0 for key in ("present", "late", "leave", "absent")}
        for row in db.execute("SELECT status,COUNT(*) n FROM attendance_record WHERE task_id=? GROUP BY status", (task_id,)):
            counts[row["status"]] = row["n"]
        updated = db.execute("SELECT * FROM attendance_task WHERE id=?", (task_id,)).fetchone()
    return result({**task_json(updated), "counts": counts})


@bp.post("/attendance-tasks/<int:task_id>/rotate-code")
def rotate_code(task_id):
    with write() as db:
        task = task_for_user(task_id, teacher=True)
        timestamp = stamp()
        if task["status"] != "open" or not task["start_at"] <= timestamp < task["end_at"]:
            raise ApiError(409, "STATE_CONFLICT", "Attendance window is closed")
        code = new_code(task["code_hash"])
        db.execute("UPDATE attendance_task SET code_hash=?,updated_at=? WHERE id=?",
                   (code_hash(code), timestamp, task_id))
        audit("attendance.rotate_code", "attendance_task", task_id)
    return one_time({"code": code, "expires_at": task["end_at"], "qr_content": code})


@bp.post("/attendance-tasks/<int:task_id>/leave-requests")
def create_leave(task_id):
    user = require_user()
    data = body(("reason",))
    reason = text_field(data["reason"], "reason", maximum=500)
    if user["role"] != "student":
        raise ApiError(403, "FORBIDDEN", "Student required")
    with write() as db:
        task = task_for_user(task_id)
        if not db.execute("SELECT 1 FROM attendance_participant WHERE task_id=? AND student_id=?",
                          (task_id, user["id"])).fetchone():
            raise ApiError(404, "NOT_FOUND", "Attendance task not found")
        if task["status"] != "open" or stamp() >= task["end_at"]:
            raise ApiError(409, "STATE_CONFLICT", "Leave window is closed")
        if db.execute("SELECT 1 FROM leave_request WHERE task_id=? AND student_id=?", (task_id, user["id"])).fetchone():
            raise ApiError(409, "DUPLICATE", "Leave request already exists")
        timestamp = stamp()
        cursor = db.execute("INSERT INTO leave_request(task_id,student_id,reason,status,created_at,updated_at) "
                            "VALUES(?,?,?,'pending',?,?)", (task_id, user["id"], reason, timestamp, timestamp))
        audit("leave.create", "leave_request", cursor.lastrowid)
        leave = db.execute("SELECT * FROM leave_request WHERE id=?", (cursor.lastrowid,)).fetchone()
    return result(leave_json(leave), 201)


def leave_for_user(leave_id):
    leave = get_db().execute("SELECT l.*,t.course_id,t.end_at,t.status AS task_status "
                             "FROM leave_request l JOIN attendance_task t ON t.id=l.task_id WHERE l.id=?",
                             (leave_id,)).fetchone()
    if not leave:
        raise ApiError(404, "NOT_FOUND", "Leave request not found")
    return leave


@bp.put("/leave-requests/<int:leave_id>")
def update_leave(leave_id):
    user = require_user()
    data = body(("reason",))
    reason = text_field(data["reason"], "reason", maximum=500)
    with write() as db:
        leave = leave_for_user(leave_id)
        course_access(leave["course_id"])
        if user["role"] != "student" or user["id"] != leave["student_id"]:
            raise ApiError(404, "NOT_FOUND", "Leave request not found")
        if leave["task_status"] != "open" or stamp() >= leave["end_at"] or leave["status"] == "approved":
            raise ApiError(409, "STATE_CONFLICT", "Leave request cannot be changed")
        db.execute("UPDATE leave_request SET reason=?,status='pending',reviewer_id=NULL,"
                   "review_note=NULL,reviewed_at=NULL,updated_at=? WHERE id=?", (reason, stamp(), leave_id))
        if leave["status"] == "rejected":
            db.execute("INSERT INTO leave_review_event(leave_id,actor_id,old_status,new_status,note,reason_snapshot,created_at) "
                       "VALUES(?,?,'rejected','pending',NULL,?,?)", (leave_id, user["id"], reason, stamp()))
        audit("leave.update", "leave_request", leave_id, before={"status": leave["status"]}, after={"status": "pending"})
        updated = db.execute("SELECT * FROM leave_request WHERE id=?", (leave_id,)).fetchone()
    return result(leave_json(updated))


@bp.patch("/leave-requests/<int:leave_id>")
def review_leave(leave_id):
    user = require_user()
    data = body(("status", "note"), ("restore_status",))
    status = data["status"]
    note = text_field(data["note"], "note", maximum=500)
    if status not in ("approved", "rejected"):
        raise ApiError(400, "VALIDATION_ERROR", "Invalid leave status")
    with write() as db:
        leave = leave_for_user(leave_id)
        course_access(leave["course_id"], teacher=True)
        if leave["status"] == status:
            return result(leave_json(leave))
        if leave["status"] != "pending" and not (leave["status"] == "approved" and status == "rejected"):
            raise ApiError(409, "STATE_CONFLICT", "Leave request cannot be reviewed")
        restore = data.get("restore_status")
        if leave["status"] == "approved" and status == "rejected":
            if restore not in ("present", "late", "absent"):
                raise ApiError(400, "VALIDATION_ERROR", "restore_status required for correction")
        elif restore is not None:
            raise ApiError(400, "VALIDATION_ERROR", "restore_status is not applicable")
        timestamp = stamp()
        db.execute("UPDATE leave_request SET status=?,reviewer_id=?,review_note=?,reviewed_at=?,updated_at=? WHERE id=?",
                   (status, user["id"], note, timestamp, timestamp, leave_id))
        db.execute("INSERT INTO leave_review_event(leave_id,actor_id,old_status,new_status,note,reason_snapshot,created_at) "
                   "VALUES(?,?,?,?,?,?,?)", (leave_id, user["id"], leave["status"], status, note, leave["reason"], timestamp))
        previous = db.execute("SELECT * FROM attendance_record WHERE task_id=? AND student_id=?",
                              (leave["task_id"], leave["student_id"])).fetchone()
        if status == "approved" or restore:
            new_status = "leave" if status == "approved" else restore
            if previous:
                db.execute("UPDATE attendance_record SET status=?,source=?,updated_at=? WHERE id=?",
                           (new_status, "approval" if status == "approved" else "correction", timestamp, previous["id"]))
            else:
                db.execute("INSERT INTO attendance_record(task_id,student_id,status,source,created_at,updated_at) "
                           "VALUES(?,?,?,'approval',?,?)", (leave["task_id"], leave["student_id"], new_status,
                                                             timestamp, timestamp))
        audit("leave.review", "leave_request", leave_id,
              before={"status": leave["status"], "record": previous["status"] if previous else None},
              after={"status": status, "record": "leave" if status == "approved" else restore})
        notify(leave["student_id"], leave["course_id"], "请假审批结果", "leave_request", leave_id,
               f"leave.review:{leave_id}:{timestamp}")
        updated = db.execute("SELECT * FROM leave_request WHERE id=?", (leave_id,)).fetchone()
    return result(leave_json(updated))


@bp.get("/courses/<int:course_id>/leave-requests")
def list_leaves(course_id):
    _, role = course_access(course_id)
    task_id = positive_int(request.args["task_id"], "task_id") if request.args.get("task_id") else None
    status = request.args.get("status")
    if status and status not in ("pending", "approved", "rejected"):
        raise ApiError(400, "VALIDATION_ERROR", "Invalid status")
    page, size = page_args()
    where, params = " WHERE t.course_id=?", [course_id]
    if role == "student":
        where += " AND l.student_id=?"
        params.append(require_user()["id"])
    if task_id:
        where += " AND l.task_id=?"
        params.append(task_id)
    if status:
        where += " AND l.status=?"
        params.append(status)
    source = " FROM leave_request l JOIN attendance_task t ON t.id=l.task_id" + where
    db = get_db()
    total = db.execute("SELECT COUNT(*)" + source, params).fetchone()[0]
    rows = db.execute("SELECT l.*" + source + " ORDER BY l.id DESC LIMIT ? OFFSET ?",
                      (*params, size, (page - 1) * size)).fetchall()
    return paged([leave_json(row) for row in rows], total, page, size)


@bp.get("/courses/<int:course_id>/attendance-records")
def list_records(course_id):
    _, role = course_access(course_id)
    task_id = positive_int(request.args["task_id"], "task_id") if request.args.get("task_id") else None
    student_id = positive_int(request.args["student_id"], "student_id") if request.args.get("student_id") else None
    user = require_user()
    if role == "student" and student_id not in (None, user["id"]):
        raise ApiError(403, "FORBIDDEN", "Only own records are visible")
    page, size = page_args()
    where, params = " WHERE t.course_id=?", [course_id]
    if role == "student" or student_id:
        where += " AND r.student_id=?"
        params.append(user["id"] if role == "student" else student_id)
    if task_id:
        where += " AND r.task_id=?"
        params.append(task_id)
    source = " FROM attendance_record r JOIN attendance_task t ON t.id=r.task_id" + where
    db = get_db()
    total = db.execute("SELECT COUNT(*)" + source, params).fetchone()[0]
    rows = db.execute("SELECT r.*" + source + " ORDER BY r.id DESC LIMIT ? OFFSET ?",
                      (*params, size, (page - 1) * size)).fetchall()
    return paged([record_json(row) for row in rows], total, page, size)


@bp.patch("/attendance-records/<int:record_id>")
def correct_record(record_id):
    data = body(("status", "reason"))
    status = data["status"]
    if status not in ("present", "late", "leave", "absent"):
        raise ApiError(400, "VALIDATION_ERROR", "Invalid record status")
    reason = text_field(data["reason"], "reason", maximum=500)
    with write() as db:
        record = db.execute("SELECT r.*,t.course_id FROM attendance_record r "
                            "JOIN attendance_task t ON t.id=r.task_id WHERE r.id=?", (record_id,)).fetchone()
        if not record:
            raise ApiError(404, "NOT_FOUND", "Attendance record not found")
        course_access(record["course_id"], teacher=True)
        db.execute("UPDATE attendance_record SET status=?,source='correction',updated_at=? WHERE id=?",
                   (status, stamp(), record_id))
        audit("attendance.correct", "attendance_record", record_id,
              before={"status": record["status"]}, after={"status": status, "reason": reason})
        notify(record["student_id"], record["course_id"], "考勤更正", "attendance_task", record["task_id"],
               f"attendance.correct:{record_id}:{stamp()}")
        updated = db.execute("SELECT * FROM attendance_record WHERE id=?", (record_id,)).fetchone()
    return result(record_json(updated))
