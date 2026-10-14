"""C04 fixed public objective practice and a projection of original error facts."""

import hashlib
import json
from pathlib import Path

from backend.models import attempt, question
from backend.shared.api import ApiError, audit

SQL = Path(__file__).resolve().parents[1] / 'migrations' / '006d_practice_wrong.sql'
VERSION = SQL.stem
CHECKSUM = hashlib.sha256(SQL.read_text(encoding='utf-8').encode()).hexdigest()
OPERATION = 'practice_attempt'


def ready(db):
    attempt.ready(db)
    row = db.execute('SELECT checksum FROM schema_migration WHERE version=?', (VERSION,)).fetchone()
    if not row or row[0] != CHECKSUM:
        raise ApiError(503, 'MAINTENANCE', '练习错题迁移尚未接入或校验失败')


def version(db, question_id, version_id):
    question.identifier(question_id)
    question.identifier(version_id)
    row = db.execute('SELECT v.*,q.course_id,q.archived FROM question_version v '
                     'JOIN question q ON q.id=v.question_id WHERE v.id=? AND q.id=?',
                     (version_id, question_id)).fetchone()
    if not row or row['archived']:
        raise ApiError(404, 'NOT_FOUND', '题目版本不存在或不可见')
    return row


def normalize(row, body):
    if set(body) != {'question_version_id', 'answer'}:
        question.invalid('练习仅接受question_version_id和answer')
    if row['type'] == 'short' or not row['practice_available']:
        raise ApiError(409, 'PRACTICE_UNAVAILABLE', '该固定版本未开放客观练习')
    return attempt.normalize_value(row, body['answer'])


def record_error(db, student_id, question_id, source, source_id):
    db.execute('INSERT INTO wrong_question(student_id,question_id,last_attempt_type,last_attempt_id,resolved) '
               'VALUES(?,?,?,?,0) ON CONFLICT(student_id,question_id) DO UPDATE SET '
               'last_attempt_type=excluded.last_attempt_type,last_attempt_id=excluded.last_attempt_id,resolved=0',
               (student_id, question_id, source, source_id))


def record_paper_errors(db, attempt_id, student_id):
    ready(db)
    for row in db.execute('SELECT v.question_id FROM answer f JOIN question_version v ON v.id=f.question_version_id '
                          "WHERE f.attempt_id=? AND f.answered=1 AND f.score_hundredths=0 AND v.type!='short'",
                          (attempt_id,)).fetchall():
        record_error(db, student_id, row['question_id'], 'paper', attempt_id)


def submit(db, row, student_id, value, at):
    score = attempt.grade({**dict(row), 'points_hundredths': 10000}, value)
    correct = score == 10000
    practice_id = db.execute('INSERT INTO practice_attempt(student_id,question_version_id,answer_json,answered,'
                             'correct,score_hundredths,created_at) VALUES(?,?,?,?,?,?,?)',
                             (student_id, row['id'], json.dumps(value, ensure_ascii=False, allow_nan=False),
                              int(value is not None), int(correct), score, at)).lastrowid
    if value is not None and not correct:
        record_error(db, student_id, row['question_id'], 'practice', practice_id)
    elif correct:
        db.execute('UPDATE wrong_question SET resolved=1 WHERE student_id=? AND question_id=?',
                   (student_id, row['question_id']))
    audit('practice.submit', 'practice_attempt', practice_id,
          after={'question_version_id': row['id'], 'answered': value is not None, 'correct': correct})
    return {'attempt_id': practice_id, 'question_version_id': row['id'], 'correct': correct,
            'score': score / 100, 'explanation': row['explanation']}


# Unified historical errors; counts are derived, never incremented on idempotent replay.
ERRORS = ("SELECT a.student_id,v.question_id,f.question_version_id,'paper' AS source,a.id AS source_id "
          'FROM answer f JOIN attempt a ON a.id=f.attempt_id JOIN question_version v ON v.id=f.question_version_id '
          "WHERE f.answered=1 AND f.score_hundredths=0 AND v.type!='short' UNION ALL "
          "SELECT p.student_id,v.question_id,p.question_version_id,'practice',p.id "
          'FROM practice_attempt p JOIN question_version v ON v.id=p.question_version_id '
          'WHERE p.answered=1 AND p.correct=0')


def wrong_item(db, row, at):
    item = question.model(db, row, teacher=False)
    reserved = False
    try:
        question.ensure_practice_unreserved(db, [row['question_id']], at=at)
    except ApiError as error:
        if error.code != 'QUESTION_RESERVED':
            raise
        reserved = True
    # Course permission was checked by the listing; historical paper access also
    # requires the original frozen participant and actual review time.
    if row['last_attempt_type'] == 'practice':
        visible = bool(row['practice_available'])
    else:
        visible = bool(db.execute('SELECT 1 FROM attempt a JOIN paper p ON p.id=a.paper_id '
                                  'JOIN paper_participant pp ON pp.paper_id=p.id AND pp.student_id=a.student_id '
                                  "WHERE a.id=? AND p.status='published' AND p.review_at IS NOT NULL AND p.review_at<=?",
                                  (row['last_attempt_id'], at)).fetchone())
    visible = visible and not reserved
    item.update(question_id=row['question_id'], question_version_id=row['id'],
                last_attempt_type=row['last_attempt_type'], last_attempt_id=row['last_attempt_id'],
                wrong_count=row['wrong_count'], resolved=bool(row['resolved']), answer_visible=visible,
                can_practice=bool(row['practice_available'] and not row['archived'] and not reserved))
    if visible:
        item.update(answer=json.loads(row['answer_json']), explanation=row['explanation'])
    return item
