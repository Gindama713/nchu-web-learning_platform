"""SPEC-004 备课单元 HTTP 适配器。"""

import sqlite3

from flask import Blueprint

from backend.shared.api import (
    ApiError,
    audit,
    body,
    notify,
    now,
    page_args,
    paged,
    parse_time,
    positive_int,
    result,
    stamp,
    text_field,
)
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db, write

bp = Blueprint("preparations", __name__)

PREPARATION_STATUSES = ("draft", "published", "withdrawn")


def _id_list(value, field):
    if not isinstance(value, list) or any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in value):
        raise ApiError(400, "VALIDATION_ERROR", f"{field} must be a list of positive integers")
    if len(value) != len(set(value)):
        raise ApiError(400, "VALIDATION_ERROR", f"{field} must not contain duplicates")
    return value


def _parse_time_optional(value, field):
    if value is None:
        return None
    from backend.shared.api import parse_time
    return stamp(parse_time(value, field))


def _preparation_row(db, preparation_id):
    return db.execute("SELECT * FROM preparation WHERE id=?", (preparation_id,)).fetchone()


def _links(db, preparation_id):
    knowledge = [r[0] for r in db.execute(
        "SELECT knowledge_id FROM preparation_knowledge WHERE preparation_id=? ORDER BY knowledge_id",
        (preparation_id,)).fetchall()]
    resource = [r[0] for r in db.execute(
        "SELECT resource_version_id FROM preparation_resource WHERE preparation_id=? ORDER BY resource_version_id",
        (preparation_id,)).fetchall()]
    question = [r[0] for r in db.execute(
        "SELECT question_version_id FROM preparation_question WHERE preparation_id=? ORDER BY question_version_id",
        (preparation_id,)).fetchall()]
    quiz = [r[0] for r in db.execute(
        "SELECT paper_id FROM preparation_quiz WHERE preparation_id=? ORDER BY paper_id",
        (preparation_id,)).fetchall()]
    return knowledge, resource, question, quiz


def _serialize(db, row, role, user_id=None):
    knowledge, resource, question, quiz = _links(db, row["id"])
    item = {
        "id": row["id"],
        "course_id": row["course_id"],
        "title": row["title"],
        "scheduled_at": row["scheduled_at"],
        "status": row["status"],
        "source_id": row["source_id"],
        "published_at": row["published_at"],
        "replaces_id": row["replaces_id"],
        "withdrawn_at": row["withdrawn_at"],
        "withdraw_reason": row["withdraw_reason"],
        "knowledge_ids": knowledge,
        "resource_version_ids": resource,
        "question_version_ids": question,
        "quiz_ids": quiz,
    }
    if role == "student":
        visible_quiz = [r[0] for r in db.execute(
            "SELECT pq.paper_id FROM preparation_quiz pq "
            "JOIN paper p ON p.id=pq.paper_id "
            "WHERE pq.preparation_id=? AND p.status='published' AND EXISTS("
            "SELECT 1 FROM paper_participant pp WHERE pp.paper_id=p.id AND pp.student_id=?)",
            (row["id"], user_id)).fetchall()]
        item["quiz_ids"] = visible_quiz
        quizzes = db.execute(
            "SELECT id,title,start_at,end_at FROM paper WHERE id IN ("
            + ",".join("?" * len(visible_quiz)) + ")", visible_quiz or [0]).fetchall() if visible_quiz else []
        current = now()
        item["quizzes"] = [dict(q) | {"window_state": "upcoming" if current < parse_time(q["start_at"], "start_at")
                            else "open" if current < parse_time(q["end_at"], "end_at") else "closed"}
                           for q in quizzes]
    return item


