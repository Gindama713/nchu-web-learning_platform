"""SPEC-010D: circuit grading teaching distribution with independent run reliability.

Teaching distribution is per (student, experiment version): the newest submission
that still owns an effective run supplies the score. Run reliability counts every
run, so platform failures never enter the teaching denominator.
"""

import json
from datetime import timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from backend.shared.api import ApiError, parse_time, stamp

VERSION = 'grading-teaching-v1'
EFFECTIVE_STATUSES = ('accepted', 'wrong_answer', 'timeout', 'resource_limit', 'invalid_circuit')
BIN_LABELS = ('[0,60)', '[60,70)', '[70,80)', '[80,90)', '[90,100]')
RELIABILITY_STATUSES = {'system_error': 'system_error_count', 'timeout': 'timeout_count',
                        'resource_limit': 'resource_limit_count'}
REQUIRED_TABLES = {'experiment', 'experiment_version', 'submission', 'grading_run', 'test_suite'}


def extract(db, course_id, start, end, cutoff, subject):
    """Read one consistent snapshot; the caller owns authorization and the transaction.

    ``start``/``end`` select published circuit versions by their frozen ``start_at``;
    submissions made after ``cutoff`` are excluded so a later retry cannot leak in.
    """
    names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not REQUIRED_TABLES <= names:
        raise ApiError(503, 'DEPENDENCY_UNAVAILABLE', 'Circuit grading tables are not installed')
    versions = []
    for row in db.execute(
            'SELECT v.id,v.experiment_id,v.submission_modes_json,v.start_at,v.end_at,e.code '
            'FROM experiment_version v JOIN experiment e ON e.id=v.experiment_id '
            "WHERE e.course_id=? AND v.status='published' ORDER BY v.id", (course_id,)):
        try:
            modes = json.loads(row['submission_modes_json'])
        except (TypeError, ValueError):
            continue
        if not isinstance(modes, list) or 'circuit' not in modes:
            continue
        versions.append({'id': row['id'], 'experiment_id': row['experiment_id'],
                         'code': row['code'], 'start_at': row['start_at'], 'end_at': row['end_at']})
    submissions, runs = [], []
    version_ids = [version['id'] for version in versions]
    if version_ids:
        marks = ','.join('?' for _ in version_ids)
        submissions = [dict(row) for row in db.execute(
            f'SELECT id,experiment_version_id,student_id,created_at FROM submission '
            f'WHERE experiment_version_id IN ({marks}) AND created_at<=? '
            f'AND (? IS NULL OR student_id=?) ORDER BY id',
            (*version_ids, cutoff, subject, subject))]
        if submissions:
            sub_marks = ','.join('?' for _ in submissions)
            runs = [dict(row) for row in db.execute(
                f'SELECT id,submission_id,suite_id,status,score_hundredths FROM grading_run '
                f'WHERE submission_id IN ({sub_marks}) ORDER BY id',
                [submission['id'] for submission in submissions])]
    return {'versions': versions, 'submissions': submissions, 'runs': runs,
            'subject_student_id': subject}


def teaching_units(snapshot, start, end):
    """Pick the effective run per (student, version) from the newest usable submission.

    APIC §7: the newest submission by (created_at, id) that owns an effective run
    represents the student. Queued/running/system_error never replace a prior score.
    """
    versions = {version['id']: version for version in snapshot['versions']
                if version['start_at'] and start <= version['start_at'] < end}
    runs_by_submission = {}
    for run in snapshot['runs']:
        runs_by_submission.setdefault(run['submission_id'], []).append(run)
    units, submissions = {}, []
    ordered = sorted(snapshot['submissions'], key=lambda row: (row['created_at'], row['id']),
                     reverse=True)
    for submission in ordered:
        if submission['experiment_version_id'] not in versions:
            continue
        submissions.append(submission)
        effective = [run for run in runs_by_submission.get(submission['id'], [])
                     if run['status'] in EFFECTIVE_STATUSES]
        key = (submission['student_id'], submission['experiment_version_id'])
        if effective and key not in units:
            units[key] = max(effective, key=lambda run: run['id'])
    return versions, units, submissions, runs_by_submission


def bins_for(scores):
    counts, _ = np.histogram(np.asarray(scores, dtype=float), bins=[0, 60, 70, 80, 90, 100])
    return [{'label': label, 'count': int(count)}
            for label, count in zip(BIN_LABELS, counts, strict=True)]


def summarize(units, submissions, runs):
    """Shared metric shape for the course total and every suite group."""
    effective = list(units.values())
    scores = [run['score_hundredths'] / 100 for run in effective
              if run['score_hundredths'] is not None]
    accepted = sum(run['status'] == 'accepted' for run in effective)
    reliability = {key: 0 for key in RELIABILITY_STATUSES.values()}
    for run in runs:
        bucket = RELIABILITY_STATUSES.get(run['status'])
        if bucket:
            reliability[bucket] += 1
    return {
        'student_count': len({student for student, _version in units}),
        'submission_count': len(submissions),
        'effective_count': len(effective),
        'accepted_count': accepted,
        'pass_rate': round(accepted / len(effective), 6) if effective else None,
        'mean_score': round(float(pd.Series(scores, dtype=float).mean()), 2) if scores else None,
        'score_bins': bins_for(scores),
        'run_count': len(runs),
        **reliability,
    }


def suite_groups(units, submissions, runs_by_submission):
    """Group by suite_id; a submission is attributed to every suite that ran it.

    A suite that only ever produced system_error runs still appears, so reliability
    failures stay visible even where they contribute no teaching sample.
    """
    grouped = {}

    def group_for(suite_id):
        return grouped.setdefault(suite_id, {'units': {}, 'submissions': {}, 'runs': []})

    for submission in submissions:
        for run in runs_by_submission.get(submission['id'], []):
            group = group_for(run['suite_id'])
            group['submissions'][submission['id']] = submission
            group['runs'].append(run)
    for (student, version), run in units.items():
        group_for(run['suite_id'])['units'][(student, version)] = run
    return [{'suite_id': suite_id,
             **summarize(group['units'], list(group['submissions'].values()), group['runs'])}
            for suite_id, group in sorted(grouped.items())]


def metrics(snapshot, start, end):
    versions, units, submissions, runs_by_submission = teaching_units(snapshot, start, end)
    runs = [run for submission in submissions
            for run in runs_by_submission.get(submission['id'], [])]
    return {'selected_version_ids': sorted(versions), **summarize(units, submissions, runs),
            'suites': suite_groups(units, submissions, runs_by_submission)}


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
    return {'dimension': 'grading', 'sample_size': overall['effective_count'], 'metrics': overall,
            'series': series, 'source_until': cutoff, 'algorithm_version': VERSION,
            'population_basis': 'published_circuit_version_start_at;'
                                'per_student_version_effective_run;run_reliability_all_runs',
            'unit': {'pass_rate': 'ratio', 'mean_score': 'points', 'score_bins': 'points'},
            'warnings': [('教学通过率按每名学生每个实验版本的有效成绩计算；排队、运行中与系统错误不计入分母，'
                         '运行可靠性另行统计全部 run')]}
