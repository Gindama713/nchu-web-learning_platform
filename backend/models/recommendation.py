"""SPEC-012 online recommendations from the existing 010B objective facts."""

from datetime import timedelta
from fractions import Fraction

from backend.models import knowledge_analysis, practice, question
from backend.shared.api import ApiError, parse_time, stamp

VERSION = 'recommend-v1'


def extract(db, course_id, student_id, cutoff):
    """Caller owns one authorized read snapshot; never read answers into output."""
    practice.ready(db)
    start = stamp(parse_time(cutoff, 'source_until') - timedelta(days=28))
    snapshot = knowledge_analysis.extract(db, course_id, start, cutoff, cutoff, student_id)
    points = [dict(row) for row in db.execute(
        'SELECT k.id,k.is_foundational FROM knowledge_point k JOIN chapter c ON c.id=k.chapter_id '
        'WHERE c.course_id=? AND k.published=1 ORDER BY k.id', (course_id,))]
    entries = {}
    # Select the current version of each identity first, then apply eligibility.
    # An older public version must not replace a newer private/short/tag-changed version.
    rows = db.execute(
        'SELECT v.id,v.question_id,t.knowledge_id FROM question q '
        'JOIN question_version v ON v.question_id=q.id '
        'JOIN question_knowledge t ON t.question_version_id=v.id '
        'JOIN knowledge_point k ON k.id=t.knowledge_id JOIN chapter c ON c.id=k.chapter_id '
        'WHERE q.course_id=? AND c.course_id=? AND k.published=1 AND q.archived=0 '
        'AND v.version=(SELECT max(version) FROM question_version WHERE question_id=q.id) '
        "AND v.practice_available=1 AND v.type!='short' ORDER BY v.id,t.knowledge_id",
        (course_id, course_id)).fetchall()
    for row in rows:
        try:
            question.ensure_practice_unreserved(db, [row['question_id']], at=cutoff)
        except ApiError as exc:
            if exc.code != 'QUESTION_RESERVED':
                raise
            continue
        entries.setdefault(row['knowledge_id'], row['id'])
    snapshot.update(foundations=points, entries=entries, start=start, source_until=cutoff)
    return snapshot


def calculate(snapshot, limit):
    metrics = knowledge_analysis.metrics(snapshot, snapshot['start'], snapshot['source_until'])
    points = {row['id']: row for row in snapshot['foundations']}
    completed = {row['knowledge_id'] for row in snapshot['progress'] if row['completed']}
    cold = sum(row['answered_count'] for row in metrics['items']) == 0
    ranked = []
    for row in metrics['items']:
        kid, n, c = row['knowledge_id'], row['answered_count'], row['correct_count']
        done = kid in completed
        if cold:
            if not points[kid]['is_foundational'] or done:
                continue
            score, reason = Fraction(1), 'foundational'
        else:
            mastery = Fraction(c, n) if n else None
            if done and n >= 5 and mastery >= Fraction(4, 5):
                continue
            weakness = 1 - mastery if n else Fraction(1, 2)
            score = Fraction(4, 5) * weakness + Fraction(not done, 5)
            reason = 'insufficient_sample' if n < 5 else 'weakness' if mastery < Fraction(4, 5) else 'incomplete'
        ranked.append((score, {'knowledge_id': kid, 'question_version_id': snapshot['entries'].get(kid),
                               'reason': reason, 'score': round(float(score), 6),
                               'mastery': row['mastery'], 'sample_size': n}))
    ranked.sort(key=lambda row: (-row[0], row[1]['knowledge_id']))
    reason = ('no_published_knowledge' if not points else
              'cold_start' if cold and ranked else 'no_foundational_candidates' if cold else
              'ok' if ranked else 'all_mastered')
    return {'items': [row[1] for row in ranked[:limit]], 'reason': reason,
            'source_until': snapshot['source_until'], 'algorithm_version': VERSION}