def _assert_same_course(db, course_id, table, column, ids, extra_where=""):
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    if table == "knowledge_point":
        rows = db.execute(
            f"SELECT k.id FROM knowledge_point k JOIN chapter c ON c.id=k.chapter_id "
            f"WHERE k.id IN ({placeholders}) AND c.course_id=?{extra_where}",
            (*ids, course_id)).fetchall()
    elif table == "question_version":
        rows = db.execute(
            f"SELECT qv.id FROM question_version qv JOIN question q ON q.id=qv.question_id "
            f"WHERE qv.id IN ({placeholders}) AND q.course_id=?{extra_where}",
            (*ids, course_id)).fetchall()
    elif table == "paper":
        rows = db.execute(
            f"SELECT id FROM paper WHERE id IN ({placeholders}) AND course_id=?{extra_where}",
            (*ids, course_id)).fetchall()
    elif table == "resource_version":
        rows = db.execute(
            f"SELECT rv.id FROM resource_version rv JOIN resource r ON r.id=rv.resource_id "
            f"WHERE rv.id IN ({placeholders}) AND r.course_id=?{extra_where}",
            (*ids, course_id)).fetchall()
    else:
        raise ApiError(500, "INTERNAL_ERROR", "Unknown relation table")
    found = {r[0] for r in rows}
    missing = [i for i in ids if i not in found]
    if missing:
        raise ApiError(404, "NOT_FOUND", f"Related {table} not found in this course", {"ids": missing})


def _resource_table_exists(db):
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='resource_version'").fetchone() is not None


def _validate_links(db, course_id, knowledge_ids, resource_ids, question_ids, quiz_ids, for_publish=False):
    _assert_same_course(db, course_id, "knowledge_point", "id", knowledge_ids,
                        " AND k.published=1" if for_publish else "")
    if resource_ids:
        if not _resource_table_exists(db):
            raise ApiError(503, "RESOURCE_MODULE_NOT_READY",
                           "Resource module (SPEC-003) is not available yet")
        _assert_same_course(db, course_id, "resource_version", "id", resource_ids,
                            " AND r.visibility='students'" if for_publish else "")
    if question_ids:
        extra = " AND qv.practice_available=1 AND qv.type IN ('single','multiple','boolean','numeric')" if for_publish else ""
        _assert_same_course(db, course_id, "question_version", "id", question_ids, extra)
    if quiz_ids:
        _assert_same_course(db, course_id, "paper", "id", quiz_ids, " AND kind='quiz'")
        if for_publish:
            placeholders = ",".join("?" * len(quiz_ids))
            unpublished = db.execute(
                f"SELECT id FROM paper WHERE id IN ({placeholders}) AND status!='published'",
                quiz_ids).fetchall()
            if unpublished:
                raise ApiError(409, "QUIZ_NOT_PUBLISHED", "Linked quiz is not published")


def _replace_links(db, preparation_id, knowledge_ids, resource_ids, question_ids, quiz_ids):
    db.execute("DELETE FROM preparation_knowledge WHERE preparation_id=?", (preparation_id,))
    db.execute("DELETE FROM preparation_resource WHERE preparation_id=?", (preparation_id,))
    db.execute("DELETE FROM preparation_question WHERE preparation_id=?", (preparation_id,))
    db.execute("DELETE FROM preparation_quiz WHERE preparation_id=?", (preparation_id,))
    for kid in knowledge_ids:
        db.execute("INSERT INTO preparation_knowledge(preparation_id,knowledge_id) VALUES(?,?)",
                   (preparation_id, kid))
    for rid in resource_ids:
        db.execute("INSERT INTO preparation_resource(preparation_id,resource_version_id) VALUES(?,?)",
                   (preparation_id, rid))
    for qid in question_ids:
        db.execute("INSERT INTO preparation_question(preparation_id,question_version_id) VALUES(?,?)",
                   (preparation_id, qid))
    for pid in quiz_ids:
        db.execute("INSERT INTO preparation_quiz(preparation_id,paper_id) VALUES(?,?)",
                   (preparation_id, pid))


@bp.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.post("/courses/<int:course_id>/preparations")
def create_preparation(course_id):
    course_access(course_id, teacher=True)
    data = body(("title", "knowledge_ids", "resource_version_ids", "question_version_ids", "quiz_ids"),
                ("scheduled_at",))
    title = text_field(data["title"], "title")
    knowledge_ids = _id_list(data["knowledge_ids"], "knowledge_ids")
    resource_ids = _id_list(data["resource_version_ids"], "resource_version_ids")
    question_ids = _id_list(data["question_version_ids"], "question_version_ids")
    quiz_ids = _id_list(data["quiz_ids"], "quiz_ids")
    scheduled_at = _parse_time_optional(data.get("scheduled_at"), "scheduled_at")
    with write() as db:
        _validate_links(db, course_id, knowledge_ids, resource_ids, question_ids, quiz_ids)
        timestamp = stamp()
        cursor = db.execute(
            "INSERT INTO preparation(course_id,title,scheduled_at,status,created_at,updated_at) "
            "VALUES(?,?,?,'draft',?,?)",
            (course_id, title, scheduled_at, timestamp, timestamp))
        prep_id = cursor.lastrowid
        _replace_links(db, prep_id, knowledge_ids, resource_ids, question_ids, quiz_ids)
        row = _preparation_row(db, prep_id)
        audit("preparation.create", "preparation", prep_id,
              after={"course_id": course_id, "title": title})
    return result(_serialize(db, row, "teacher"), 201)


