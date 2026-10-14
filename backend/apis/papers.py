"""C02b ordinary paper routes; quiz publication belongs to C05."""

from flask import Blueprint, request

from backend.apis.questions import query_integer, write_body
from backend.models import paper
from backend.models.question import MAX_ID, identifier, invalid
from backend.shared.api import ApiError, paged, result, stamp
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db, write

bp = Blueprint('papers', __name__)


@bp.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.post('/courses/<int:course_id>/papers')
def create_paper(course_id):
    identifier(course_id)
    with write() as db:
        course_access(course_id, teacher=True)
        paper.ready(db)
        paper_id = paper.create(db, course_id, write_body())
        item = paper.detail(db, paper.find(db, paper_id), teacher=True)
    return result(item, 201)


@bp.post('/papers/<int:paper_id>/publish')
def publish_paper(paper_id):
    require_user()
    with write() as db:
        paper.ready(db)
        row = paper.find(db, paper_id)
        course_access(row['course_id'], teacher=True)
        paper.publish(db, row, write_body())
        item = paper.detail(db, paper.find(db, paper_id), teacher=True)
    return result(item)


@bp.get('/papers/<int:paper_id>')
def get_paper(paper_id):
    user = require_user()
    if request.args:
        invalid('详情不接受查询参数')
    db = get_db()
    db.execute('BEGIN')
    try:
        paper.ready(db)
        row = paper.find(db, paper_id)
        _, role = course_access(row['course_id'])
        if role == 'student' and (row['status'] != 'published' or not db.execute(
                'SELECT 1 FROM paper_participant WHERE paper_id=? AND student_id=?', (paper_id, user['id'])).fetchone()):
            raise ApiError(404, 'NOT_FOUND', '试卷不存在或不可见')
        item = paper.detail(db, row, teacher=role == 'teacher')
    finally:
        db.rollback()
    return result(item)


@bp.get('/courses/<int:course_id>/papers')
def list_papers(course_id):
    identifier(course_id)
    user = require_user()
    if set(request.args) - {'page', 'page_size', 'kind', 'status'} or any(
            len(request.args.getlist(key)) != 1 for key in request.args):
        invalid('查询参数不合法或重复')
    page, size = query_integer('page', 1), query_integer('page_size', 20)
    if size > 100 or (page - 1) * size > MAX_ID:
        invalid('分页超出允许范围')
    where, args = ['p.course_id=?'], [course_id]
    for name, allowed in (('kind', paper.KINDS), ('status', {'draft', 'published'})):
        value = request.args.get(name)
        if value is not None:
            if value not in allowed:
                invalid('试卷类型或状态不合法')
            where.append(f'p.{name}=?')
            args.append(value)
    db = get_db()
    db.execute('BEGIN')
    try:
        _, role = course_access(course_id)
        paper.ready(db)
        if role == 'student':
            where.extend(["p.status='published'", ('EXISTS(SELECT 1 FROM paper_participant pp '
                          'WHERE pp.paper_id=p.id AND pp.student_id=?)')])
            args.append(user['id'])
        base = 'FROM paper p WHERE ' + ' AND '.join(where)
        total = db.execute(f'SELECT count(*) {base}', args).fetchone()[0]
        rows = db.execute(f'SELECT p.* {base} ORDER BY p.id LIMIT ? OFFSET ?',
                          (*args, size, (page - 1) * size)).fetchall()
        at = stamp()
        items = [paper.metadata(db, row, teacher=role == 'teacher', at=at) for row in rows]
    finally:
        db.rollback()
    return paged(items, total, page, size)
