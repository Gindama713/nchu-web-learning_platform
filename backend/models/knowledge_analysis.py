"""SPEC-010B: immutable objective samples and current published knowledge progress."""

from datetime import timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from backend.shared.api import parse_time, stamp

VERSION = 'knowledge-objective-v1'


def extract(db, course_id, start, end, cutoff, subject):
    """Caller owns the read transaction, including authorization and source_until."""
    knowledge = [dict(row) for row in db.execute(
        'SELECT k.id,k.title,k.content_revision FROM knowledge_point k JOIN chapter c ON c.id=k.chapter_id '
        'WHERE c.course_id=? AND k.published=1 ORDER BY k.id',
        (course_id,))]
    progress = [] if subject is None else [dict(row) for row in db.execute(
        'SELECT p.knowledge_id,p.completed,p.completed_at FROM learning_progress p '
        'JOIN knowledge_point k ON k.id=p.knowledge_id JOIN chapter c ON c.id=k.chapter_id '
        'WHERE c.course_id=? AND k.published=1 AND p.user_id=? ORDER BY p.knowledge_id', (course_id, subject))]
    rows = db.execute(
        "WITH samples AS (SELECT 'practice' source,p.id sample_id,p.student_id,p.question_version_id,"
        'p.created_at event_at,p.correct FROM practice_attempt p '
        'JOIN question_version v ON v.id=p.question_version_id JOIN question q ON q.id=v.question_id '
        "WHERE q.course_id=? AND v.type!='short' AND p.answered=1 "
        'AND p.created_at>=? AND p.created_at<? AND p.created_at<=? '
        'AND (? IS NULL OR p.student_id=?) '
        "UNION ALL SELECT 'answer',f.id,a.student_id,f.question_version_id,a.submitted_at,"
        'CASE WHEN f.score_hundredths>0 THEN 1 ELSE 0 END FROM answer f '
        'JOIN attempt a ON a.id=f.attempt_id JOIN paper p ON p.id=a.paper_id '
        'JOIN question_version v ON v.id=f.question_version_id '
        "WHERE p.course_id=? AND v.type!='short' AND f.answered=1 "
        'AND a.submitted_at>=? AND a.submitted_at<? AND a.submitted_at<=? '
        'AND (? IS NULL OR a.student_id=?)) '
        'SELECT s.*,t.knowledge_id FROM samples s LEFT JOIN question_knowledge t '
        'ON t.question_version_id=s.question_version_id ORDER BY s.source,s.sample_id,t.knowledge_id',
        (course_id, start, end, cutoff, subject, subject) * 2).fetchall()
    samples = {}
    for row in rows:
        key = (row['source'], row['sample_id'])
        if key not in samples:
            samples[key] = {name: value for name, value in dict(row).items() if name != 'knowledge_id'}
            samples[key]['knowledge_ids'] = []
        if row['knowledge_id'] is not None:
            samples[key]['knowledge_ids'].append(row['knowledge_id'])
    return {'knowledge': knowledge, 'progress': progress, 'samples': list(samples.values()),
            'subject_student_id': subject}


def metrics(snapshot, start, end):
    samples = [row for row in snapshot['samples'] if start <= row['event_at'] < end]
    frame = pd.DataFrame(samples, columns=['source', 'sample_id', 'correct', 'knowledge_ids'])
    frame = frame.drop_duplicates(['source', 'sample_id'])
    answered, correct = len(frame), int(frame['correct'].sum())
    tagged = frame.explode('knowledge_ids').dropna(subset=['knowledge_ids'])
    tagged = tagged.drop_duplicates(['source', 'sample_id', 'knowledge_ids'])
    counts = tagged.groupby('knowledge_ids', sort=True)['correct'].agg(['count', 'sum'])
    ids = [point['id'] for point in snapshot['knowledge']]
    counts = counts.reindex(ids, fill_value=0)
    items = []
    for point in snapshot['knowledge']:
        count, right = int(counts.loc[point['id'], 'count']), int(counts.loc[point['id'], 'sum'])
        items.append({'knowledge_id': point['id'], 'title': point['title'], 'answered_count': count,
                      'correct_count': right, 'wrong_count': count - right,
                      'mastery': right / count if count else None})
    completed = None if snapshot['subject_student_id'] is None else sum(
        row['completed'] for row in snapshot['progress'])
    return {'answered_count': answered, 'correct_count': correct,
            'mastery': correct / answered if answered else None,
            'completed_knowledge_count': completed, 'published_knowledge_count': len(ids),
            'progress': completed / len(ids) if ids and completed is not None else None, 'items': items}


def calculate(snapshot, start, end, cutoff):
    """Weekly samples use half-open intervals; progress always uses the frozen current set."""
    overall = metrics(snapshot, start, end)
    series = []
    cursor, stop = parse_time(start, 'from'), parse_time(end, 'to')
    while cursor < stop:
        local = cursor.astimezone(ZoneInfo('Asia/Shanghai'))
        boundary = min(stop, (local - timedelta(days=local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0) + timedelta(days=7))
        series.append({'period_start': stamp(cursor), 'period_end': stamp(boundary),
                       'metrics': metrics(snapshot, stamp(cursor), stamp(boundary))})
        cursor = boundary
    return {'dimension': 'knowledge', 'sample_size': overall['answered_count'], 'metrics': overall,
            'series': series, 'source_until': cutoff, 'algorithm_version': VERSION,
            'population_basis': 'objective_answer_events;progress=current_published_knowledge_snapshot',
            'unit': {'mastery': 'ratio', 'progress': 'ratio'},
            'warnings': ['自报完成进度不代表掌握度；日期只筛选作答，进度取当前发布集合'] +
            (['班级进度未定义，请选择学生查看个人进度'] if snapshot['subject_student_id'] is None else [])}
