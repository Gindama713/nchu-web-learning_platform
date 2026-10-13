"""SPEC-001 course membership, notifications and audit access."""

from flask import Blueprint, request

from backend.shared.api import (
    ApiError,
    audit,
    body,
    page_args,
    paged,
    positive_int,
    result,
    stamp,
    text_field,
)
from backend.shared.auth import course_access, require_admin, require_user
from backend.shared.db import get_db, write

bp = Blueprint("courses", __name__)


def course_json(row):
    return {key: row[key] for key in ("id", "title", "description", "teacher_id")}


def member_json(row):
    return {key: row[key] for key in ("user_id", "name", "student_no", "member_role", "active")}


@bp.get("/courses")
def list_courses():
    user = require_user()
    page, size = page_args()
    db = get_db()
    if user["role"] == "admin":
        base, params = "FROM course", ()
    else:
        base = ("FROM course c JOIN course_member m ON m.course_id=c.id "
                "WHERE m.user_id=? AND m.active=1 AND m.member_role=?")
        params = (user["id"], user["role"])
    total = db.execute("SELECT COUNT(*) " + base, params).fetchone()[0]
    rows = db.execute("SELECT c.* " + base + " ORDER BY c.id LIMIT ? OFFSET ?" if user["role"] != "admin"
                      else "SELECT * " + base + " ORDER BY id LIMIT ? OFFSET ?",
                      (*params, size, (page - 1) * size)).fetchall()
    return paged([course_json(row) for row in rows], total, page, size)


@bp.post("/courses")
def create_course():
    require_admin()
    data = body(("title", "teacher_id"), ("description",))
    title = text_field(data["title"], "title")
    description = text_field(data.get("description", ""), "description", 0, 5000)
    teacher_id = positive_int(data["teacher_id"], "teacher_id")
    with write() as db:
        teacher = db.execute("SELECT id FROM user WHERE id=? AND role='teacher' AND active=1", (teacher_id,)).fetchone()
        if not teacher:
            raise ApiError(422, "VALIDATION_ERROR", "Active teacher required")
        timestamp = stamp()
        cursor = db.execute("INSERT INTO course(title,description,teacher_id,created_at,updated_at) "
                            "VALUES(?,?,?,?,?)", (title, description, teacher_id, timestamp, timestamp))
        course_id = cursor.lastrowid
        db.execute("INSERT INTO course_member(course_id,user_id,member_role,active,created_at,updated_at) "
                   "VALUES(?,?,'teacher',1,?,?)", (course_id, teacher_id, timestamp, timestamp))
        audit("course.create", "course", course_id, after={"teacher_id": teacher_id})
        course = db.execute("SELECT * FROM course WHERE id=?", (course_id,)).fetchone()
    return result(course_json(course), 201)


@bp.get("/courses/<int:course_id>/members")
def list_members(course_id):
    course_access(course_id, teacher=True, manager=True)
    role = request.args.get("member_role")
    if role and role not in ("student", "teacher"):
        raise ApiError(400, "VALIDATION_ERROR", "Invalid member_role")
    query = request.args.get("q", "").strip()
    if len(query) > 100:
        raise ApiError(400, "VALIDATION_ERROR", "q too long")
    page, size = page_args()
    where = " WHERE m.course_id=?"
    params = [course_id]
    if role:
        where += " AND m.member_role=?"
        params.append(role)
    if query:
        where += " AND (u.name LIKE ? OR u.student_no LIKE ?)"
        params += [f"%{query}%", f"%{query}%"]
    source = " FROM course_member m JOIN user u ON u.id=m.user_id" + where
    db = get_db()
    total = db.execute("SELECT COUNT(*)" + source, params).fetchone()[0]
    rows = db.execute("SELECT m.user_id,u.name,u.student_no,m.member_role,m.active" + source +
                      " ORDER BY m.user_id LIMIT ? OFFSET ?", (*params, size, (page - 1) * size)).fetchall()
    return paged([member_json(row) for row in rows], total, page, size)


@bp.post("/courses/<int:course_id>/members")
def add_member(course_id):
    actor = require_user()
    data = body(("user_id", "member_role"))
    user_id = positive_int(data["user_id"], "user_id")
    role = data["member_role"]
    if role not in ("student", "teacher"):
        raise ApiError(400, "VALIDATION_ERROR", "Invalid member_role")
    with write() as db:
        course_access(course_id, teacher=True, manager=True)
        if actor["role"] == "teacher" and role != "student":
            raise ApiError(403, "FORBIDDEN", "Teachers may only add students")
        user = db.execute("SELECT * FROM user WHERE id=?", (user_id,)).fetchone()
        if not user or not user["active"] or user["role"] != role:
            raise ApiError(422, "VALIDATION_ERROR", "Active user with matching role required")
        existing = db.execute("SELECT * FROM course_member WHERE course_id=? AND user_id=?", (course_id, user_id)).fetchone()
        if existing and existing["active"]:
            raise ApiError(409, "DUPLICATE", "Member already active")
        timestamp = stamp()
        if existing:
            db.execute("UPDATE course_member SET member_role=?,active=1,updated_at=? WHERE id=?",
                       (role, timestamp, existing["id"]))
        else:
            db.execute("INSERT INTO course_member(course_id,user_id,member_role,active,created_at,updated_at) "
                       "VALUES(?,?,?,1,?,?)", (course_id, user_id, role, timestamp, timestamp))
        audit("course.member_add", "course_member", user_id,
              after={"course_id": course_id, "role": role})
    return result({"user_id": user_id, "member_role": role, "active": True}, 201)


