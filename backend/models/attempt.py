"""C03a frozen-version validation, objective grading and APIC 11 acceptance."""

import hashlib
import json
from datetime import timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from uuid import UUID

from backend.models import paper
from backend.models.question import (
    MAX_ID,
    ensure_practice_unreserved,
    identifier,
    invalid,
    number,
)
from backend.shared.api import ApiError, audit, now, stamp

SQL = Path(__file__).resolve().parents[1] / 'migrations' / '006c_attempts.sql'
VERSION = SQL.stem
CHECKSUM = hashlib.sha256(SQL.read_text(encoding='utf-8').encode()).hexdigest()
OPERATION = 'paper_attempt'


def ready(db):
    paper.ready(db)
    row = db.execute('SELECT checksum FROM schema_migration WHERE version=?', (VERSION,)).fetchone()
    if not row or row[0] != CHECKSUM:
        raise ApiError(503, 'MAINTENANCE', '作答迁移尚未接入或校验失败')


def idempotency_key(value):
    if type(value) is not str or len(value) != 36:
        invalid('Idempotency-Key须为UUID')
    try:
        parsed = UUID(value)
    except ValueError:
        invalid('Idempotency-Key须为UUID')
    if str(parsed) != value.lower():
        invalid('Idempotency-Key须为UUID')
    return str(parsed)


def items(db, paper_id):
    return db.execute('SELECT v.*,i.points_hundredths,i.position FROM paper_item i '
                      'JOIN question_version v ON v.id=i.question_version_id '
                      'WHERE i.paper_id=? ORDER BY i.position', (paper_id,)).fetchall()


def normalize_value(row, value):
    if value is None:
        return None
    kind = row['type']
    if kind == 'single':
        keys = {item['key'] for item in json.loads(row['options_json'])}
        if type(value) is not str or value not in keys:
            invalid('单选作答须为已定义key')
    elif kind == 'multiple':
        keys = {item['key'] for item in json.loads(row['options_json'])}
        if (type(value) is not list or any(type(key) is not str for key in value)
                or len(set(value)) != len(value) or not set(value) <= keys):
            invalid('多选作答须为不重复的已定义key数组')
        return sorted(value) if value else None
    elif kind == 'boolean':
        if type(value) is not bool:
            invalid('判断作答须为JSON布尔')
    elif kind == 'numeric':
        number(value, 'value')
    elif kind == 'short':
        if type(value) is not str:
            invalid('简答作答须为文本')
        value = value.strip()
        if len(value) > 5000:
            invalid('简答作答最多5000字符')
        return value or None
    return value


def normalize_answers(rows, body):
    if set(body) != {'answers'} or type(body['answers']) is not list:
        invalid('提交仅接受answers数组')
    versions = {row['id']: row for row in rows}
    values = {}
    for item in body['answers']:
        if type(item) is not dict or set(item) != {'question_version_id', 'value'}:
            invalid('作答条目仅接受question_version_id和value')
        version_id = identifier(item['question_version_id'])
        if version_id not in versions or version_id in values:
            invalid('版本须属于本卷且不能重复')
        values[version_id] = normalize_value(versions[version_id], item['value'])
    # Omitted and explicit unanswered values describe the same full paper submission.
    return [{'question_version_id': row['id'], 'value': values.get(row['id'])}
            for row in sorted(rows, key=lambda item: item['id'])]


