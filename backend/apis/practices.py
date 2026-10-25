"""Student-only public practice and personal wrong questions, with current access."""

from flask import Blueprint, current_app, request

from backend.apis.questions import query_integer, write_body
from backend.models import attempt, practice
from backend.models.question import (
    MAX_ID,
    ensure_practice_unreserved,
    identifier,
    invalid,
)
from backend.shared.api import ApiError, paged, result, stamp
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db, write

bp = Blueprint('practices', __name__)


@bp.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


def student():
    user = require_user()
    if user['role'] != 'student':
        raise ApiError(403, 'FORBIDDEN', '仅学生可访问个人练习和错题')
    return user


@bp.post('/questions/<int:question_id>/practice-attempts')
def submit_practice(question_id):
    user = student()
    with write() as db:
        practice.ready(db)
        body = write_body()
        if set(body) != {'question_version_id', 'answer'}:
            invalid('练习仅接受question_version_id和answer')
        row = practice.version(db, question_id, body['question_version_id'])
        course_access(row['course_id'])
        value = practice.normalize(row, body)
        key = attempt.idempotency_key(request.headers.get('Idempotency-Key'))
        at = stamp()
        # Recheck before replay as well: a saved explanation must never bypass
        # current identity-level protection in anomalous legacy data.
        ensure_practice_unreserved(db, [question_id], at=at)
        request_hash = attempt.fingerprint(question_id, [{'question_version_id': row['id'], 'value': value}])
        previous = attempt.replay(db, user['id'], key, request_hash, at, operation=practice.OPERATION)
        if previous:
            response = current_app.response_class(previous['response_json'], mimetype='application/json')
            status = previous['response_status']
        else:
            data = practice.submit(db, row, user['id'], value, at)
            response, status = result(data, 201)
            attempt.save_response(db, user['id'], key, request_hash, data['attempt_id'], response, status,
                                  operation=practice.OPERATION, resource_type='practice_attempt')
    return response, status


@bp.get('/users/me/wrong-questions')
def list_wrong():
    user = student()
    if set(request.args) - {'page', 'page_size', 'knowledge_id'} or any(
            len(request.args.getlist(key)) != 1 for key in request.args):
        invalid('错题查询参数不合法或重复')
    page, size = query_integer('page', 1), query_integer('page_size', 20)
    if size > 100 or (page - 1) * size > MAX_ID:
        invalid('分页超出允许范围')
    knowledge_id = query_integer('knowledge_id')
    where, args = ['w.student_id=?', "m.active=1 AND m.member_role='student'"], [user['id']]
    if knowledge_id is not None:
        identifier(knowledge_id)
        where.append('EXISTS(SELECT 1 FROM question_knowledge k WHERE k.question_version_id=v.id AND k.knowledge_id=?)')
        args.append(knowledge_id)
    base = (f'FROM wrong_question w JOIN ({practice.ERRORS}) e ON e.student_id=w.student_id '
            'AND e.question_id=w.question_id AND e.source=w.last_attempt_type AND e.source_id=w.last_attempt_id '
            'JOIN question_version v ON v.id=e.question_version_id JOIN question q ON q.id=w.question_id '
            'JOIN course_member m ON m.course_id=q.course_id AND m.user_id=w.student_id WHERE ' + ' AND '.join(where))
    db = get_db()
    db.execute('BEGIN')
    try:
        require_user()
        practice.ready(db)
        total = db.execute(f'SELECT count(*) {base}', args).fetchone()[0]
        rows = db.execute(f'SELECT v.*,q.archived,w.last_attempt_type,w.last_attempt_id,w.resolved,'
                          f'(SELECT count(*) FROM ({practice.ERRORS}) errors WHERE errors.student_id=w.student_id '
                          f'AND errors.question_id=w.question_id) AS wrong_count {base} '
                          'ORDER BY w.id DESC LIMIT ? OFFSET ?', (*args, size, (page - 1) * size)).fetchall()
        at = stamp()
        data = [practice.wrong_item(db, row, at) for row in rows]
    finally:
        db.rollback()
    return paged(data, total, page, size)