@bp.delete("/courses/<int:course_id>/members/<int:user_id>")
def remove_member(course_id, user_id):
    actor = require_user()
    with write() as db:
        course, _ = course_access(course_id, teacher=True, manager=True)
        member = db.execute("SELECT * FROM course_member WHERE course_id=? AND user_id=?",
                            (course_id, user_id)).fetchone()
        if not member:
            raise ApiError(404, "NOT_FOUND", "Member not found")
        if actor["role"] == "teacher" and member["member_role"] != "student":
            raise ApiError(403, "FORBIDDEN", "Teachers may only remove students")
        if course["teacher_id"] == user_id:
            raise ApiError(409, "STATE_CONFLICT", "Transfer responsible teacher first")
        db.execute("UPDATE course_member SET active=0,updated_at=? WHERE id=?", (stamp(), member["id"]))
        audit("course.member_remove", "course_member", user_id,
              before={"course_id": course_id, "active": bool(member["active"])})
    return "", 204


@bp.patch("/courses/<int:course_id>")
def transfer_course(course_id):
    require_admin()
    data = body(("teacher_id", "retain_previous_teacher"))
    teacher_id = positive_int(data["teacher_id"], "teacher_id")
    retain = data["retain_previous_teacher"]
    if not isinstance(retain, bool):
        raise ApiError(400, "VALIDATION_ERROR", "retain_previous_teacher must be boolean")
    with write() as db:
        course = db.execute("SELECT * FROM course WHERE id=?", (course_id,)).fetchone()
        teacher = db.execute("SELECT id FROM user WHERE id=? AND role='teacher' AND active=1", (teacher_id,)).fetchone()
        if not course:
            raise ApiError(404, "NOT_FOUND", "Course not found")
        if not teacher or (teacher_id == course["teacher_id"] and not retain):
            raise ApiError(422, "VALIDATION_ERROR", "Valid replacement teacher required")
        timestamp = stamp()
        db.execute("INSERT INTO course_member(course_id,user_id,member_role,active,created_at,updated_at) "
                   "VALUES(?,?,'teacher',1,?,?) ON CONFLICT(course_id,user_id) DO UPDATE SET "
                   "member_role='teacher',active=1,updated_at=excluded.updated_at",
                   (course_id, teacher_id, timestamp, timestamp))
        if not retain and teacher_id != course["teacher_id"]:
            db.execute("UPDATE course_member SET active=0,updated_at=? WHERE course_id=? AND user_id=?",
                       (timestamp, course_id, course["teacher_id"]))
        db.execute("UPDATE course SET teacher_id=?,updated_at=? WHERE id=?", (teacher_id, timestamp, course_id))
        audit("course.transfer", "course", course_id,
              before={"teacher_id": course["teacher_id"]}, after={"teacher_id": teacher_id, "retain": retain})
        updated = db.execute("SELECT * FROM course WHERE id=?", (course_id,)).fetchone()
    return result(course_json(updated))


@bp.get("/notifications")
def notifications():
    user = require_user()
    unread = request.args.get("unread")
    if unread not in (None, "true", "false"):
        raise ApiError(400, "VALIDATION_ERROR", "Invalid unread filter")
    page, size = page_args()
    where = " WHERE user_id=?" + (" AND read_at IS NULL" if unread == "true" else " AND read_at IS NOT NULL" if unread == "false" else "")
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM notification" + where, (user["id"],)).fetchone()[0]
    rows = db.execute("SELECT id,title,target_type,target_id,read_at FROM notification" + where +
                      " ORDER BY id DESC LIMIT ? OFFSET ?", (user["id"], size, (page - 1) * size)).fetchall()
    return paged([dict(row) for row in rows], total, page, size)


@bp.patch("/notifications/<int:notification_id>")
def read_notification(notification_id):
    user = require_user()
    data = body(("read",))
    if data["read"] is not True:
        raise ApiError(400, "VALIDATION_ERROR", "read must be true")
    with write() as db:
        row = db.execute("SELECT * FROM notification WHERE id=? AND user_id=?",
                         (notification_id, user["id"])).fetchone()
        if not row:
            raise ApiError(404, "NOT_FOUND", "Notification not found")
        db.execute("UPDATE notification SET read_at=COALESCE(read_at,?) WHERE id=?", (stamp(), notification_id))
        updated = db.execute("SELECT id,title,target_type,target_id,read_at FROM notification WHERE id=?",
                             (notification_id,)).fetchone()
    return result(dict(updated))


@bp.get("/admin/audit-events")
def audit_events():
    require_admin()
    page, size = page_args()
    action = request.args.get("action")
    actor_id = positive_int(request.args["actor"], "actor") if request.args.get("actor") else None
    conditions, params = [], []
    if action:
        conditions.append("action=?")
        params.append(text_field(action, "action"))
    if actor_id:
        conditions.append("actor_id=?")
        params.append(actor_id)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM audit_event" + where, params).fetchone()[0]
    rows = db.execute("SELECT * FROM audit_event" + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
                      (*params, size, (page - 1) * size)).fetchall()
    return paged([dict(row) for row in rows], total, page, size)
