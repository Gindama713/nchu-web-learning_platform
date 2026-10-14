"""C08 immutable, ordered SPEC-013 inputs; no generated-paper HTTP endpoint."""

import hashlib
import json
import secrets
from dataclasses import asdict, dataclass
from fractions import Fraction

import numpy as np

from backend.models import practice, question
from backend.models.paper import KINDS, points
from backend.shared.api import ApiError, parse_time, stamp

ALGORITHM_VERSION = 'paper-backtrack-v1'
DIFFICULTIES = ('easy', 'medium', 'hard')
MAX_CANDIDATES = 500
MAX_SELECTED = 100
MAX_NODES = 100000


@dataclass(frozen=True)
class Constraints:
    kind: str
    count: int
    total_hundredths: int
    knowledge_ids: tuple[int, ...]
    difficulty_counts: tuple[int, ...]
    confidential: bool
    history_until: str


@dataclass(frozen=True)
class Candidate:
    question_id: int
    version_id: int
    type: str
    difficulty: str
    knowledge_ids: tuple[int, ...]
    correct_count: int
    sample_size: int
    random_key: str

    @property
    def correct_rate(self):
        return self.correct_count / self.sample_size if self.sample_size else None

    def order_key(self):
        return (not self.sample_size, Fraction(self.correct_count, self.sample_size or 1),
                self.random_key, self.version_id)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


@dataclass(frozen=True)
class Snapshot:
    course_id: int
    seed: int
    source_until: str
    parameters: Constraints
    candidates: tuple[Candidate, ...]
    algorithm_version: str = ALGORITHM_VERSION

    def payload(self):
        value = asdict(self)
        for candidate, row in zip(self.candidates, value['candidates'], strict=True):
            row['correct_rate'] = candidate.correct_rate
        return value

    def dumps(self):
        return canonical(self.payload())

    @property
    def input_sha256(self):
        return hashlib.sha256(self.dumps().encode('utf-8')).hexdigest()

    @classmethod
    def loads(cls, value, expected_hash):
        """Saved keys/order are authoritative; never invoke an RNG during replay."""
        try:
            data = json.loads(value)
            parameters = data.pop('parameters')
            parameters['knowledge_ids'] = tuple(parameters['knowledge_ids'])
            parameters['difficulty_counts'] = tuple(parameters['difficulty_counts'])
            rows = []
            for row in data.pop('candidates'):
                rate = row.pop('correct_rate')
                row['knowledge_ids'] = tuple(row['knowledge_ids'])
                candidate = Candidate(**row)
                if rate != candidate.correct_rate:
                    raise ValueError('inconsistent history')
                rows.append(candidate)
            snapshot = cls(parameters=Constraints(**parameters), candidates=tuple(rows), **data)
            validate_snapshot(snapshot)
            if snapshot.input_sha256 != expected_hash:
                raise ValueError('input checksum mismatch')
            return snapshot
        except (ValueError, TypeError, KeyError, ZeroDivisionError, ApiError) as exc:
            raise ApiError(503, 'SNAPSHOT_UNAVAILABLE', '组卷快照不可用或校验失败') from exc


def normalize(body, source_until):
    required = {'kind', 'count', 'total_points', 'knowledge_ids', 'difficulty_counts'}
    if type(body) is not dict or required - body.keys() or body.keys() - required - {
            'seed', 'confidential', 'history_until'}:
        question.invalid('组卷算法输入字段不合法')
    if type(body['kind']) is not str or body['kind'] not in KINDS:
        question.invalid('试卷类型不合法')
    count = body['count']
    if type(count) is not int or not 1 <= count <= MAX_SELECTED:
        question.invalid('选题量须为1至100的JSON整数')
    total = points(body['total_points'])
    if not 100 <= total <= 100000:
        question.invalid('总分须为1至1000且最多两位小数')
    quotas = body['difficulty_counts']
    if type(quotas) is not dict or set(quotas) != set(DIFFICULTIES):
        question.invalid('难度配额须包含easy/medium/hard')
    if any(type(v) is not int or not 0 <= v <= MAX_SELECTED for v in quotas.values()):
        question.invalid('难度配额须为非负JSON整数')
    if sum(quotas.values()) != count:
        question.invalid('难度配额总和须等于题量')
    ids = body['knowledge_ids']
    if type(ids) is not list:
        question.invalid('知识点须为ID数组')
    for value in ids:
        question.identifier(value)
    if len(set(ids)) != len(ids):
        question.invalid('知识点不能重复')
    confidential = body.get('confidential', body['kind'] == 'exam')
    if type(confidential) is not bool:
        question.invalid('保密标志须为JSON布尔')
    seed = body.get('seed', secrets.randbits(63))
    if type(seed) is not int or not -question.MAX_ID - 1 <= seed <= question.MAX_ID:
        question.invalid('seed须为可存储的JSON整数')
    source = parse_time(source_until, 'source_until')
    history = parse_time(body.get('history_until', source_until), 'history_until')
    if source.microsecond % 1000 or history.microsecond % 1000 or history > source:
        question.invalid('历史截止不能晚于读取截止，时间最多毫秒精度')
    return Constraints(body['kind'], count, total, tuple(sorted(ids)),
                       tuple(quotas[k] for k in DIFFICULTIES), confidential, stamp(history)), seed, stamp(source)