@bp.post("/preparations/<int:preparation_id>/copy")
def copy_preparation(preparation_id):
    require_user()
    data = body(("title",))
    title = text_field(data["title"], "title")
    with write() as db:
        source = _preparation_row(db, preparation_id)
        if not source:
            raise ApiError(404, "NOT_FOUND", "Preparation not found")
        course_access(source["course_id"], teacher=True)
        knowledge_ids, resource_ids, question_ids, quiz_ids = _links(db, preparation_id)
        timestamp = stamp()
        cursor = db.execute(
            "INSERT INTO preparation(course_id,title,scheduled_at,status,source_id,created_at,updated_at) "
            "VALUES(?,?,?,'draft',?,?,?)",
            (source["course_id"], title, source["scheduled_at"], preparation_id, timestamp, timestamp))
        new_id = cursor.lastrowid
        _replace_links(db, new_id, knowledge_ids, resource_ids, question_ids, quiz_ids)
        row = _preparation_row(db, new_id)
        audit("preparation.copy", "preparation", new_id,
              after={"source_id": preparation_id, "title": title})
    return result(_serialize(db, row, "teacher"), 201)


@bp.post("/preparations/<int:preparation_id>/publish")
def publish_preparation(preparation_id):
    require_user()
    data = body((), ("replaces_id",))
    replaces_id = data.get("replaces_id")
    if replaces_id is not None:
        replaces_id = positive_int(replaces_id, "replaces_id")
    with write() as db:
        row = _preparation_row(db, preparation_id)
        if not row:
            raise ApiError(404, "NOT_FOUND", "Preparation not found")
        course_access(row["course_id"], teacher=True)
        if row["status"] != "draft":
            raise ApiError(409, "STATE_CONFLICT", "Only draft preparation can be published")
        knowledge_ids, resource_ids, question_ids, quiz_ids = _links(db, preparation_id)
        _validate_links(db, row["course_id"], knowledge_ids, resource_ids, question_ids, quiz_ids,
                        for_publish=True)
        if replaces_id is not None:
            if replaces_id == preparation_id:
                raise ApiError(400, "VALIDATION_ERROR", "replaces_id cannot reference itself")
            old = db.execute("SELECT * FROM preparation WHERE id=? AND course_id=?",
                             (replaces_id, row["course_id"])).fetchone()
            if not old or old["status"] != "published":
                raise ApiError(404, "NOT_FOUND", "replaces_id must be a published preparation in this course")
            db.execute("UPDATE preparation SET replaces_id=? WHERE id=?",
                       (replaces_id, preparation_id))
            db.execute("UPDATE preparation SET status='withdrawn',withdrawn_at=?,withdraw_reason=?,"
                       "updated_at=? WHERE id=?",
                       (stamp(), "replaced by new published preparation", stamp(), replaces_id))
        timestamp = stamp()
        db.execute("UPDATE preparation SET status='published',published_at=?,updated_at=? WHERE id=?",
                   (timestamp, timestamp, preparation_id))
        row = _preparation_row(db, preparation_id)
        audit("preparation.publish", "preparation", preparation_id,
              after={"status": "published", "replaces_id": replaces_id})
        members = db.execute(
            "SELECT user_id FROM course_member WHERE course_id=? AND member_role='student' AND active=1",
            (row["course_id"],)).fetchall()
        for m in members:
            notify(m["user_id"], row["course_id"], f"备课已发布：{row['title']}",
                   "preparation", preparation_id, f"preparation:publish:{preparation_id}")
    return result(_serialize(db, row, "teacher"))


