"""SPEC-006 fixed-version drafts, roster freeze and shared publication service."""

import hashlib
from decimal import Decimal
from pathlib import Path

from backend.models.question import (
    MAX_ID,
    ensure_practice_unreserved,
    ensure_questions_unreserved,
    identifier,
    invalid,
    model,
    number,
)
from backend.models.question import (
    ready as questions_ready,
)
from backend.shared.api import ApiError, audit, notify, parse_time, stamp, text_field

KINDS = frozenset({'homework', 'exam', 'quiz'})
SQL = Path(__file__).resolve().parents[1] / 'migrations' / '006b_papers.sql'
VERSION = SQL.stem
CHECKSUM = hashlib.sha256(SQL.read_text(encoding='utf-8').encode()).hexdigest()


def ready(db):
    questions_ready(db)
    row = db.execute('SELECT checksum FROM schema_migration WHERE version=?', (VERSION,)).fetchone()
    if not row or row[0] != CHECKSUM:
        raise ApiError(503, 'MAINTENANCE', '试卷迁移尚未接入或校验失败')


def points(value):
    number(value, 'points')
    decimal = Decimal(str(value))
    if not 0 < decimal <= Decimal(MAX_ID) / 100:
        invalid('配分须为可存储的正数')
    scaled = decimal * 100
    if scaled != scaled.to_integral_value():
        invalid('配分最多两位小数')
    return int(scaled)


def create(db, course_id, body):
    if set(body) - {'title', 'kind', 'confidential', 'items'} or {'title', 'kind', 'items'} - set(body):
        invalid('编卷字段不合法')
    title = text_field(body['title'], 'title', 1, 100)
    kind = body['kind']
    if type(kind) is not str or kind not in KINDS:
        invalid('试卷类型不合法')
    confidential = body.get('confidential', kind == 'exam')
    if type(confidential) is not bool:
        invalid('保密标志须为JSON布尔')
    if type(body['items']) is not list or not body['items']:
        invalid('试卷须有至少一道题目')
    items, seen, total = [], set(), 0
    for item in body['items']:
        if type(item) is not dict or set(item) != {'question_version_id', 'points'}:
            invalid('条目仅接受question_version_id和points')
        version_id = identifier(item['question_version_id'])
        value = points(item['points'])
        row = db.execute('SELECT v.question_id,q.course_id,q.archived FROM question_version v '
                         'JOIN question q ON q.id=v.question_id WHERE v.id=?', (version_id,)).fetchone()
        if not row or row['course_id'] != course_id or row['archived']:
            invalid('版本须为本课程未归档题目')
        if row['question_id'] in seen:
            invalid('同一题目不能重复入卷，即使版本不同')
        seen.add(row['question_id'])
        total += value
        if total > MAX_ID:
            invalid('总配分超出存储范围')
        items.append((version_id, row['question_id'], len(items) + 1, value))
    paper_id = db.execute('INSERT INTO paper(course_id,title,kind,confidential) VALUES(?,?,?,?)',
                          (course_id, title, kind, int(confidential))).lastrowid
    db.executemany('INSERT INTO paper_item(paper_id,question_version_id,question_id,position,points_hundredths) '
                   'VALUES(?,?,?,?,?)', [(paper_id, *item) for item in items])
    audit('paper.create', 'paper', paper_id, after={'kind': kind, 'item_count': len(items)})
    return paper_id


def find(db, paper_id):
    identifier(paper_id)
    row = db.execute('SELECT * FROM paper WHERE id=?', (paper_id,)).fetchone()
    if not row:
        raise ApiError(404, 'NOT_FOUND', '试卷不存在或不可见')
    return row


