"""C02a question routes using SPEC-001 identity, CSRF and transaction helpers."""

from flask import Blueprint, request

from backend.models.question import (
    DIFFICULTIES,
    MAX_ID,
    TYPES,
    ensure_practice_unreserved,
    identifier,
    invalid,
    latest,
    model,
    ready,
    save_version,
    validate_question,
)
from backend.shared.api import audit, paged, result
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db, write

bp = Blueprint('questions', __name__)


@bp.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


def write_body():
    if request.args:
        invalid('写请求不接受查询参数')
    body = request.get_json(silent=True)
    if type(body) is not dict:
        invalid('请求须为JSON对象')
    return body


def query_integer(name, default=None):
    value = request.args.get(name)
    if value is None:
        return default
    if len(value) > 19 or not value.isascii() or not value.isdecimal():
        invalid('分页或知识点ID不合法')
    return identifier(int(value))


@bp.post('/courses/<int:course_id>/questions')
def create_question(course_id):
    identifier(course_id)
    with write() as db:
        course_access(course_id, teacher=True)
        ready(db)
        values = validate_question(write_body())
        item = save_version(db, course_id, values)
        audit('question.create', 'question', item['id'], after={'version_id': item['version_id']})
    return result(item, 201)


@bp.patch('/questions/<int:question_id>')
def update_question(question_id):
    identifier(question_id)
    with write() as db:
        ready(db)
        current = latest(db, question_id)
        course_access(current['course_id'], teacher=True)
        values = validate_question(write_body(), model(db, current))
        item = save_version(db, current['course_id'], values, current)
        audit('question.version', 'question', item['id'], before={'version_id': current['id']},
              after={'version_id': item['version_id']})
    return result(item)


@bp.get('/courses/<int:course_id>/questions')
def list_questions(course_id):
    identifier(course_id)
    require_user()
    if set(request.args) - {'page', 'page_size', 'type', 'difficulty', 'knowledge_id'}:
        invalid('查询参数不合法')
    if any(len(request.args.getlist(key)) != 1 for key in request.args):
        invalid('查询参数不能重复')
    page, size = query_integer('page', 1), query_integer('page_size', 20)
    if size > 100 or (page - 1) * size > MAX_ID:
        invalid('分页超出允许范围')
    knowledge_id = query_integer('knowledge_id')
    where, args = ['q.course_id=?', 'q.archived=0',
                   'v.version=(SELECT MAX(v2.version) FROM question_version v2 WHERE v2.question_id=q.id)'], [course_id]
    for name, allowed in (('type', TYPES), ('difficulty', DIFFICULTIES)):
        value = request.args.get(name)
        if value is not None:
            if value not in allowed:
                invalid('题型或难度不合法')
            where.append(f'v.{name}=?')
            args.append(value)
    if knowledge_id is not None:
        where.append('EXISTS(SELECT 1 FROM question_knowledge k WHERE k.question_version_id=v.id AND k.knowledge_id=?)')
        args.append(knowledge_id)
    db = get_db()
    db.execute('BEGIN')
    try:
        _, role = course_access(course_id)
        ready(db)
        if role == 'student':
            where.append('v.practice_available=1')
        base = 'FROM question q JOIN question_version v ON v.question_id=q.id WHERE ' + ' AND '.join(where)
        total = db.execute(f'SELECT count(*) {base}', args).fetchone()[0]
        rows = db.execute(f'SELECT v.* {base} ORDER BY q.id LIMIT ? OFFSET ?',
                          (*args, size, (page - 1) * size)).fetchall()
        if role == 'student' and rows:
            ensure_practice_unreserved(db, [row['question_id'] for row in rows])
        items = [model(db, row, teacher=role == 'teacher') for row in rows]
    finally:
        db.rollback()
    return paged(items, total, page, size)
