"""SPEC-003 teaching resources: upload, version, list, content, update, question import."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, request, send_file

from backend.models import attempt as attempt_model
from backend.models.question import (
    check_knowledge,
    require_tables,
    save_version,
    validate_question,
)
from backend.shared.api import (
    ApiError,
    audit,
    page_args,
    paged,
    positive_int,
    request_id,
    result,
    stamp,
    text_field,
)
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db, write

bp = Blueprint("resources", __name__)

# 文件大小限制（字节）
SIZE_LIMITS = {"video": 100 * 1024 * 1024, "slides": 20 * 1024 * 1024,
               "guide": 20 * 1024 * 1024, "question_bank": 20 * 1024 * 1024}
# view 支持的 media_type 前缀
VIEWABLE_PREFIXES = ("application/pdf", "image/png", "image/jpeg", "video/")
KIND_MEDIA = {
    "slides": ("application/pdf", "application/vnd.ms-powerpoint",
               "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    "video": ("video/mp4", "video/webm"),
    "guide": ("application/pdf",),
    "question_bank": ("application/json",),
}


def upload_root():
    root = current_app.config.get("UPLOAD_ROOT", "instance/uploads")
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_file(file_storage, kind):
    """读取上传内容、校验大小/类型、落盘并返回 file_object 字段。"""
    if kind not in SIZE_LIMITS:
        raise ApiError(400, "VALIDATION_ERROR", "Invalid kind")
    media_type = file_storage.mimetype or "application/octet-stream"
    allowed = KIND_MEDIA.get(kind, ())
    if allowed and media_type not in allowed:
        raise ApiError(415, "UNSUPPORTED_MEDIA", "File type not supported for this kind")
    content = file_storage.read()
    size = len(content)
    if size > SIZE_LIMITS[kind]:
        raise ApiError(413, "FILE_TOO_LARGE", f"{kind} exceeds size limit")
    if size == 0:
        raise ApiError(400, "VALIDATION_ERROR", "Empty file")
    sha256 = hashlib.sha256(content).hexdigest()
    storage_key = uuid4().hex
    # 原子写入：先写临时文件再改名
    target = upload_root() / storage_key
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(content)
    tmp.replace(target)
    return {"storage_key": storage_key, "original_name": file_storage.filename or storage_key,
            "media_type": media_type, "size_bytes": size, "sha256": sha256,
            "purpose": f"resource:{kind}"}


def insert_file_object(db, fields, owner_id):
    ts = stamp()
    cursor = db.execute(
        "INSERT INTO file_object(owner_id,storage_key,original_name,media_type,"
        "size_bytes,sha256,purpose,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (owner_id, fields["storage_key"], fields["original_name"], fields["media_type"],
         fields["size_bytes"], fields["sha256"], fields["purpose"], ts),
    )
    return cursor.lastrowid, ts


def resource_json(row):
    return {k: row[k] for k in ("id", "course_id", "chapter_id", "title",
                               "kind", "visibility", "archived")}


def version_json(row):
    out = {k: row[k] for k in ("id", "resource_id", "version", "change_note", "created_at")}
    out["size"] = row["size_bytes"]
    out["sha256"] = row["sha256"]
    out["title"] = row["title"]
    out["kind"] = row["kind"]
    return out


def visible_to_student(resource_row):
    """学生只能看到 visibility=students 且非 question_bank 的资源。"""
    return resource_row["visibility"] == "students" and resource_row["kind"] != "question_bank"


def load_resource(db, resource_id, *, teacher=False):
    """加载资源并按可见性鉴权。teacher=True 时允许 teacher_only。"""
    require_user()
    row = db.execute("SELECT * FROM resource WHERE id=?", (resource_id,)).fetchone()
    if not row or row["archived"]:
        raise ApiError(404, "NOT_FOUND", "Resource not found")
    _course, role = course_access(row["course_id"], teacher=teacher)
    if not teacher and role == "student" and not visible_to_student(row):
        raise ApiError(404, "NOT_FOUND", "Resource not found")
    return row, role


# ---------- POST /courses/<id>/resources ----------
@bp.post("/courses/<int:course_id>/resources")
def create_resource(course_id):
    user = require_user()
    file_storage = request.files.get("file")
    if not file_storage:
        raise ApiError(400, "VALIDATION_ERROR", "file required")
    title = text_field((request.form.get("title") or ""), "title")
    kind = request.form.get("kind", "")
    if kind not in ("slides", "video", "guide", "question_bank"):
        raise ApiError(400, "VALIDATION_ERROR", "Invalid kind")
    chapter_id_raw = request.form.get("chapter_id")
    chapter_id = positive_int(chapter_id_raw, "chapter_id") if chapter_id_raw else None
    with write() as db:
        _course, _ = course_access(course_id, teacher=True)
        if chapter_id:
            ch = db.execute("SELECT * FROM chapter WHERE id=? AND course_id=?",
                            (chapter_id, course_id)).fetchone()
            if not ch:
                raise ApiError(404, "NOT_FOUND", "Chapter not found")
        visibility = "teacher_only" if kind == "question_bank" else "students"
        fields = save_file(file_storage, kind)
        file_id, ts = insert_file_object(db, fields, user["id"])
        cursor = db.execute(
            "INSERT INTO resource(course_id,chapter_id,title,kind,visibility,archived,"
            "created_at,updated_at) VALUES(?,?,?,?,?,0,?,?)",
            (course_id, chapter_id, title, kind, visibility, ts, ts),
        )
        resource_id = cursor.lastrowid
        vcur = db.execute(
            "INSERT INTO resource_version(resource_id,version,file_id,change_note,created_at) "
            "VALUES(?,1,?,NULL,?)", (resource_id, file_id, ts))
        rv_id = vcur.lastrowid
        audit("resource.create", "resource", resource_id,
              after={"title": title, "kind": kind, "visibility": visibility})
        rv = db.execute(
            "SELECT rv.*,r.title,r.kind,f.size_bytes,f.sha256 "
            "FROM resource_version rv JOIN resource r ON r.id=rv.resource_id "
            "JOIN file_object f ON f.id=rv.file_id WHERE rv.id=?", (rv_id,)).fetchone()
    return result({"resource_id": resource_id, "version": 1, "id": rv["id"],
                   "title": rv["title"], "kind": rv["kind"],
                   "size": rv["size_bytes"], "sha256": rv["sha256"]}, 201)


# ---------- POST /resources/<id>/versions ----------
@bp.post("/resources/<int:resource_id>/versions")
def add_version(resource_id):
    user = require_user()
    file_storage = request.files.get("file")
    if not file_storage:
        raise ApiError(400, "VALIDATION_ERROR", "file required")
    change_note = request.form.get("change_note")
    if change_note is not None:
        change_note = text_field(change_note, "change_note", 0, 5000)
    with write() as db:
        resource, _ = load_resource(db, resource_id, teacher=True)
        fields = save_file(file_storage, resource["kind"])
        file_id, ts = insert_file_object(db, fields, user["id"])
        next_version = db.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM resource_version WHERE resource_id=?",
            (resource_id,)).fetchone()[0]
        cursor = db.execute(
            "INSERT INTO resource_version(resource_id,version,file_id,change_note,created_at) "
            "VALUES(?,?,?,?,?)", (resource_id, next_version, file_id, change_note, ts))
        db.execute("UPDATE resource SET updated_at=? WHERE id=?", (ts, resource_id))
        audit("resource.version_add", "resource_version", cursor.lastrowid,
              after={"resource_id": resource_id, "version": next_version})
    rv = db.execute(
        "SELECT rv.*,r.title,r.kind,f.size_bytes,f.sha256 "
        "FROM resource_version rv JOIN resource r ON r.id=rv.resource_id "
        "JOIN file_object f ON f.id=rv.file_id WHERE rv.id=?", (cursor.lastrowid,)).fetchone()
    return result(version_json(rv), 201)


# ---------- GET /resources/<id>/versions ----------
@bp.get("/resources/<int:resource_id>/versions")
def list_versions(resource_id):
    page, size = page_args()
    db = get_db()
    _resource, _ = load_resource(db, resource_id)
    total = db.execute("SELECT COUNT(*) FROM resource_version WHERE resource_id=?",
                       (resource_id,)).fetchone()[0]
    rows = db.execute(
        "SELECT rv.*,r.title,r.kind,f.size_bytes,f.sha256 "
        "FROM resource_version rv JOIN resource r ON r.id=rv.resource_id "
        "JOIN file_object f ON f.id=rv.file_id WHERE rv.resource_id=? "
        "ORDER BY rv.version DESC LIMIT ? OFFSET ?",
        (resource_id, size, (page - 1) * size)).fetchall()
    return paged([version_json(r) for r in rows], total, page, size)


# ---------- GET /courses/<id>/resources ----------
@bp.get("/courses/<int:course_id>/resources")
def list_resources(course_id):
    require_user()
    _course, role = course_access(course_id)
    q = request.args.get("q", "").strip()
    if len(q) > 100:
        raise ApiError(400, "VALIDATION_ERROR", "q too long")
    kind = request.args.get("kind")
    if kind and kind not in ("slides", "video", "guide", "question_bank"):
        raise ApiError(400, "VALIDATION_ERROR", "Invalid kind")
    chapter_id = request.args.get("chapter_id")
    chapter_id = positive_int(chapter_id, "chapter_id") if chapter_id else None
    page, size = page_args()
    where, params = " WHERE r.course_id=? AND r.archived=0", [course_id]
    if role == "student":
        where += " AND r.visibility='students' AND r.kind!='question_bank'"
    if kind:
        where += " AND r.kind=?"
        params.append(kind)
    if chapter_id:
        where += " AND r.chapter_id=?"
        params.append(chapter_id)
    if q:
        where += " AND r.title LIKE ?"
        params.append(f"%{q}%")
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM resource r" + where, params).fetchone()[0]
    rows = db.execute(
        "SELECT r.*, rv.id AS version_id, rv.version, f.size_bytes, f.sha256 "
        "FROM resource r LEFT JOIN resource_version rv ON rv.id="
        "(SELECT id FROM resource_version WHERE resource_id=r.id ORDER BY version DESC LIMIT 1) "
        "LEFT JOIN file_object f ON f.id=rv.file_id" + where +
        " ORDER BY r.id LIMIT ? OFFSET ?", (*params, size, (page - 1) * size)).fetchall()
    items = [{**resource_json(r), "latest_version_id": r["version_id"],
              "latest_version": r["version"], "size": r["size_bytes"],
              "sha256": r["sha256"]} for r in rows]
    return paged(items, total, page, size)


# ---------- GET /resource-versions/<id>/content ----------
@bp.get("/resource-versions/<int:version_id>/content")
def get_content(version_id):
    user = require_user()
    intent = request.args.get("intent")
    event_id = request.args.get("event_id", "")
    if intent not in ("view", "download"):
        raise ApiError(400, "VALIDATION_ERROR", "intent must be view or download")
    if not event_id:
        raise ApiError(400, "VALIDATION_ERROR", "event_id required")
    db = get_db()
    rv = db.execute(
        "SELECT rv.*,r.course_id,r.kind,r.visibility,r.archived,r.title "
        "FROM resource_version rv JOIN resource r ON r.id=rv.resource_id WHERE rv.id=?",
        (version_id,)).fetchone()
    if not rv or rv["archived"]:
        raise ApiError(404, "NOT_FOUND", "Resource version not found")
    _course, role = course_access(rv["course_id"])
    if role == "student" and (rv["visibility"] != "students" or rv["kind"] == "question_bank"):
        raise ApiError(404, "NOT_FOUND", "Resource version not found")
    if rv["kind"] == "question_bank" and intent != "download":
        raise ApiError(422, "INVALID_CIRCUIT", "Question bank is download-only")
    file_row = db.execute("SELECT * FROM file_object WHERE id=?", (rv["file_id"],)).fetchone()
    if not file_row:
        raise ApiError(404, "NOT_FOUND", "File not found")
    if intent == "view" and not file_row["media_type"].startswith(VIEWABLE_PREFIXES):
        raise ApiError(415, "PREVIEW_UNSUPPORTED", "Preview not supported for this type")
    file_path = upload_root() / file_row["storage_key"]
    if not file_path.is_file():
        raise ApiError(404, "NOT_FOUND", "File not found")
    as_attachment = intent == "download"
    download_name = file_row["original_name"]
    response = send_file(file_path, mimetype=file_row["media_type"],
                          as_attachment=as_attachment,
                          download_name=download_name if as_attachment else None,
                          conditional=True)
    # R39：仅成功提供内容的 200/206 计数；HEAD、304、416 及错误响应不记录事件
    if request.method == "HEAD" or response.status_code not in (200, 206):
        return response
    # 记录访问事件：先查后插，避免依赖 IntegrityError 回滚整个事务
    existing = db.execute(
        "SELECT event_type,resource_version_id FROM resource_event "
        "WHERE user_id=? AND event_id=?", (user["id"], event_id)).fetchone()
    if existing:
        if existing["event_type"] != intent or existing["resource_version_id"] != version_id:
            raise ApiError(409, "EVENT_CONFLICT",
                           "event_id already used with different intent or version")
    else:
        ts = stamp()
        rid = request_id()
        with write() as wdb:
            wdb.execute(
                "INSERT INTO resource_event(user_id,resource_version_id,event_type,event_id,"
                "request_id,created_at) VALUES(?,?,?,?,?,?)",
                (user["id"], version_id, intent, event_id, rid, ts))
            audit("resource.access", "resource_version", version_id,
                  after={"event_type": intent, "event_id": event_id})
    return response


# ---------- PATCH /resources/<id> ----------
@bp.patch("/resources/<int:resource_id>")
def update_resource(resource_id):
    require_user()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) - {"title", "visibility"}:
        raise ApiError(400, "VALIDATION_ERROR", "Expected title and/or visibility")
    title_raw = payload.get("title")
    visibility = payload.get("visibility")
    with write() as db:
        resource, _ = load_resource(db, resource_id, teacher=True)
        updates, ts = {}, stamp()
        if title_raw is not None:
            updates["title"] = text_field(title_raw, "title")
        if visibility is not None:
            if visibility not in ("students", "teacher_only"):
                raise ApiError(400, "VALIDATION_ERROR", "Invalid visibility")
            if resource["kind"] == "question_bank" and visibility == "students":
                raise ApiError(422, "VALIDATION_ERROR",
                               "question_bank cannot be visible to students")
            # 检查是否有 published 备课引用（简化：检查 preparation_resource）
            refs = db.execute(
                "SELECT pr.preparation_id FROM preparation_resource pr "
                "JOIN preparation p ON p.id=pr.preparation_id "
                "WHERE pr.resource_version_id IN "
                "(SELECT id FROM resource_version WHERE resource_id=?) "
                "AND p.status='published'", (resource_id,)).fetchall()
            if refs and visibility == "teacher_only":
                raise ApiError(409, "RESOURCE_IN_USE",
                               "Published preparation still references this resource")
            updates["visibility"] = visibility
        if not updates:
            raise ApiError(400, "VALIDATION_ERROR", "No fields to update")
        sets = ", ".join(f"{k}=?" for k in updates)
        db.execute(f"UPDATE resource SET {sets},updated_at=? WHERE id=?",
                   (*updates.values(), ts, resource_id))
        audit("resource.update", "resource", resource_id, after=updates)
        row = db.execute("SELECT * FROM resource WHERE id=?", (resource_id,)).fetchone()
    return result(resource_json(row))


# ---------- POST /resources/<id>/question-imports ----------
IMPORT_OPERATION = "resource_question_import"
MAX_IMPORT = 500


@bp.post("/resources/<int:resource_id>/question-imports")
def import_questions(resource_id):
    """题库导入：全量校验后同事务创建，禁止部分导入；同键重放原响应。"""
    user = require_user()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != {"resource_version_id"}:
        raise ApiError(400, "VALIDATION_ERROR", "Expected resource_version_id")
    version_id = positive_int(payload["resource_version_id"], "resource_version_id")
    key = attempt_model.idempotency_key(request.headers.get("Idempotency-Key"))
    request_hash = hashlib.sha256(json.dumps(
        {"resource_version_id": version_id}, sort_keys=True).encode()).hexdigest()
    with write() as db:
        require_tables(db, {"question", "question_version", "question_knowledge",
                            "idempotency_record"}, "题库模块未接入，暂不能导入")
        resource, _ = load_resource(db, resource_id, teacher=True)
        if resource["kind"] != "question_bank":
            raise ApiError(422, "VALIDATION_ERROR", "Only question_bank resources can be imported")
        rv = db.execute("SELECT rv.*,f.storage_key FROM resource_version rv "
                        "JOIN file_object f ON f.id=rv.file_id "
                        "WHERE rv.id=? AND rv.resource_id=?", (version_id, resource_id)).fetchone()
        if not rv:
            raise ApiError(404, "NOT_FOUND", "Resource version not found")
        at = stamp()
        previous = attempt_model.replay(db, user["id"], key, request_hash, at,
                                        operation=IMPORT_OPERATION)
        if previous:
            return current_app.response_class(previous["response_json"],
                                              mimetype="application/json"), previous["response_status"]
        # 读取题库源文件并解析
        file_path = upload_root() / rv["storage_key"]
        if not file_path.is_file():
            raise ApiError(404, "NOT_FOUND", "File not found")
        try:
            text = file_path.read_text(encoding="utf-8")
            items = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(400, "VALIDATION_ERROR", "File must be a UTF-8 JSON array") from exc
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_IMPORT:
            raise ApiError(400, "VALIDATION_ERROR", f"Expected 1-{MAX_IMPORT} questions in JSON array")
        # 全量校验：任何一题失败即返回 400 及下标，不创建任何题目
        validated = []
        for index, item in enumerate(items):
            try:
                values = validate_question(item)
                check_knowledge(db, resource["course_id"], values["knowledge_ids"])
            except ApiError as exc:
                raise ApiError(exc.status, exc.code,
                               f"题目[{index}]：{exc.message}") from exc
            validated.append(values)
        # 同事务创建题目与版本
        question_version_ids = [save_version(db, resource["course_id"], values)["version_id"]
                                for values in validated]
        cursor = db.execute(
            "INSERT INTO question_import(resource_version_id,actor_id,count,created_at) "
            "VALUES(?,?,?,?)", (version_id, user["id"], len(validated), at))
        import_id = cursor.lastrowid
        audit("resource.question_import", "question_import", import_id,
              after={"resource_version_id": version_id, "count": len(validated)})
        response, status = result({"import_id": import_id,
                                   "question_version_ids": question_version_ids,
                                   "count": len(validated)}, 201)
        attempt_model.save_response(db, user["id"], key, request_hash, import_id, response,
                                    status, operation=IMPORT_OPERATION,
                                    resource_type="question_import")
    return response, status