@bp.post("/preparations/<int:preparation_id>/withdraw")
def withdraw_preparation(preparation_id):
    require_user()
    data = body(("reason",))
    reason = text_field(data["reason"], "reason", minimum=1, maximum=500)
    with write() as db:
        row = _preparation_row(db, preparation_id)
        if not row:
            raise ApiError(404, "NOT_FOUND", "Preparation not found")
        course_access(row["course_id"], teacher=True)
        if row["status"] == "withdrawn":
            return result(_serialize(db, row, "teacher"))
        if row["status"] != "published":
            raise ApiError(409, "STATE_CONFLICT", "Only published preparation can be withdrawn")
        timestamp = stamp()
        db.execute("UPDATE preparation SET status='withdrawn',withdrawn_at=?,withdraw_reason=?,"
                   "updated_at=? WHERE id=?", (timestamp, reason, timestamp, preparation_id))
        row = _preparation_row(db, preparation_id)
        audit("preparation.withdraw", "preparation", preparation_id,
              after={"status": "withdrawn", "reason": reason})
    return result(_serialize(db, row, "teacher"))


@bp.get("/courses/<int:course_id>/preparations")
def list_preparations(course_id):
    user = require_user()
    _, role = course_access(course_id)
    page, size = page_args()
    db = get_db()
    if role == "teacher":
        where, params = "WHERE course_id=?", (course_id,)
    else:
        where, params = "WHERE course_id=? AND status='published'", (course_id,)
    total = db.execute("SELECT COUNT(*) FROM preparation " + where, params).fetchone()[0]
    rows = db.execute("SELECT * FROM preparation " + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
                      (*params, size, (page - 1) * size)).fetchall()
    items = [_serialize(db, r, role, user["id"]) for r in rows]
    return paged(items, total, page, size)


@bp.get("/preparations/<int:preparation_id>")
def get_preparation(preparation_id):
    user = require_user()
    db = get_db()
    row = _preparation_row(db, preparation_id)
    if not row:
        raise ApiError(404, "NOT_FOUND", "Preparation not found")
    _, role = course_access(row["course_id"])
    if role == "student" and row["status"] != "published":
        raise ApiError(404, "NOT_FOUND", "Preparation not found")
    return result(_serialize(db, row, role, user["id"]))


@bp.patch("/preparations/<int:preparation_id>")
def update_preparation(preparation_id):
    require_user()
    data = body((), ("title", "knowledge_ids", "resource_version_ids", "question_version_ids",
                     "quiz_ids", "scheduled_at"))
    if not data:
        raise ApiError(400, "VALIDATION_ERROR", "At least one field must be provided")
    with write() as db:
        row = _preparation_row(db, preparation_id)
        if not row:
            raise ApiError(404, "NOT_FOUND", "Preparation not found")
        course_access(row["course_id"], teacher=True)
        if row["status"] != "draft":
            raise ApiError(409, "STATE_CONFLICT", "Only draft preparation can be updated")
        title = text_field(data["title"], "title") if "title" in data else row["title"]
        scheduled_at = (_parse_time_optional(data["scheduled_at"], "scheduled_at")
                        if "scheduled_at" in data else row["scheduled_at"])
        knowledge_ids = (_id_list(data["knowledge_ids"], "knowledge_ids")
                         if "knowledge_ids" in data else _links(db, preparation_id)[0])
        resource_ids = (_id_list(data["resource_version_ids"], "resource_version_ids")
                        if "resource_version_ids" in data else _links(db, preparation_id)[1])
        question_ids = (_id_list(data["question_version_ids"], "question_version_ids")
                        if "question_version_ids" in data else _links(db, preparation_id)[2])
        quiz_ids = (_id_list(data["quiz_ids"], "quiz_ids")
                    if "quiz_ids" in data else _links(db, preparation_id)[3])
        _validate_links(db, row["course_id"], knowledge_ids, resource_ids, question_ids, quiz_ids)
        db.execute("UPDATE preparation SET title=?,scheduled_at=?,updated_at=? WHERE id=?",
                   (title, scheduled_at, stamp(), preparation_id))
        if any(k in data for k in ("knowledge_ids", "resource_version_ids",
                                   "question_version_ids", "quiz_ids")):
            _replace_links(db, preparation_id, knowledge_ids, resource_ids, question_ids, quiz_ids)
        row = _preparation_row(db, preparation_id)
        audit("preparation.update", "preparation", preparation_id,
              after={"title": title})
    return result(_serialize(db, row, "teacher"))


@bp.errorhandler(sqlite3.IntegrityError)
def integrity_error(_error):
    return result({}, 409)
