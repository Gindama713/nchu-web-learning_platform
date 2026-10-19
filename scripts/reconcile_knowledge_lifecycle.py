"""Independently join retained raw facts; do not call analytics/recommendation/QA."""

import argparse
import json
from pathlib import Path


def reconcile(path):
    evidence = json.loads(path.read_text(encoding='utf-8'))
    original = evidence['stages']['original']['facts']
    old_ids = {evidence['stages']['original'][role]['analysis_run_id'] for role in ('student', 'teacher')}
    # The first snapshots predate the checkpoint's additional queries.
    frozen = [row for row in original['analysis_run'] if row['id'] in old_ids]
    checked = []
    for name, stage in evidence['stages'].items():
        facts = stage['facts']
        published = [row for row in facts['knowledge_point'] if row['published']]
        ids = {row['id'] for row in published}
        tags = {}
        for row in facts['question_knowledge']:
            tags.setdefault(row['question_version_id'], set()).add(row['knowledge_id'])
        for role in ('student', 'teacher'):
            if role not in stage:
                continue
            result = stage[role]
            filters, metrics = result['filters'], result['metrics']
            samples = [row for row in facts['practice_attempt'] if row['answered'] and
                       row['student_id'] == filters['student_id'] and
                       filters['from'] <= row['created_at'] < filters['to']]
            assert result['sample_size'] == metrics['answered_count'] == len(samples)
            correct = sum(row['correct'] for row in samples)
            assert metrics['correct_count'] == correct
            assert metrics['mastery'] == (correct / len(samples) if samples else None)
            assert filters['knowledge_ids'] == sorted(ids)
            assert [row['knowledge_id'] for row in metrics['items']] == sorted(ids)
            for item in metrics['items']:
                selected = [row for row in samples if item['knowledge_id'] in tags[row['question_version_id']]]
                point = next(row for row in published if row['id'] == item['knowledge_id'])
                assert item['title'] == point['title']
                assert item['answered_count'] == len(selected)
                assert item['correct_count'] == sum(row['correct'] for row in selected)
            done = sum(row['completed'] for row in facts['learning_progress']
                       if row['knowledge_id'] in ids and row['user_id'] == filters['student_id'])
            assert metrics['published_knowledge_count'] == len(ids)
            assert metrics['completed_knowledge_count'] == done
            assert metrics['progress'] == (done / len(ids) if ids else None)
            saved = next(row for row in facts['analysis_run'] if row['id'] == result['analysis_run_id'])
            inputs = json.loads(saved['input_snapshot_json'])
            assert {tuple(row['knowledge_ids']) for row in inputs['samples']} == (
                {(1, 2), (2,)} if samples else set())
        for table in ('practice_attempt', 'question_version', 'question_knowledge', 'learning_progress'):
            assert facts[table] == original[table], table
        assert [row for row in facts['analysis_run'] if row['id'] in old_ids] == frozen
        assert facts['foreign_key_check'] == []
        checked.append(name)
    return {'file': path.as_posix(), 'stages': checked, 'result': 'passed'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if len(args.files) > 3:
        parser.error('Read at most three evidence files per batch')
    results = [reconcile(path) for path in args.files]
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'result': 'passed', 'scenarios': len(results)}))


if __name__ == '__main__':
    main()
