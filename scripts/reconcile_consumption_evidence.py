"""Independent JSON/raw-table arithmetic; never calls production calculation code."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def reconcile(facts):
    assert facts['foreign_key_check'] == []
    tags = {}
    for row in facts['question_knowledge']:
        tags.setdefault(row['question_version_id'], []).append(row['knowledge_id'])
    practices = {p['id']: p for p in facts['practice_attempt']}
    checked = []
    for row in facts['analysis_run']:
        raw, value = json.loads(row['input_snapshot_json']), json.loads(row['result_json'])
        metrics = value['metrics']
        if row['kind'] == 'knowledge':
            samples = raw['samples']
            assert len({(s['source'], s['sample_id']) for s in samples}) == len(samples)
            for sample in samples:
                if sample['source'] == 'practice':
                    source = practices[sample['sample_id']]
                    assert (sample['student_id'], sample['question_version_id'], sample['correct']) == (
                        source['student_id'], source['question_version_id'], source['correct'])
                    assert sample['knowledge_ids'] == sorted(tags.get(source['question_version_id'], []))
            assert metrics['answered_count'] == len(samples)
            assert metrics['correct_count'] == sum(s['correct'] for s in samples)
            for item in metrics['items']:
                subset = [s for s in samples if item['knowledge_id'] in s['knowledge_ids']]
                assert (item['answered_count'], item['correct_count'], item['wrong_count']) == (
                    len(subset), sum(s['correct'] for s in subset), sum(not s['correct'] for s in subset))
        elif row['kind'] == 'scores':
            assignments = raw['assignments']
            counts = Counter(a['status'] if a['attempt_id'] is not None else 'missing' for a in assignments)
            assert metrics['expected_count'] == len(assignments)
            assert metrics['submitted_count'] == len(assignments) - counts['missing']
            assert metrics['missing_count'] == counts['missing']
            assert metrics['graded_count'] == counts['graded']
            assert metrics['partial_count'] == counts['partial']
            totals = {p['id']: p['total_hundredths'] for p in raw['papers']}
            percentages = [a['score_hundredths'] / totals[a['paper_id']] * 100
                           for a in assignments if a['status'] == 'graded']
            expected = round(sum(percentages) / len(percentages), 2) if percentages else None
            assert metrics['mean_percentage'] == expected
            bins = [0] * 5
            for percentage in percentages:
                bins[sum(percentage >= edge for edge in (60, 70, 80, 90))] += 1
            assert [b['count'] for b in metrics['score_bins']] == bins
        checked.append({'id': row['id'], 'kind': row['kind'], 'sample_size': value['sample_size']})
    for snapshot in facts['generation_snapshot']:
        selected = json.loads(snapshot['selected_ids_json'])
        paper = next(p for p in facts['paper'] if p['generation_snapshot_id'] == snapshot['id'])
        items = sorted((v for v in facts['paper_item'] if v['paper_id'] == paper['id']), key=lambda v: v['position'])
        assert [v['question_version_id'] for v in items] == selected
        assert len({v['question_id'] for v in items}) == 3
        assert [v['points_hundredths'] for v in items] == [334, 334, 333]
        assert sum(v['points_hundredths'] for v in items) == 1001
        assert len([v for v in facts['paper_participant'] if v['paper_id'] == paper['id']]) == 3
    return checked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    result = {'status': 'passed', 'inputs': [], 'scope': 'Independent arithmetic from saved raw facts; no model calculators'}
    paths = [args.evidence / 'handlers' / (name + '.json') for name in (
        'test_recommendation_practice_wrong_facts_and_saved_knowledge',
        'test_generated_quiz_attempts_classified_scores_and_two_immutable_snapshots')]
    paths += [args.evidence / 'browsers' / (channel + '-facts.json') for channel in ('chrome', 'msedge')]
    for path in paths:
        data = load(path)
        phases = {name: reconcile(phase['facts']) for name, phase in data['phases'].items()}
        final = reconcile(data['final_facts'])
        result['inputs'].append({'path': str(path.relative_to(args.evidence)),
                                 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                 'phases': phases, 'final': final})
    (args.evidence / 'reconciliation.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Independent consumption facts reconciliation passed')


if __name__ == '__main__':
    main()
