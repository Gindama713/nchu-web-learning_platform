"""SPEC-005 HTTP adapter. Missing SPEC-001 security fails closed.

Integration contract: app.extensions['course_security'] must provide
current_user_id() and verify_write_request() using the real server session,
session expiry/revocation, CSRF token and Origin checks. No fallback identity.
"""

import os
import sqlite3
from functools import wraps
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import HTTPException

from backend.models.knowledge import (
    KnowledgeError,
    KnowledgeStore,
    invalid,
    positive_id,
)

blueprint = Blueprint("knowledge", __name__, url_prefix="/api/v1")


def error_response(status, code, message):
    return jsonify(error={"code": code, "message": message, "details": {}}, request_id=uuid4().hex), status


@blueprint.errorhandler(KnowledgeError)
def business_error(error):
    return error_response(error.status, error.code, error.message)


@blueprint.errorhandler(HTTPException)
def http_error(error):
    return error_response(error.code, "UNSUPPORTED_MEDIA" if error.code == 415 else "VALIDATION_ERROR",
                          "请求格式不合法")


@blueprint.errorhandler(sqlite3.IntegrityError)
def integrity_error(error):
    current_app.logger.warning("Knowledge integrity constraint rejected a write")
    return error_response(409, "STATE_CONFLICT", "数据状态冲突，请刷新后重试")


def endpoint(function):
    @wraps(function)
    def dispatch(**kwargs):
        security = current_app.extensions.get("course_security")
        if security is None:
            raise KnowledgeError(503, "MAINTENANCE", "等待 SPEC-001 会话鉴权接入")
        user_id = security.current_user_id()
        if user_id is None:
            raise KnowledgeError(401, "UNAUTHENTICATED", "请先登录")
        positive_id(user_id)
        if request.method != "GET":
            security.verify_write_request()
        path = current_app.config.get("DATABASE_PATH") or os.environ.get("DATABASE_PATH", "instance/app.db")
        data, status, metadata = function(KnowledgeStore(path), user_id, **kwargs)
        result = jsonify(data=data, request_id=uuid4().hex, **metadata)
        result.headers["Cache-Control"] = "no-store"
        return result, status
    return dispatch


def query(allowed=()):
    keys = {"page", "page_size", *allowed}
    if set(request.args) - keys or any(len(request.args.getlist(key)) != 1 for key in request.args):
        invalid("查询参数不合法")
    def integer(key, default=None, maximum=None):
        raw = request.args.get(key)
        if raw is None:
            return default
        if not raw.isascii() or not raw.isdecimal() or int(raw) < 1 or (maximum and int(raw) > maximum):
            invalid("分页或章节参数不合法")
        return int(raw)
    return integer("page", 1), integer("page_size", 20, 100), integer("chapter_id")


@blueprint.get("/courses/<int:course_id>/chapters")
@endpoint
def chapters(store, user, course_id):
    page, size, _ = query()
    data, total, revision = store.chapters(user, course_id, page, size)
    return data, 200, {"page": page, "page_size": size, "total": total, "chapters_revision": revision}


@blueprint.post("/courses/<int:course_id>/chapters")
@endpoint
def add_chapter(store, user, course_id):
    return store.add_chapter(user, course_id, request.get_json()), 201, {}


@blueprint.patch("/chapters/<int:chapter_id>")
@endpoint
def rename_chapter(store, user, chapter_id):
    return store.rename_chapter(user, chapter_id, request.get_json()), 200, {}


@blueprint.put("/courses/<int:course_id>/chapter-order")
@endpoint
def chapter_order(store, user, course_id):
    return store.reorder(user, course_id, request.get_json()), 200, {}


@blueprint.post("/chapters/<int:chapter_id>/knowledge-points")
@endpoint
def create_knowledge(store, user, chapter_id):
    return store.save_knowledge(user, chapter_id, request.get_json(), create=True), 201, {}


@blueprint.patch("/knowledge-points/<int:knowledge_id>")
@endpoint
def update_knowledge(store, user, knowledge_id):
    return store.save_knowledge(user, knowledge_id, request.get_json()), 200, {}


@blueprint.get("/courses/<int:course_id>/knowledge-points")
@endpoint
def list_knowledge(store, user, course_id):
    page, size, chapter_id = query({"q", "chapter_id"})
    data, total = store.list_knowledge(user, course_id, page, size, request.args.get("q", ""), chapter_id)
    return data, 200, {"page": page, "page_size": size, "total": total}


@blueprint.get("/knowledge-points/<int:knowledge_id>")
@endpoint
def detail(store, user, knowledge_id):
    if request.args:
        invalid("详情接口不接受筛选参数")
    return store.detail(user, knowledge_id), 200, {}


@blueprint.put("/knowledge-points/<int:knowledge_id>/bookmark")
@endpoint
def bookmark(store, user, knowledge_id):
    return store.personal_state(user, knowledge_id, request.get_json(), "bookmark"), 200, {}


@blueprint.put("/knowledge-points/<int:knowledge_id>/progress")
@endpoint
def progress(store, user, knowledge_id):
    return store.personal_state(user, knowledge_id, request.get_json(), "progress"), 200, {}
