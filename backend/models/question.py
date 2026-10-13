"""SPEC-006 question validation and immutable versions; no grading or paper publishing."""

import hashlib
import json
import math
from pathlib import Path

from backend.shared.api import ApiError, stamp, text_field

TYPES = frozenset({'single', 'multiple', 'boolean', 'numeric', 'short'})
DIFFICULTIES = frozenset({'easy', 'medium', 'hard'})
FIELDS = frozenset({'type', 'stem', 'options', 'answer', 'explanation', 'difficulty',
                    'tolerance', 'knowledge_ids', 'practice_available'})
REQUIRED = FIELDS - {'explanation', 'tolerance', 'practice_available'}
SQL = Path(__file__).resolve().parents[1] / 'migrations' / '006_question_versions.sql'
VERSION = SQL.stem
CHECKSUM = hashlib.sha256(SQL.read_text(encoding='utf-8').encode()).hexdigest()
MAX_ID = 9223372036854775807


def invalid(message='题目字段不合法'):
    raise ApiError(400, 'VALIDATION_ERROR', message)


def identifier(value):
    if type(value) is not int or not 0 < value <= MAX_ID:
        invalid('ID须为数据库可表示的正整数')
    return value


def number(value, field):
    if type(value) not in (int, float):
        invalid(f'{field}须为有限JSON数值')
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        invalid(f'{field}须为有限JSON数值')
    return value


def validate_question(body, previous=None):
    if type(body) is not dict or not body or set(body) - FIELDS:
        invalid()
    if previous is None and REQUIRED - set(body):
        invalid('缺少题目必需字段')
    values = {'explanation': '', 'tolerance': 0, 'practice_available': False}
    if previous is not None:
        values.update({key: previous[key] for key in FIELDS})
    values.update(body)
    kind, difficulty = values['type'], values['difficulty']
    if not isinstance(kind, str) or kind not in TYPES:
        invalid('题型不合法')
    if not isinstance(difficulty, str) or difficulty not in DIFFICULTIES:
        invalid('难度不合法')
    values['stem'] = text_field(values['stem'], 'stem', 1, 5000)
    values['explanation'] = text_field(values['explanation'], 'explanation', 0, 5000)
    options = values['options']
    if type(options) is not list:
        invalid('选项须为数组')
    if kind in {'single', 'multiple'}:
        if not 2 <= len(options) <= 8:
            invalid('选择题须有2至8个选项')
        normalized = []
        for option in options:
            if type(option) is not dict or set(option) != {'key', 'text'}:
                invalid('选项仅接受key/text')
            normalized.append({'key': text_field(option['key'], 'key', 1, 20),
                               'text': text_field(option['text'], 'option text', 1, 5000)})
        keys = [item['key'] for item in normalized]
        if len(set(keys)) != len(keys):
            invalid('选项key不能重复')
        values['options'] = normalized
    elif options:
        invalid('非选择题选项须为空数组')
    else:
        keys = []
    answer = values['answer']
    if kind == 'single':
        if type(answer) is not str or answer not in keys:
            invalid('单选答案须为已定义的key')
    elif kind == 'multiple':
        if (type(answer) is not list or not answer or any(type(key) is not str for key in answer)
                or len(set(answer)) != len(answer) or not set(answer) <= set(keys)):
            invalid('多选答案须为非空不重复的已定义key数组')
    elif kind == 'boolean':
        if type(answer) is not bool:
            invalid('判断答案须为JSON布尔')
    elif kind == 'numeric':
        number(answer, 'answer')
    else:
        values['answer'] = text_field(answer, 'answer', 1, 5000)
    tolerance = number(values['tolerance'], 'tolerance')
    if tolerance < 0 or (kind != 'numeric' and tolerance != 0):
        invalid('容差须非负，且仅数值题可设置非零容差')
    ids = values['knowledge_ids']
    if type(ids) is not list or not ids:
        invalid('须选择至少一个知识点')
    for item in ids:
        identifier(item)
    if len(set(ids)) != len(ids):
        invalid('知识点不能重复')
    values['knowledge_ids'] = sorted(ids)
    if type(values['practice_available']) is not bool:
        invalid('练习开放状态须为JSON布尔')
    if kind == 'short' and values['practice_available']:
        invalid('简答不支持单题公开练习')
    return values


