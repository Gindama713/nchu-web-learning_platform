"""Student's online, uncached recommendations; no dependency on analytics HTTP."""

import sqlite3

from flask import Blueprint, request

from backend.models import recommendation as model
from backend.models.question import identifier
from backend.shared.api import ApiError, positive_int, result, stamp
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db

bp = Blueprint('recommendations', __name__)


@bp.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


def authorize(course_id):
    user = require_user()
    if user['role'] != 'student':
        raise ApiError(403, 'FORBIDDEN', '仅学生可读取本人推荐')
    course_access(course_id)
    return user


def read_snapshot(db, course_id, cutoff):
    db.execute('BEGIN')
    try:
        user = authorize(course_id)
        return model.extract(db, course_id, user['id'], cutoff)
    finally:
        db.rollback()


@bp.get('/courses/<int:course_id>/recommendations')
def recommendations(course_id):
    identifier(course_id)
    authorize(course_id)  # Prime the shared session before opening a read transaction.
    args = request.args
    if set(args) - {'limit'} or any(len(args.getlist(key)) != 1 or len(args[key]) > 2 for key in args):
        raise ApiError(400, 'VALIDATION_ERROR', '推荐仅接受一个limit参数')
    limit = positive_int(args.get('limit', '5'), 'limit')
    if limit > 20:
        raise ApiError(400, 'VALIDATION_ERROR', 'limit须为1至20')
    db = get_db()
    try:
        for _ in range(3):
            cutoff = stamp()
            snapshot = read_snapshot(db, course_id, cutoff)
            try:
                data = model.calculate(snapshot, limit)
            except Exception as exc:
                raise ApiError(503, 'RECOMMENDATION_UNAVAILABLE', '推荐暂不可用，请重试') from exc
            # Recheck both identity and current facts after calculation. No stale
            # published knowledge, foundation flag, progress or practice entry.
            if snapshot == read_snapshot(db, course_id, cutoff):
                return result(data)
    except sqlite3.Error as exc:
        raise ApiError(503, 'RECOMMENDATION_UNAVAILABLE', '推荐事实暂不可用，请重试') from exc
    raise ApiError(503, 'RECOMMENDATION_UNAVAILABLE', '学习数据持续变化，请重试')
