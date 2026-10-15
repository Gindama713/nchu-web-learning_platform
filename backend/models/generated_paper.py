"""C09 draft persistence; search is finished before this service takes a write lock."""

import hashlib
from pathlib import Path

from backend.models import generation_snapshot, question
from backend.shared.api import ApiError, audit, stamp

SQL = Path(__file__).resolve().parents[1] / 'migrations' / '013b_generated_papers.sql'
VERSION = SQL.stem
CHECKSUM = hashlib.sha256(SQL.read_text(encoding='utf-8').encode()).hexdigest()


def ready(db):
    generation_snapshot.ready(db)
    row = db.execute('SELECT checksum FROM schema_migration WHERE version=?', (VERSION,)).fetchone()
    if not row or row[0] != CHECKSUM:
        raise ApiError(503, 'MAINTENANCE', '组卷草稿迁移尚未接入或校验失败')


def save(db, title, snapshot, solution, *, replay_of=None):
    if not db.in_transaction:
        raise RuntimeError('generated paper requires caller transaction')
    ready(db)
    # These are current eligibility checks, never a new candidate/history read.
    identities = []
    for version_id in solution.selected_version_ids:
        row = db.execute('SELECT q.* FROM question_version v JOIN question q ON q.id=v.question_id '
                         'WHERE v.id=? AND q.course_id=?', (version_id, snapshot.course_id)).fetchone()
        if not row or row['archived']:
            raise ApiError(409, 'QUESTION_UNAVAILABLE', '原选题已归档或不可用，请重新生成')
        identities.append(row['id'])
        if snapshot.parameters.confidential and (
                row['ever_public'] or db.execute('SELECT 1 FROM question_version WHERE question_id=? '
                                                 'AND practice_available=1', (row['id'],)).fetchone()
                or db.execute("SELECT 1 FROM paper p JOIN paper_item i ON i.paper_id=p.id "
                              "WHERE i.question_id=? AND p.status='published' AND p.start_at<=?",
                              (row['id'], stamp())).fetchone()):
            raise ApiError(409, 'QUESTION_PUBLIC', '原选题身份曾公开，不能生成保密草稿')
    question.ensure_questions_unreserved(db, identities, confidential=snapshot.parameters.confidential, at=stamp())
    snapshot_id = generation_snapshot.save(db, snapshot, solution)
    paper_id = db.execute('INSERT INTO paper(course_id,title,kind,confidential,seed,algorithm_version,'
                          'generation_snapshot_id) VALUES(?,?,?,?,?,?,?)',
                          (snapshot.course_id, title, snapshot.parameters.kind, int(snapshot.parameters.confidential),
                           snapshot.seed, snapshot.algorithm_version, snapshot_id)).lastrowid
    candidates = {row.version_id: row for row in snapshot.candidates}
    db.executemany('INSERT INTO paper_item(paper_id,question_version_id,question_id,position,points_hundredths) '
                   'VALUES(?,?,?,?,?)', [(paper_id, version_id, candidates[version_id].question_id, position, points)
                                        for position, (version_id, points) in enumerate(zip(
                                            solution.selected_version_ids, solution.points_hundredths, strict=True), 1)])
    audit('paper.generate', 'paper', paper_id, after={'generation_snapshot_id': snapshot_id,
          'replay_of': replay_of, 'input_sha256': snapshot.input_sha256, 'status': 'draft'})
    return {'paper_id': paper_id, 'generation_snapshot_id': snapshot_id, 'status': 'draft',
            'selected_version_ids': solution.selected_version_ids, 'coverage': solution.coverage,
            'seed': snapshot.seed, 'seed_text': str(snapshot.seed), 'algorithm_version': snapshot.algorithm_version,
            'points_hundredths': solution.points_hundredths, 'search_nodes': solution.search_nodes}
