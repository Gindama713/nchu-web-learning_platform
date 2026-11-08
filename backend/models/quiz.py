"""SPEC-008 projections of frozen papers and current grading facts."""

import json

from backend.models import attempt
from backend.shared.api import ApiError, audit


def ensure_quiz(row):
    if row['kind'] != 'quiz':
        raise ApiError(409, 'STATE_CONFLICT', '此入口仅接受随堂测')


def review(db, row, at):
    ensure_quiz(row)
    if row['status'] != 'published' or at < row['end_at']:
        raise ApiError(409, 'WINDOW_OPEN', '仅已截止的随堂测可发布讲评')
    # Retry preserves the first publication time, including ordinary timed quizzes.
    if row['review_at'] is not None:
        return row['review_at']
    db.execute('UPDATE paper SET review_at=? WHERE id=? AND review_at IS NULL', (at, row['id']))
    audit('quiz.review', 'paper', row['id'], before={'review_at': None}, after={'review_at': at})
    return at


def statistics(db, row, at):
    """Caller holds one read transaction, including auth and source_until capture."""
    ensure_quiz(row)
    paper_id = row['id']
    expected = db.execute('SELECT count(*) FROM paper_participant WHERE paper_id=?', (paper_id,)).fetchone()[0]
    submitted = db.execute('SELECT count(*) FROM attempt a JOIN paper_participant pp '
                           'ON pp.paper_id=a.paper_id AND pp.student_id=a.student_id '
                           'WHERE a.paper_id=?', (paper_id,)).fetchone()[0]
    # Aggregate in SQLite rather than materializing student identities or full answers.
    facts = {item['question_version_id']: item for item in db.execute(
        'SELECT a.question_version_id,sum(a.answered) AS answered,count(a.score_hundredths) AS graded,'
        'sum(a.score_hundredths IS NULL) AS pending,avg(a.score_hundredths) AS mean_score,'
        'sum(a.answered=1 AND a.score_hundredths=i.points_hundredths) AS correct '
        'FROM answer a JOIN attempt t ON t.id=a.attempt_id '
        'JOIN paper_participant pp ON pp.paper_id=t.paper_id AND pp.student_id=t.student_id '
        'JOIN paper_item i ON i.paper_id=t.paper_id AND i.question_version_id=a.question_version_id '
        'WHERE t.paper_id=? GROUP BY a.question_version_id', (paper_id,))}
    selections = {}
    for item in db.execute(
            'SELECT a.question_version_id,j.value,count(*) AS selected FROM answer a '
            'JOIN attempt t ON t.id=a.attempt_id '
            'JOIN paper_participant pp ON pp.paper_id=t.paper_id AND pp.student_id=t.student_id '
            'JOIN question_version v ON v.id=a.question_version_id JOIN json_each(a.value_json) j '
            "WHERE t.paper_id=? AND a.answered=1 AND v.type IN ('single','multiple') "
            'GROUP BY a.question_version_id,j.value', (paper_id,)):
        selections[(item['question_version_id'], item['value'])] = item['selected']
    questions, objective_count, correct_total = [], 0, 0
    for item in attempt.items(db, paper_id):
        fact = facts.get(item['id'])
        answered, graded, pending = (fact[key] for key in ('answered', 'graded', 'pending')) if fact else (0, 0, 0)
        correct = None if item['type'] == 'short' else (fact['correct'] if fact else 0)
        if correct is not None:
            objective_count += 1
            correct_total += correct
        options = []
        for option in json.loads(item['options_json']):
            count = selections.get((item['id'], option['key']), 0)
            options.append({**option, 'selected_count': count,
                            'selection_rate': count / submitted if submitted else None})
        questions.append({'question_version_id': item['id'], 'type': item['type'],
                          'max_score': item['points_hundredths'] / 100,
                          'submitted_count': submitted, 'answered_count': answered,
                          'unanswered_count': submitted - answered, 'graded_count': graded,
                          'pending_count': pending, 'correct_count': correct,
                          'correct_rate': correct / submitted if correct is not None and submitted else None,
                          'mean_score': fact['mean_score'] / 100 if graded else None, 'options': options})
    denominator = submitted * objective_count
    return {'quiz_id': paper_id, 'source_until': at, 'expected_count': expected,
            'submitted_count': submitted, 'missing_count': expected - submitted,
            'objective_correct_rate': correct_total / denominator if denominator else None,
            'questions': questions}
