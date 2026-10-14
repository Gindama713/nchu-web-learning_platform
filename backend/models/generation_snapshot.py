"""C08 immutable persistence; C09 callers own authorization and write transaction."""

import hashlib
import json
from pathlib import Path

from backend.models import practice, question
from backend.models.generation_input import Snapshot, canonical
from backend.models.generation_solver import solve, validate_solution
from backend.shared.api import ApiError

SQL = Path(__file__).resolve().parents[1] / 'migrations' / '013_generation_snapshot.sql'
VERSION = SQL.stem
CHECKSUM = hashlib.sha256(SQL.read_text(encoding='utf-8').encode()).hexdigest()


def ready(db):
    practice.ready(db)
    row = db.execute('SELECT checksum FROM schema_migration WHERE version=?', (VERSION,)).fetchone()
    if not row or row[0] != CHECKSUM:
        raise ApiError(503, 'MAINTENANCE', '组卷快照迁移尚未接入或校验失败')


def history(snapshot):
    return [{'version_id': r.version_id, 'correct_count': r.correct_count,
             'sample_size': r.sample_size, 'correct_rate': r.correct_rate} for r in snapshot.candidates]


def save(db, snapshot, result):
    """Must join the caller's short transaction; never commit independently.

    Old candidate versions remain valid evidence after edits/archive/publication.
    Verify every version/course reference, not current latest status. C09 must
    check current eligibility separately before creating/publishing draft items.
    """
    if not db.in_transaction:
        raise RuntimeError('snapshot save requires caller transaction')
    ready(db)
    validate_solution(snapshot, result)
    for candidate in snapshot.candidates:
        if not db.execute('SELECT 1 FROM question_version v JOIN question q ON q.id=v.question_id '
                          'WHERE v.id=? AND q.id=? AND q.course_id=?',
                          (candidate.version_id, candidate.question_id, snapshot.course_id)).fetchone():
            raise ApiError(422, 'INFEASIBLE_CONSTRAINTS', '快照版本须属于原课程')
    payload = snapshot.payload()
    return db.execute(
        'INSERT INTO generation_snapshot(course_id,seed,algorithm_version,parameters_json,candidates_json,'
        'history_json,source_until,input_sha256,selected_ids_json) VALUES(?,?,?,?,?,?,?,?,?)',
        (snapshot.course_id, snapshot.seed, snapshot.algorithm_version, canonical(payload['parameters']),
         canonical(payload['candidates']), canonical(history(snapshot)), snapshot.source_until,
         snapshot.input_sha256, canonical(result.selected_version_ids))).lastrowid


def load(db, snapshot_id, course_id):
    """Read only saved input; caller must authorize the current teacher/course."""
    question.identifier(snapshot_id)
    question.identifier(course_id)
    ready(db)
    row = db.execute('SELECT * FROM generation_snapshot WHERE id=? AND course_id=?',
                     (snapshot_id, course_id)).fetchone()
    if not row:
        raise ApiError(404, 'NOT_FOUND', '组卷快照不存在或不可见')
    try:
        snapshot = Snapshot.loads(canonical({
            'course_id': row['course_id'], 'seed': row['seed'], 'algorithm_version': row['algorithm_version'],
            'source_until': row['source_until'], 'parameters': json.loads(row['parameters_json']),
            'candidates': json.loads(row['candidates_json'])}), row['input_sha256'])
        if json.loads(row['history_json']) != history(snapshot):
            raise ValueError('history checksum mismatch')
        selected_ids = json.loads(row['selected_ids_json'])
        if type(selected_ids) is not list or any(type(v) is not int for v in selected_ids):
            raise ValueError('invalid selected IDs')
        return snapshot, tuple(selected_ids)
    except (ValueError, TypeError, KeyError) as exc:
        raise ApiError(503, 'SNAPSHOT_UNAVAILABLE', '组卷快照不可用或校验失败') from exc


def replay(db, snapshot_id, course_id):
    snapshot, selected_ids = load(db, snapshot_id, course_id)
    result = solve(snapshot)
    if result.selected_version_ids != selected_ids:
        raise ApiError(503, 'SNAPSHOT_UNAVAILABLE', '重算选题与原快照不一致')
    return snapshot, result
