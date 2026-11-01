"""C03a paper acceptance and quiz alias share one transaction and success snapshot."""

from flask import Blueprint, current_app, request

from backend.apis.questions import query_integer, write_body
from backend.models import attempt, paper
from backend.models.question import MAX_ID, identifier, invalid
from backend.shared.api import ApiError, paged, result, stamp
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db, write

bp = Blueprint('attempts', __name__)


@bp.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.post('/papers/<int:paper_id>/attempts')
@bp.post('/quizzes/<int:paper_id>/attempts')
def submit_paper(paper_id):
    user = require_user()
    with write() as db:
        attempt.ready(db)
        row = paper.find(db, paper_id)
        _, role = course_access(row['course_id'])
        if request.path.startswith('/api/v1/quizzes/') and row['kind'] != 'quiz':
            raise ApiError(404, 'NOT_FOUND', '随堂测不存在或不可见')
        if role != 'student':
            raise ApiError(403, 'FORBIDDEN', '仅学生可交卷')
        if row['status'] != 'published' or not db.execute(
                'SELECT 1 FROM paper_participant WHERE paper_id=? AND student_id=?', (paper_id, user['id'])).fetchone():
            raise ApiError(404, 'NOT_FOUND', '试卷不存在或不可见')
        body = write_body()
        key = attempt.idempotency_key(request.headers.get('Idempotency-Key'))
        rows = attempt.items(db, paper_id)
        answers = attempt.normalize_answers(rows, body)
        request_hash = attempt.fingerprint(paper_id, answers)
        at = stamp()
        previous = attempt.replay(db, user['id'], key, request_hash, at)
        if previous:
            response = current_app.response_class(previous['response_json'], mimetype='application/json')
            status = previous['response_status']
        else:
            attempt_id = attempt.submit(db, row, user['id'], rows, answers, at)
            response, status = result(attempt.detail(db, attempt.find(db, attempt_id), at=at), 201)
            attempt.save_response(db, user['id'], key, request_hash, attempt_id, response, status)
    return response, status


def authorize(row, user_id):
    _, role = course_access(row['course_id'])
    if role == 'student' and (row['student_id'] != user_id or row['paper_status'] != 'published' or not get_db().execute(
            'SELECT 1 FROM paper_participant WHERE paper_id=? AND student_id=?', (row['paper_id'], user_id)).fetchone()):
        raise ApiError(404, 'NOT_FOUND', '答卷不存在或不可见')
    return role


@bp.get('/attempts/<int:attempt_id>')
def get_attempt(attempt_id):
    user = require_user()
    if request.args:
        invalid('详情不接受查询参数')
    db = get_db()
    db.execute('BEGIN')
    try:
        attempt.ready(db)
        row = attempt.find(db, attempt_id)
        role = authorize(row, user['id'])
        data = attempt.detail(db, row, teacher=role == 'teacher')
    finally:
        db.rollback()
    return result(data)


@bp.patch('/attempts/<int:attempt_id>/manual-scores')
def grade_attempt(attempt_id):
    user = require_user()
    with write() as db:
        attempt.ready(db)
        row = attempt.find(db, attempt_id)
        course_access(row['course_id'], teacher=True)
        data = attempt.manual_scores(db, row, write_body(), user['id'])
    return result(data)


@bp.get('/courses/<int:course_id>/attempts')
def list_attempts(course_id):
    identifier(course_id)
    user = require_user()
    if set(request.args) - {'page', 'page_size', 'paper_id', 'student_id', 'status'} or any(
            len(request.args.getlist(key)) != 1 for key in request.args):
        invalid('查询参数不合法或重复')
    page, size = query_integer('page', 1), query_integer('page_size', 20)
    if size > 100 or (page - 1) * size > MAX_ID:
        invalid('分页超出允许范围')
    where, args = ['p.course_id=?'], [course_id]
    for field in ('paper_id', 'student_id'):
        value = query_integer(field)
        if value is not None:
            where.append(f'a.{field}=?')
            args.append(value)
    status = request.args.get('status')
    if status is not None:
        if status not in {'partial', 'graded'}:
            invalid('答卷状态不合法')
        where.append('a.status=?')
        args.append(status)
    db = get_db()
    db.execute('BEGIN')
    try:
        _, role = course_access(course_id)
        attempt.ready(db)
        if role == 'student':
            where.extend(['a.student_id=?', "p.status='published'", ('EXISTS(SELECT 1 FROM paper_participant pp '
                          'WHERE pp.paper_id=p.id AND pp.student_id=a.student_id)')])
            args.append(user['id'])
        base = 'FROM attempt a JOIN paper p ON p.id=a.paper_id WHERE ' + ' AND '.join(where)
        total = db.execute(f'SELECT count(*) {base}', args).fetchone()[0]
        rows = db.execute(f'SELECT a.*,p.review_at {base} ORDER BY a.id DESC LIMIT ? OFFSET ?',
                          (*args, size, (page - 1) * size)).fetchall()
        at = stamp()
        data = [attempt.detail(db, row, teacher=role == 'teacher', at=at) for row in rows]
    finally:
        db.rollback()
    return paged(data, total, page, size)