def require_tables(db, names, message):
    existing = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not set(names) <= existing:
        raise ApiError(503, 'DEPENDENCY_UNAVAILABLE', message)


def ready(db):
    row = db.execute('SELECT checksum FROM schema_migration WHERE version=?', (VERSION,)).fetchone()
    if not row or row[0] != CHECKSUM:
        raise ApiError(503, 'MAINTENANCE', '题库迁移尚未接入或校验失败')


def check_knowledge(db, course_id, ids):
    require_tables(db, {'chapter', 'knowledge_point'}, '知识模块未接入，暂不能保存题目')
    # One query per ID keeps SQLite's parameter limit independent of the tag count.
    for item in ids:
        row = db.execute('SELECT c.course_id FROM knowledge_point k JOIN chapter c ON c.id=k.chapter_id '
                         'WHERE k.id=?', (item,)).fetchone()
        if not row or row[0] != course_id:
            invalid('知识标签须属于本课程')


def ensure_practice_unreserved(db, question_ids):
    """Shared question-identity guard. Caller holds the read/write transaction."""
    require_tables(db, {'paper', 'paper_item'}, '试卷保密保护尚未接入，暂不能开放或读取公开练习')
    at = stamp()
    for question_id in question_ids:
        reserved = db.execute(
            'SELECT 1 FROM paper p JOIN paper_item i ON i.paper_id=p.id '
            "WHERE i.question_id=? AND p.status='published' AND p.confidential=1 "
            'AND (p.review_at IS NULL OR p.review_at>?) LIMIT 1', (question_id, at)).fetchone()
        if reserved:
            raise ApiError(409, 'QUESTION_RESERVED', '题目仍被保密试卷保护，不能开放练习')


def latest(db, question_id):
    row = db.execute('SELECT v.*,q.course_id,q.archived FROM question_version v '
                     'JOIN question q ON q.id=v.question_id WHERE q.id=? ORDER BY v.version DESC LIMIT 1',
                     (question_id,)).fetchone()
    if not row or row['archived']:
        raise ApiError(404, 'NOT_FOUND', '题目不存在或不可见')
    return row


def model(db, row, teacher=True):
    result = {'id': row['question_id'], 'version_id': row['id'], 'version': row['version'],
              'type': row['type'], 'stem': row['stem'], 'options': json.loads(row['options_json']),
              'difficulty': row['difficulty'], 'tolerance': row['tolerance'],
              'practice_available': bool(row['practice_available']),
              'knowledge_ids': [item[0] for item in db.execute(
                  'SELECT knowledge_id FROM question_knowledge WHERE question_version_id=? ORDER BY knowledge_id',
                  (row['id'],))]}
    if teacher:
        result.update(answer=json.loads(row['answer_json']), explanation=row['explanation'])
    return result


def save_version(db, course_id, values, current=None):
    check_knowledge(db, course_id, values['knowledge_ids'])
    if values['practice_available']:
        ensure_practice_unreserved(db, [current['question_id']] if current is not None else [])
    if current is None:
        question_id = db.execute('INSERT INTO question(course_id) VALUES(?)', (course_id,)).lastrowid
        version = 1
    else:
        question_id, version = current['question_id'], current['version'] + 1
    serialize = lambda value: json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    version_id = db.execute(
        'INSERT INTO question_version(question_id,version,type,stem,options_json,answer_json,explanation,'
        'difficulty,tolerance,practice_available) VALUES(?,?,?,?,?,?,?,?,?,?)',
        (question_id, version, values['type'], values['stem'], serialize(values['options']),
         serialize(values['answer']), values['explanation'], values['difficulty'], values['tolerance'],
         int(values['practice_available']))).lastrowid
    db.executemany('INSERT INTO question_knowledge(question_version_id,knowledge_id) VALUES(?,?)',
                   [(version_id, item) for item in values['knowledge_ids']])
    if values['practice_available']:
        db.execute('UPDATE question SET ever_public=1 WHERE id=?', (question_id,))
    return model(db, latest(db, question_id))
