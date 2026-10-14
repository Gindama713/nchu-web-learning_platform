"""010B scores: frozen paper/student assignments, never a writable grade source."""

from datetime import timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from backend.shared.api import ApiError, parse_time, stamp

VERSION = 'scores-frozen-participants-v1'
BIN_LABELS = ('[0,60)', '[60,70)', '[70,80)', '[80,90)', '[90,100]')


def extract(db, course_id, start, end, cutoff, subject, kind, paper_id):
    if paper_id is not None:
        paper = db.execute("SELECT id FROM paper WHERE id=? AND course_id=? AND kind=? "
                           "AND status='published'", (paper_id, course_id, kind)).fetchone()
        if not paper or (subject is not None and not db.execute(
                'SELECT 1 FROM paper_participant WHERE paper_id=? AND student_id=?',
                (paper_id, subject)).fetchone()):
            raise ApiError(404, 'NOT_FOUND', 'Paper not found')
    papers = [dict(row) for row in db.execute(
        'SELECT p.id,p.title,p.kind,p.start_at,SUM(i.points_hundredths) total_hundredths '
        'FROM paper p JOIN paper_item i ON i.paper_id=p.id '
        "WHERE p.course_id=? AND p.status='published' AND p.kind=? "
        'AND p.start_at>=? AND p.start_at<? '
        'AND (? IS NULL OR p.id=?) GROUP BY p.id ORDER BY p.id',
        (course_id, kind, start, end, paper_id, paper_id))]
    # Join assignments first: missing and partial are distinct from a final zero.
    rows = [dict(row) for row in db.execute(
        'SELECT p.id paper_id,m.student_id,a.id attempt_id,a.status,a.score_hundredths,a.submitted_at '
        'FROM paper p JOIN paper_participant m ON m.paper_id=p.id '
        'LEFT JOIN attempt a ON a.paper_id=p.id AND a.student_id=m.student_id AND a.submitted_at<=? '
        "WHERE p.course_id=? AND p.status='published' AND p.kind=? "
        'AND p.start_at>=? AND p.start_at<? '
        'AND (? IS NULL OR p.id=?) AND (? IS NULL OR m.student_id=?) ORDER BY p.id,m.student_id',
        (cutoff, course_id, kind, start, end, paper_id, paper_id, subject, subject))]
    if subject is not None:
        assigned = {row['paper_id'] for row in rows}
        papers = [paper for paper in papers if paper['id'] in assigned]
    return {'kind': kind, 'papers': papers, 'assignments': rows, 'subject_student_id': subject}


def metrics(snapshot, start, end):
    papers = {p['id']: p for p in snapshot['papers'] if start <= p['start_at'] < end}
    rows = [r for r in snapshot['assignments'] if r['paper_id'] in papers]
    submitted = sum(r['attempt_id'] is not None for r in rows)
    partial = sum(r['status'] == 'partial' for r in rows)
    graded = [r for r in rows if r['status'] == 'graded' and r['score_hundredths'] is not None]
    frame = pd.DataFrame([{'score': r['score_hundredths'] / 100,
                           'percentage': 100 * r['score_hundredths'] / papers[r['paper_id']]['total_hundredths']}
                          for r in graded], columns=['score', 'percentage'])
    bins, _ = np.histogram(frame['percentage'].to_numpy(dtype=float), bins=[0, 60, 70, 80, 90, 100])
    return {'kind': snapshot['kind'], 'selected_paper_ids': sorted(papers),
            'expected_count': len(rows), 'submitted_count': submitted, 'missing_count': len(rows) - submitted,
            'graded_count': len(graded), 'partial_count': partial,
            'mean_score': round(float(frame['score'].mean()), 2) if graded and len(papers) == 1 else None,
            'mean_percentage': round(float(frame['percentage'].mean()), 2) if graded else None,
            'score_bins': [{'label': label, 'count': int(count)} for label, count in zip(BIN_LABELS, bins, strict=True)]}


def calculate(snapshot, start, end, cutoff):
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
    return {'dimension': 'scores', 'sample_size': overall['graded_count'], 'metrics': overall, 'series': series,
            'source_until': cutoff, 'algorithm_version': VERSION,
            'population_basis': 'paper_start_at;frozen_paper_student_assignments;graded_attempts_only',
            'unit': {'mean_score': 'points', 'mean_percentage': 'percent', 'score_bins': 'percent'},
            'warnings': ['应交按冻结名单计人卷次；缺交和待批不计均分；跨卷只比较百分比，未提交不代表0分']}