def publish(db, row, body, *, quiz=False):
    """Caller holds BEGIN IMMEDIATE and has rechecked current teacher access.

    C05 can call quiz=True from its own route to leave review_at null.
    """
    if row['status'] != 'draft':
        raise ApiError(409, 'STATE_CONFLICT', '试卷已发布，不能重复发布或修改')
    if quiz and row['kind'] != 'quiz':
        raise ApiError(409, 'STATE_CONFLICT', '随堂测专用入口仅接受quiz试卷')
    fields = {'start_at', 'end_at'} | (set() if quiz else {'review_at'})
    if fields - set(body) or set(body) - fields - {'confidentiality_note'}:
        invalid('发布字段不合法')
    times = {}
    for field in fields:
        value = parse_time(body[field], field)
        if value.microsecond % 1000:
            invalid('时间最多支持毫秒精度')
        times[field] = stamp(value)
    if times['start_at'] >= times['end_at'] or (not quiz and times['end_at'] > times['review_at']):
        invalid('须满足开始早于截止，讲评不早于截止')
    note = body.get('confidentiality_note')
    if row['confidential'] or note is not None:
        note = text_field(note, 'confidentiality_note', 1, 1000)
    at = stamp()
    items = db.execute('SELECT i.*,q.ever_public,q.archived,q.course_id FROM paper_item i '
                       'JOIN question q ON q.id=i.question_id WHERE i.paper_id=? ORDER BY i.position',
                       (row['id'],)).fetchall()
    if not items:
        invalid('空试卷不能发布')
    for item in items:
        if item['archived'] or item['course_id'] != row['course_id']:
            invalid('试卷含无效题目')
    ids = [item['question_id'] for item in items]
    ensure_questions_unreserved(db, ids, confidential=bool(row['confidential']), at=at)
    if row['confidential']:
        for item in items:
            public_version = db.execute('SELECT 1 FROM question_version WHERE question_id=? '
                                        'AND practice_available=1 LIMIT 1', (item['question_id'],)).fetchone()
            exposed = db.execute('SELECT 1 FROM paper p JOIN paper_item i ON i.paper_id=p.id '
                                 "WHERE i.question_id=? AND p.status='published' AND p.start_at<=? LIMIT 1",
                                 (item['question_id'], at)).fetchone()
            if item['ever_public'] or public_version or exposed:
                raise ApiError(409, 'QUESTION_PUBLIC', '题目身份曾公开，不能用于保密发布')
    # Freeze the effective student population, not just member_role or global role alone.
    db.execute('INSERT INTO paper_participant(paper_id,student_id) '
               "SELECT ?,u.id FROM course_member m JOIN user u ON u.id=m.user_id WHERE m.course_id=? "
               "AND m.active=1 AND m.member_role='student' AND u.active=1 AND u.role='student'",
               (row['id'], row['course_id']))
    db.execute("UPDATE paper SET status='published',start_at=?,end_at=?,review_at=?,confidentiality_note=? WHERE id=?",
               (times['start_at'], times['end_at'], times.get('review_at'), note, row['id']))
    count = db.execute('SELECT count(*) FROM paper_participant WHERE paper_id=?', (row['id'],)).fetchone()[0]
    audit('paper.publish', 'paper', row['id'], before={'status': 'draft'},
          after={'status': 'published', 'participant_count': count, **times})
    if row['kind'] == 'quiz':
        for participant in db.execute('SELECT student_id FROM paper_participant WHERE paper_id=?', (row['id'],)):
            notify(participant['student_id'], row['course_id'], f"随堂测已发布：{row['title']}",
                   'quiz', row['id'], f"quiz.published:{row['id']}")


def metadata(db, row, *, teacher=False, at=None):
    at = at or stamp()
    state = None if row['status'] == 'draft' else (
        'upcoming' if at < row['start_at'] else 'open' if at < row['end_at'] else 'closed')
    total = db.execute('SELECT coalesce(sum(points_hundredths),0) FROM paper_item WHERE paper_id=?',
                       (row['id'],)).fetchone()[0]
    item = {'id': row['id'], 'title': row['title'], 'kind': row['kind'], 'status': row['status'],
            'confidential': bool(row['confidential']), 'total_points': total / 100,
            'window_state': state, 'start_at': row['start_at'], 'end_at': row['end_at'], 'review_at': row['review_at']}
    if teacher:
        item['confidentiality_note'] = row['confidentiality_note']
        item['participant_count'] = db.execute('SELECT count(*) FROM paper_participant WHERE paper_id=?',
                                               (row['id'],)).fetchone()[0]
    return item


def detail(db, row, *, teacher, at=None):
    at = at or stamp()
    item = metadata(db, row, teacher=teacher, at=at)
    if not teacher and at < row['start_at']:
        return item
    rows = db.execute('SELECT v.*,i.position,i.points_hundredths FROM paper_item i '
                      'JOIN question_version v ON v.id=i.question_version_id WHERE i.paper_id=? ORDER BY i.position',
                      (row['id'],)).fetchall()
    answer_visible = teacher or (row['review_at'] is not None and at >= row['review_at'])
    if not teacher and answer_visible:
        ensure_practice_unreserved(db, [value['question_id'] for value in rows], at=at)
    item['items'] = [{**model(db, value, teacher=answer_visible), 'question_version_id': value['id'],
                      'position': value['position'], 'points': value['points_hundredths'] / 100} for value in rows]
    return item
