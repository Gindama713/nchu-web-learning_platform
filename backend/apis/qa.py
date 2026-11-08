"""SPEC-011 HTTP adapter reusing the current SPEC-001/005 security contract."""

import os
import sqlite3
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import HTTPException

from backend.apis.knowledge import business_error, http_error
from backend.apis.knowledge_security import security_for_request
from backend.models.knowledge import KnowledgeError, invalid
from backend.models.qa import QAStore

blueprint = Blueprint("qa", __name__, url_prefix="/api/v1")
blueprint.register_error_handler(KnowledgeError, business_error)
blueprint.register_error_handler(HTTPException, http_error)


@blueprint.post("/courses/<int:course_id>/qa")
def ask(course_id):
    security = security_for_request()
    user_id = security.current_user_id()
    if user_id is None:
        raise KnowledgeError(401, "UNAUTHENTICATED", "请先登录")
    security.verify_write_request()
    if request.args:
        invalid("问答接口不接受查询参数")
    path = current_app.config.get("DATABASE_PATH") or os.environ.get("DATABASE_PATH", "instance/app.db")
    store = QAStore(path, security.verify_transaction, current_app.extensions["qa_cache"])
    try:
        data = store.ask(user_id, course_id, request.get_json())
    except sqlite3.Error as error:
        raise KnowledgeError(503, "INDEX_UNAVAILABLE", "检索记录暂时无法保存，请稍后重试") from error
    result = jsonify(data=data, request_id=uuid4().hex)
    result.headers["Cache-Control"] = "no-store"
    return result
