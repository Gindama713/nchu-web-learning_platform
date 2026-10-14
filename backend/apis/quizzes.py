"""SPEC-008 dedicated publication; all quiz facts remain in SPEC-006 tables."""

from flask import Blueprint, request

from backend.apis.papers import list_papers
from backend.apis.questions import write_body
from backend.models import attempt, paper, quiz
from backend.models.question import identifier, invalid
from backend.shared.api import ApiError, result, stamp
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db, write

bp = Blueprint('quizzes', __name__)


@bp.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.get('/courses/<int:course_id>/quizzes')
def list_quizzes(course_id):
    return list_papers(course_id, quiz=True)


@bp.post('/courses/<int:course_id>/quizzes')
def publish_quiz(course_id):
    identifier(course_id)
    with write() as db:
        course_access(course_id, teacher=True)
        paper.ready(db)
        body = write_body()
        if 'paper_id' not in body:
            invalid('发布随堂测须指定paper_id')
        paper_id = identifier(body['paper_id'])
        row = paper.find(db, paper_id)
        if row['course_id'] != course_id:
            raise ApiError(404, 'NOT_FOUND', '随堂测不存在或不可见')
        paper.publish(db, row, {key: value for key, value in body.items() if key != 'paper_id'}, quiz=True)
        item = paper.metadata(db, paper.find(db, paper_id), teacher=True)
        item.update(paper_id=paper_id, status=item['window_state'])
    return result(item, 201)


@bp.get('/quizzes/<int:quiz_id>/statistics')
def quiz_statistics(quiz_id):
    require_user()
    if request.args:
        invalid('逐题统计不接受查询参数')
    db = get_db()
    db.execute('BEGIN')
    try:
        attempt.ready(db)
        row = paper.find(db, quiz_id)
        course_access(row['course_id'], teacher=True)
        item = quiz.statistics(db, row, stamp())
    finally:
        db.rollback()
    return result(item)


@bp.post('/quizzes/<int:quiz_id>/review')
def review_quiz(quiz_id):
    require_user()
    with write() as db:
        paper.ready(db)
        row = paper.find(db, quiz_id)
        course_access(row['course_id'], teacher=True)
        if request.args or (request.get_data() and write_body()):
            invalid('讲评不接受查询参数或业务字段')
        at = quiz.review(db, row, stamp())
    return result({'review_published_at': at})
