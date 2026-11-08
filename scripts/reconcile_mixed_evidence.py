"""Independently reconcile saved raw facts; never calls business algorithms."""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path


def time(value):
    return datetime.fromisoformat(value)


def objective_facts(facts, student, start, end, cutoff):
    versions = {r['id']: r for r in facts['question_version']}
    labels = {}
    for row in facts['question_knowledge']:
        labels.setdefault(row['question_version_id'], []).append(row['knowledge_id'])
    attempts = {r['id']: r for r in facts['attempt']}
    result = []
    for source, rows in (('practice', facts['practice_attempt']), ('answer', facts['answer'])):
        for row in rows:
            version = row['question_version_id']
            parent = row if source == 'practice' else attempts[row['attempt_id']]
            event = row['created_at'] if source == 'practice' else parent['submitted_at']
            if (versions[version]['type'] == 'short' or not row['answered'] or parent['student_id'] != student
                    or not time(start) <= time(event) < time(end) or time(event) > time(cutoff)):
                continue
            result.append({'source': source, 'sample_id': row['id'], 'student_id': student,
                'question_version_id': version, 'event_at': event,
                'correct': row['correct'] if source == 'practice' else int(row['score_hundredths'] > 0),
                'knowledge_ids': sorted(labels.get(version, []))})
    return sorted(result, key=lambda r: (r['source'], r['sample_id']))


def knowledge_metrics(samples, metrics, start, end):
    rows = [r for r in samples if time(start) <= time(r['event_at']) < time(end)]
    assert len({(r['source'], r['sample_id']) for r in rows}) == len(rows)
    assert metrics['answered_count'] == len(rows)
    assert metrics['correct_count'] == sum(r['correct'] for r in rows)
    assert metrics['mastery'] == (sum(r['correct'] for r in rows) / len(rows) if rows else None)
    for point in metrics['items']:
        subset = [r for r in rows if point['knowledge_id'] in r['knowledge_ids']]
        n, c = len(subset), sum(r['correct'] for r in subset)
        assert (point['answered_count'], point['correct_count'], point['wrong_count'], point['mastery']) == (
            n, c, n - c, c / n if n else None)


def scores(facts, data):
    f = data['filters']
    papers = {r['id']: r for r in facts['paper'] if r['kind'] == data['metrics']['kind']
              and r['status'] == 'published' and time(f['from']) <= time(r['start_at']) < time(f['to'])}
    if f.get('paper_id'):
        papers = {k: v for k, v in papers.items() if k == f['paper_id']}
    attempts = {(r['paper_id'], r['student_id']): r for r in facts['attempt']
                if time(r['submitted_at']) <= time(data['source_until'])}
    totals = {pid: sum(i['points_hundredths'] for i in facts['paper_item'] if i['paper_id'] == pid) for pid in papers}

    def check(metrics, start, end):
        selected = {pid for pid, p in papers.items() if time(start) <= time(p['start_at']) < time(end)}
        rows = [r for r in facts['paper_participant'] if r['paper_id'] in selected]
        actual = [attempts.get((r['paper_id'], r['student_id'])) for r in rows]
        graded = [r for r in actual if r and r['status'] == 'graded']
        percentages = [100 * r['score_hundredths'] / totals[r['paper_id']] for r in graded]
        assert metrics['selected_paper_ids'] == sorted(selected)
        assert [metrics[k] for k in ('expected_count', 'submitted_count', 'missing_count', 'graded_count', 'partial_count')] == [
            len(rows), sum(r is not None for r in actual), sum(r is None for r in actual), len(graded),
            sum(r is not None and r['status'] == 'partial' for r in actual)]
        assert metrics['mean_percentage'] == (round(sum(percentages) / len(graded), 2) if graded else None)
        assert metrics['mean_score'] == (round(sum(r['score_hundredths'] / 100 for r in graded) / len(graded), 2)
                                          if graded and len(selected) == 1 else None)
        bins = [sum(low <= p < high or high == 100 and p == 100 for p in percentages)
                for low, high in ((0, 60), (60, 70), (70, 80), (80, 90), (90, 100))]
        assert [r['count'] for r in metrics['score_bins']] == bins
    check(data['metrics'], f['from'], f['to'])
    for series in data['series']:
        check(series['metrics'], series['period_start'], series['period_end'])


def reconcile(path):
    evidence = json.loads(path.read_text(encoding='utf-8'))
    stages = evidence['stages']
    if 'a-new-scores' in stages:
        first, pending, final = [stages[name] for name in ('a-generated-drafts', 'a-pending-scores', 'a-new-scores')]
        assert first['facts']['generation_snapshot'] == final['facts']['generation_snapshot']
        for generated in first['values']['generated']:
            items = [r for r in final['facts']['paper_item'] if r['paper_id'] == generated['paper_id']]
            items.sort(key=lambda r: r['position'])
            assert [r['question_version_id'] for r in items] == generated['selected_version_ids']
            assert [r['points_hundredths'] for r in items] == generated['points_hundredths']
            parent = next(r for r in final['facts']['paper'] if r['id'] == generated['paper_id'])
            assert parent['generation_snapshot_id'] == generated['generation_snapshot_id']
        for stage in (pending, final):
            for key in ('homework', 'exam'):
                scores(stage['facts'], stage['values'][key])
        scores(final['facts'], final['values']['single'])
        return {'file': str(path), 'scope': 'generated versions/source/points; category/cross-paper/weekly scores', 'result': 'passed'}
    final = stages['b-second-week']
    data, facts = final['values']['knowledge'], final['facts']
    run = next(r for r in facts['analysis_run'] if r['id'] == data['analysis_run_id'])
    original = json.loads(run['input_snapshot_json'])
    params = json.loads(run['parameters_json'])
    raw = objective_facts(facts, original['subject_student_id'], params['from'], params['to'], data['source_until'])
    assert raw == original['samples']
    knowledge_metrics(raw, data['metrics'], params['from'], params['to'])
    assert data['series'][0]['period_end'] == '2026-10-11T16:00:00.000Z'
    for series in data['series']:
        knowledge_metrics(raw, series['metrics'], series['period_start'], series['period_end'])
    rec = final['values']['recommendation']
    window = (time(rec['source_until']) - timedelta(days=28)).isoformat()
    rec_raw = objective_facts(facts, original['subject_student_id'], window, rec['source_until'], rec['source_until'])
    assert rec_raw == raw
    for item in rec['items']:
        rows = [r for r in rec_raw if item['knowledge_id'] in r['knowledge_ids']]
        mastery = sum(r['correct'] for r in rows) / len(rows)
        assert (item['sample_size'], item['mastery'], item['score'], item['reason']) == (
            len(rows), mastery, round(.8 * (1 - mastery) + .2, 6), 'insufficient_sample')
    return {'file': str(path), 'scope': 'raw practice/answer namespace, answered objective filter, fixed labels, two weeks, recommendation',
            'sources': [(r['source'], r['sample_id'], r['question_version_id'], r['knowledge_ids']) for r in raw], 'result': 'passed'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.evidence.rglob('test_*.json'))
    results = [reconcile(path) for path in paths if 'stages' in json.loads(path.read_text(encoding='utf-8'))]
    assert len(results) == 6, len(results)
    (args.evidence / 'reconciliation.json').write_text(json.dumps({
        'method': 'raw table joins and arithmetic; no business algorithm imports', 'checks': results,
        'result': 'passed'}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{len(results)} independent scenario reconciliations passed')


if __name__ == '__main__':
    main()
