"""SPEC-008 dedicated publication; all quiz facts remain in SPEC-006 tables."""

from flask import Blueprint

from backend.apis.papers import list_papers
from backend.apis.questions import write_body
from backend.models import paper
from backend.models.question import identifier, invalid
from backend.shared.api import ApiError, result
from backend.shared.auth import course_access
from backend.shared.db import write

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