def validate_snapshot(snapshot):
    """Validate decoded inputs before allocating search structures or persisting."""
    if snapshot.algorithm_version != ALGORITHM_VERSION:
        raise ApiError(503, 'SNAPSHOT_UNAVAILABLE', '不支持该组卷算法版本')
    question.identifier(snapshot.course_id)
    p = snapshot.parameters
    normalized, seed, source = normalize({
        'kind': p.kind, 'count': p.count, 'total_points': p.total_hundredths / 100,
        'knowledge_ids': list(p.knowledge_ids), 'difficulty_counts': dict(zip(DIFFICULTIES, p.difficulty_counts)),
        'confidential': p.confidential, 'history_until': p.history_until, 'seed': snapshot.seed}, snapshot.source_until)
    if (normalized, seed, source) != (p, snapshot.seed, snapshot.source_until):
        question.invalid('快照参数须为标准格式')
    if len(snapshot.candidates) > MAX_CANDIDATES:
        question.invalid('候选题量不能超过500')
    versions = set()
    for row in snapshot.candidates:
        question.identifier(row.question_id)
        question.identifier(row.version_id)
        if row.version_id in versions or row.type not in question.TYPES or row.difficulty not in DIFFICULTIES:
            question.invalid('候选版本或类型无效')
        versions.add(row.version_id)
        for value in row.knowledge_ids:
            question.identifier(value)
        if tuple(sorted(set(row.knowledge_ids))) != row.knowledge_ids:
            question.invalid('候选知识点须有序且去重')
        if type(row.sample_size) is not int or type(row.correct_count) is not int or not 0 <= row.correct_count <= row.sample_size:
            question.invalid('历史计数不合法')
        if row.type == 'short' and row.sample_size:
            question.invalid('简答不计算客观正确率')
        if type(row.random_key) is not str or len(row.random_key) != 16 or any(c not in '0123456789abcdef' for c in row.random_key):
            question.invalid('排序键须为固定16位十六进制')
    if tuple(sorted(snapshot.candidates, key=Candidate.order_key)) != snapshot.candidates:
        question.invalid('快照须保存全部有序候选')


def freeze(db, course_id, body, *, source_until):
    """Own a bounded read transaction, release it before the potentially long search.

    History is per fixed version across actual paper answers and practices. A
    partial paper's scored objective answers count; omissions/shorts never do.
    The caller supplies a server timestamp and is responsible for authorization.
    """
    question.identifier(course_id)
    parameters, seed, source = normalize(body, source_until)
    if db.in_transaction:
        raise RuntimeError('freeze requires a separate read transaction')
    db.execute('BEGIN')
    try:
        practice.ready(db)
        if not db.execute('SELECT 1 FROM course WHERE id=?', (course_id,)).fetchone():
            question.invalid('课程不存在')
        for knowledge_id in parameters.knowledge_ids:
            if not db.execute('SELECT 1 FROM knowledge_point k JOIN chapter c ON c.id=k.chapter_id '
                              'WHERE k.id=? AND c.course_id=?', (knowledge_id, course_id)).fetchone():
                question.invalid('知识点须属于本课程')
        rows = db.execute(
            'SELECT v.* FROM question q JOIN question_version v ON v.question_id=q.id '
            'WHERE q.course_id=? AND q.archived=0 '
            'AND v.version=(SELECT max(version) FROM question_version WHERE question_id=q.id) '
            'AND (?=0 OR (q.ever_public=0 '
            'AND NOT EXISTS(SELECT 1 FROM question_version pv WHERE pv.question_id=q.id AND pv.practice_available=1) '
            "AND NOT EXISTS(SELECT 1 FROM paper_item i JOIN paper p ON p.id=i.paper_id WHERE i.question_id=q.id "
            "AND p.status='published' AND p.start_at<=?))) ORDER BY v.id LIMIT ?",
            (course_id, int(parameters.confidential), source, MAX_CANDIDATES + 1)).fetchall()
        if len(rows) > MAX_CANDIDATES:
            question.invalid('候选超过500，请缩小题库范围或另行评审')
        history = {r['version_id']: r for r in db.execute(
            'SELECT version_id,count(*) AS n,sum(correct) AS c FROM ('
            'SELECT f.question_version_id AS version_id,(f.score_hundredths=i.points_hundredths) AS correct '
            'FROM answer f JOIN attempt a ON a.id=f.attempt_id '
            'JOIN paper_item i ON i.paper_id=a.paper_id AND i.question_version_id=f.question_version_id '
            'JOIN question_version v ON v.id=f.question_version_id JOIN question q ON q.id=v.question_id '
            "WHERE q.course_id=? AND v.type!='short' AND f.answered=1 AND f.score_hundredths IS NOT NULL AND a.submitted_at<=? "
            'UNION ALL SELECT f.question_version_id,f.correct FROM practice_attempt f '
            'JOIN question_version v ON v.id=f.question_version_id JOIN question q ON q.id=v.question_id '
            "WHERE q.course_id=? AND v.type!='short' AND f.answered=1 AND f.created_at<=?) GROUP BY version_id",
            (course_id, parameters.history_until, course_id, parameters.history_until))}
        keys = np.random.Generator(np.random.PCG64(seed % (1 << 64))).bit_generator.random_raw(len(rows))
        candidates = []
        for row, key in zip(rows, keys, strict=True):
            ids = tuple(r[0] for r in db.execute('SELECT knowledge_id FROM question_knowledge '
                                                 'WHERE question_version_id=? ORDER BY knowledge_id', (row['id'],)))
            counts = history.get(row['id'], {'c': 0, 'n': 0})
            candidates.append(Candidate(row['question_id'], row['id'], row['type'], row['difficulty'], ids,
                                        counts['c'], counts['n'], format(int(key), '016x')))
        snapshot = Snapshot(course_id, seed, source, parameters, tuple(sorted(candidates, key=Candidate.order_key)))
        validate_snapshot(snapshot)
        return snapshot
    finally:
        db.rollback()