def fingerprint(paper_id, answers):
    normalized = []
    for item in answers:
        value = item['value']
        # JSON 1 and 1.0 have the same numeric meaning; bool must remain distinct.
        if type(value) in (int, float):
            decimal = Decimal(str(value))
            canonical = format(decimal, 'f')
            if '.' in canonical:
                canonical = canonical.rstrip('0').rstrip('.')
            value = {'number': '0' if decimal == 0 else canonical}
        normalized.append({**item, 'value': value})
    data = json.dumps({'paper_id': paper_id, 'answers': normalized}, sort_keys=True,
                      ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()


def replay(db, user_id, key, request_hash, at):
    row = db.execute('SELECT * FROM idempotency_record WHERE user_id=? AND operation=? AND key=?',
                     (user_id, OPERATION, key)).fetchone()
    if row and row['expires_at'] > at:
        if row['request_hash'] != request_hash:
            raise ApiError(409, 'IDEMPOTENCY_CONFLICT', '同一幂等键已用于其他内容')
        return row
    if row:
        db.execute('DELETE FROM idempotency_record WHERE id=?', (row['id'],))
    return None


def grade(row, value):
    if value is None:
        return 0
    kind = row['type']
    if kind == 'short':
        return None
    expected = json.loads(row['answer_json'])
    if kind == 'multiple':
        correct = set(value) == set(expected)
    elif kind == 'numeric':
        # Finite JSON floats/accepted ints span at most ~633 decimal places.
        with localcontext() as context:
            context.prec = 1100
            correct = abs(Decimal(str(value)) - Decimal(str(expected))) <= Decimal(str(row['tolerance']))
    else:
        correct = value == expected
    return row['points_hundredths'] if correct else 0


def submit(db, row, user_id, rows, answers, at):
    """Caller holds the shared write transaction and checked auth, syntax, then replay."""
    if not row['start_at'] <= at < row['end_at']:
        raise ApiError(409, 'WINDOW_CLOSED', '当前不在作答窗口内')
    if db.execute('SELECT 1 FROM attempt WHERE paper_id=? AND student_id=?', (row['id'], user_id)).fetchone():
        raise ApiError(409, 'ALREADY_SUBMITTED', '每人每卷只能提交一次')
    values = {item['question_version_id']: item['value'] for item in answers}
    scored = [(item, values[item['id']], grade(item, values[item['id']])) for item in rows]
    partial = sum(score for _, _, score in scored if score is not None)
    pending = any(score is None for _, _, score in scored)
    attempt_id = db.execute('INSERT INTO attempt(paper_id,student_id,status,score_hundredths,'
                            'partial_score_hundredths,submitted_at) VALUES(?,?,?,?,?,?)',
                            (row['id'], user_id, 'partial' if pending else 'graded',
                             None if pending else partial, partial, at)).lastrowid
    db.executemany('INSERT INTO answer(attempt_id,question_version_id,value_json,score_hundredths,answered) '
                   'VALUES(?,?,?,?,?)', [(attempt_id, item['id'], json.dumps(value, ensure_ascii=False, allow_nan=False),
                                        score, int(value is not None)) for item, value, score in scored])
    # Answers are the authoritative C04 wrong-question inputs; no duplicate mutable fact table here.
    audit('attempt.submit', 'attempt', attempt_id,
          after={'paper_id': row['id'], 'status': 'partial' if pending else 'graded', 'answer_count': len(rows)})
    return attempt_id


def save_response(db, user_id, key, request_hash, attempt_id, response, status):
    db.execute('INSERT INTO idempotency_record(user_id,operation,key,request_hash,resource_type,resource_id,'
               'response_status,response_json,expires_at) VALUES(?,?,?,?,?,?,?,?,?)',
               (user_id, OPERATION, key, request_hash, 'attempt', attempt_id, status,
                response.get_data(as_text=True), stamp(now() + timedelta(hours=24))))


def find(db, attempt_id):
    identifier(attempt_id)
    row = db.execute('SELECT a.*,p.course_id,p.status AS paper_status,p.review_at FROM attempt a '
                     'JOIN paper p ON p.id=a.paper_id WHERE a.id=?', (attempt_id,)).fetchone()
    if not row:
        raise ApiError(404, 'NOT_FOUND', '答卷不存在或不可见')
    return row


def manual_scores(db, row, body, actor_id):
    """Validate the entire batch before updating facts in the caller's write transaction."""
    if set(body) != {'revision', 'items'} or type(body['revision']) is not int or not 0 <= body['revision'] < MAX_ID:
        invalid('批阅须带合法revision和items')
    if type(body['items']) is not list or not body['items']:
        invalid('批阅items须为非空数组')
    normalized, seen = [], set()
    for item in body['items']:
        if type(item) is not dict or set(item) != {'question_version_id', 'score', 'comment'}:
            invalid('批阅条目仅接受question_version_id、score和comment')
        version_id = identifier(item['question_version_id'])
        if version_id in seen:
            invalid('批阅题号不能重复')
        seen.add(version_id)
        number(item['score'], 'score')
        score = Decimal(str(item['score']))
        if score < 0:
            invalid('评分须为非负数')
        with localcontext() as context:
            context.prec = 1100
            scaled = score * 100
        if scaled != scaled.to_integral_value():
            invalid('评分最多两位小数')
        if type(item['comment']) is not str or len(item['comment']) > 1000:
            invalid('评语须为0至1000字符文本')
        normalized.append((version_id, int(scaled), item['comment']))
    facts = {item['question_version_id']: item for item in db.execute(
        'SELECT a.*,v.type,i.points_hundredths FROM answer a '
        'JOIN question_version v ON v.id=a.question_version_id '
        'JOIN paper_item i ON i.paper_id=? AND i.question_version_id=a.question_version_id '
        'WHERE a.attempt_id=?', (row['paper_id'], row['id']))}
    for version_id, score, _ in normalized:
        fact = facts.get(version_id)
        if not fact or fact['type'] != 'short' or not fact['answered'] or score > fact['points_hundredths']:
            raise ApiError(422, 'INVALID_MANUAL_SCORE', '仅可批阅本卷已作答简答，且分数不能超过配分')
    if body['revision'] != row['revision']:
        raise ApiError(409, 'REVISION_CONFLICT', '答卷评分已变化，请重新加载后批阅')
    before = [{'question_version_id': version_id, 'score_hundredths': facts[version_id]['score_hundredths'],
               'comment': facts[version_id]['comment'], 'graded_by': facts[version_id]['graded_by']}
              for version_id, _, _ in normalized]
    db.executemany('UPDATE answer SET score_hundredths=?,comment=?,graded_by=? '
                   'WHERE attempt_id=? AND question_version_id=?',
                   [(score, comment, actor_id, row['id'], version_id) for version_id, score, comment in normalized])
    summary = db.execute('SELECT coalesce(sum(score_hundredths),0) AS partial,'
                          'sum(score_hundredths IS NULL) AS pending FROM answer WHERE attempt_id=?',
                          (row['id'],)).fetchone()
    partial, pending = summary['partial'], summary['pending']
    updated = db.execute('UPDATE attempt SET status=?,score_hundredths=?,partial_score_hundredths=?,revision=revision+1 '
                         'WHERE id=? AND revision=?', ('partial' if pending else 'graded',
                         None if pending else partial, partial, row['id'], body['revision']))
    if updated.rowcount != 1:
        raise ApiError(409, 'REVISION_CONFLICT', '答卷评分已变化，请重新加载后批阅')
    audit('attempt.manual_scores', 'attempt', row['id'],
          before={'revision': row['revision'], 'items': before},
          after={'revision': row['revision'] + 1, 'items': [
              {'question_version_id': version_id, 'score_hundredths': score, 'comment': comment, 'graded_by': actor_id}
              for version_id, score, comment in normalized], 'status': 'partial' if pending else 'graded',
              'partial_score_hundredths': partial}, actor_id=actor_id)
    return detail(db, find(db, row['id']), teacher=True)


def detail(db, row, *, teacher=False, at=None):
    at = at or stamp()
    rows = db.execute('SELECT a.*,v.question_id,v.type,v.answer_json,v.explanation,i.points_hundredths '
                      'FROM answer a JOIN question_version v ON v.id=a.question_version_id '
                      'JOIN paper_item i ON i.paper_id=? AND i.question_version_id=a.question_version_id '
                      'WHERE a.attempt_id=? ORDER BY i.position', (row['paper_id'], row['id'])).fetchall()
    visible = teacher or (row['review_at'] is not None and at >= row['review_at'])
    if visible and not teacher:
        ensure_practice_unreserved(db, [item['question_id'] for item in rows], at=at)
    answers = []
    for item in rows:
        score = item['score_hundredths']
        value = {'question_version_id': item['question_version_id'], 'value': json.loads(item['value_json']),
                 'answered': bool(item['answered']), 'grading_status': 'unanswered' if not item['answered'] else (
                     'pending' if score is None else 'graded'), 'score': None if score is None else score / 100,
                 'max_score': item['points_hundredths'] / 100, 'comment': item['comment'],
                 'correct': None if item['type'] == 'short' else bool(item['answered'] and score == item['points_hundredths'])}
        if visible:
            value.update(answer=json.loads(item['answer_json']), explanation=item['explanation'])
        answers.append(value)
    total = db.execute('SELECT sum(points_hundredths) FROM paper_item WHERE paper_id=?', (row['paper_id'],)).fetchone()[0]
    return {'id': row['id'], 'paper_id': row['paper_id'], 'student_id': row['student_id'],
            'revision': row['revision'], 'status': row['status'],
            'score': None if row['score_hundredths'] is None else row['score_hundredths'] / 100,
            'partial_score': row['partial_score_hundredths'] / 100, 'total_points': total / 100,
            'submitted_at': row['submitted_at'], 'answers': answers}
