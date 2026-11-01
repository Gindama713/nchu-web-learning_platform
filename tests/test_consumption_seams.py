"""Two narrow real-handler seams; no solver, failure injection or business SQL fixtures."""

import hashlib
import json
import os
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from backend.shared.db import connect
from tests.test_question_validation import question
from tests.test_questions import ORIGIN, QuestionApiBase


def redacted(value):
    if isinstance(value, dict):
        return {k: '[REDACTED]' if k in {'password', 'csrf_token', 'password_hash', 'session_id'}
                else redacted(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redacted(v) for v in value]
    return value


class ConsumptionSeamsTest(QuestionApiBase):
    def setUp(self):
        self.records, self.phases = [], {}
        super().setUp()
        self.knowledge_fixture()
        self.analytics = f'/courses/{self.course_id}/analytics'

    def call(self, client, method, path, data=None, status=200, *, key=None):
        headers = {'Origin': ORIGIN, 'X-CSRF-Token': getattr(client, 'csrf', '')}
        if key:
            headers['Idempotency-Key'] = key
        response = client.open('/api/v1' + path, method=method, json=data, headers=headers)
        raw = response.get_data()
        self.records.append({'transport': 'Flask real handler', 'method': method, 'path': path,
                             'request': redacted(data), 'idempotency_key': key,
                             'status': response.status_code, 'response': redacted(response.get_json(silent=True)),
                             'content_type': response.content_type,
                             'cache_control': response.headers.get('Cache-Control'),
                             'body_sha256': hashlib.sha256(raw).hexdigest(),
                             'csv': raw.decode('utf-8-sig') if 'text/csv' in response.content_type else None})
        self.assertEqual(response.status_code, status, self.records[-1])
        return response

    def facts(self):
        tables = ('course', 'course_member', 'chapter', 'knowledge_point', 'learning_progress',
                  'question', 'question_version', 'question_knowledge', 'practice_attempt', 'wrong_question',
                  'paper', 'paper_item', 'paper_participant', 'attempt', 'answer', 'generation_snapshot',
                  'analysis_run', 'audit_event')
        with closing(connect(self.path)) as db:
            result = {t: [dict(row) for row in db.execute(f'SELECT * FROM {t}')] for t in tables}
            result['foreign_key_check'] = [list(row) for row in db.execute('PRAGMA foreign_key_check')]
        return redacted(result)

    def phase(self, name, **values):
        self.phases[name] = {'values': values, 'facts': self.facts()}

    def tearDown(self):
        output = os.environ.get('CONSUMPTION_SEAMS_OUTPUT')
        if output:
            target = Path(output)
            target.mkdir(parents=True, exist_ok=True)
            (target / (self._testMethodName + '.json')).write_text(json.dumps({
                'requests': self.records, 'phases': self.phases, 'final_facts': self.facts(),
                'fixtures': 'Only initial admin/teacher SQL bootstrap, random secrets and TEST_NOW. '
                            'Students and all successful business objects use real APIs. SQL otherwise read only.',
            }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        super().tearDown()

    def create_question(self, **values):
        return self.call(self.teacher, 'POST', self.url, question(**values), 201).json['data']

    def advance(self, seconds=1):
        self.app.config['TEST_NOW'] += timedelta(seconds=seconds)

    def practice(self, q, value, key=None):
        return self.call(self.student, 'POST', f"/questions/{q['id']}/practice-attempts",
                         {'question_version_id': q['version_id'], 'answer': value}, 201, key=key or str(uuid4()))

    def recommendations(self):
        return self.call(self.student, 'GET', f'/courses/{self.course_id}/recommendations').json['data']

    def query(self, dimension, client=None, kind=None):
        return self.call(client or self.teacher, 'GET', self.analytics + '?dimension=' + dimension +
                         ('&kind=' + kind if kind else '')).json['data']

    def restore(self, value, client=None, status=200):
        return self.call(client or self.teacher, 'GET', self.analytics +
                         f"?analysis_run_id={value['analysis_run_id']}", status=status)

    def export(self, value):
        return self.call(self.teacher, 'GET', self.analytics +
                         f"/export?analysis_run_id={value['analysis_run_id']}&format=csv").data

    def test_recommendation_practice_wrong_facts_and_saved_knowledge(self):
        for kid in (1, 2):
            self.call(self.teacher, 'PATCH', f'/knowledge-points/{kid}', {'is_foundational': True})
        q = self.create_question(knowledge_ids=[1, 2], practice_available=True, explanation='原版A解析')
        cold = self.recommendations()
        self.assertEqual(cold['reason'], 'cold_start')
        self.assertEqual([v['question_version_id'] for v in cold['items']], [q['version_id']] * 2)
        zero = self.query('knowledge', self.student)
        self.assertEqual(zero['sample_size'], 0)
        key = str(uuid4())
        wrong = self.practice(q, 'B', key)
        self.assertEqual(self.practice(q, 'B', key).data, wrong.data)
        self.advance()
        rec_wrong = self.recommendations()
        old = self.query('knowledge')
        own = self.query('knowledge', self.student)
        csv_before = self.export(old)
        wrong_item = self.call(self.student, 'GET', '/users/me/wrong-questions').json['data'][0]
        self.assertEqual((wrong_item['wrong_count'], wrong_item['resolved'], wrong_item['question_version_id']),
                         (1, False, q['version_id']))
        self.assertEqual([v['sample_size'] for v in rec_wrong['items']], [1, 1])
        self.assertEqual((old['sample_size'], old['metrics']['correct_count']), (1, 0))
        self.phase('wrong', recommendation=rec_wrong, wrong=wrong_item, snapshot=old)
        newer = self.call(self.teacher, 'PATCH', f"/questions/{q['id']}",
                          {'answer': 'B', 'knowledge_ids': [2], 'explanation': '新版B解析'}).json['data']
        moved = self.recommendations()
        entries = {v['knowledge_id']: v['question_version_id'] for v in moved['items']}
        self.assertEqual(entries, {1: None, 2: newer['version_id']})
        # The wrong-book supplies the original version; recommendations supply the latest eligible version.
        self.practice({'id': wrong_item['question_id'], 'version_id': wrong_item['question_version_id']}, 'A')
        self.practice(newer, 'B')
        self.call(self.student, 'PUT', '/knowledge-points/1/progress', {'completed': True})
        self.advance()
        current = self.query('knowledge', self.student)
        rec_after = self.recommendations()
        fixed_wrong = self.call(self.student, 'GET', '/users/me/wrong-questions').json['data'][0]
        self.assertEqual((current['sample_size'], current['metrics']['correct_count']), (3, 2))
        self.assertEqual([(p['answered_count'], p['correct_count']) for p in current['metrics']['items']], [(2, 1), (3, 2)])
        self.assertEqual(current['metrics']['progress'], .5)
        self.assertEqual([(v['knowledge_id'], v['sample_size'], v['score']) for v in rec_after['items']],
                         [(2, 3, .466667), (1, 2, .4)])
        self.assertEqual((fixed_wrong['wrong_count'], fixed_wrong['resolved'], fixed_wrong['last_attempt_id']),
                         (1, True, wrong_item['last_attempt_id']))
        self.assertEqual(fixed_wrong['question_version_id'], q['version_id'])
        self.assertEqual(self.restore(zero, self.student).json['data'], zero)
        self.assertEqual(self.restore(own, self.student).json['data'], own)
        self.assertEqual(self.restore(old).json['data'], old)
        self.assertEqual(self.export(old), csv_before)
        with closing(connect(self.path)) as db:
            raw = json.loads(db.execute('SELECT input_snapshot_json FROM analysis_run WHERE id=?',
                                       (current['analysis_run_id'],)).fetchone()[0])
            self.assertEqual(len(raw['samples']), 3)
            self.assertEqual({v['source'] for v in raw['samples']}, {'practice'})
        self.phase('after_versions_and_progress', current=current, recommendation=rec_after, wrong=fixed_wrong)
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{self.student_id}', status=204)
        self.call(self.student, 'GET', f'/courses/{self.course_id}/recommendations', status=404)
        self.assertEqual(self.call(self.student, 'GET', '/users/me/wrong-questions').json['data'], [])
        self.restore(own, self.student, 404)
        self.assertEqual(self.export(old), csv_before)
        self.phase('revoked', saved_class=old)

    def seed_generation(self):
        other_id = self.call(self.outsider, 'GET', '/auth/session').json['data']['user']['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members',
                  {'user_id': other_id, 'member_role': 'student'}, 201)
        absent = self.app.test_client()
        absent_id = self.call(absent, 'POST', '/auth/register',
                              {'student_no': 'TSEAMMISS', 'name': '缺交样本', 'password': self.password}, 201).json['data']['user']['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members',
                  {'user_id': absent_id, 'member_role': 'student'}, 201)
        qs = [self.create_question(knowledge_ids=[1, 2], stem='生成卷客观题', explanation='原固定A'),
              self.create_question(type='boolean', options=[], answer=True, difficulty='medium', knowledge_ids=[2]),
              self.create_question(type='short', options=[], answer='原参考', difficulty='hard', knowledge_ids=[1])]
        return qs

    def test_generated_quiz_attempts_classified_scores_and_two_immutable_snapshots(self):
        qs = self.seed_generation()
        first = self.call(self.teacher, 'POST', f'/courses/{self.course_id}/generated-papers', {
            'title': '013→008→010B', 'kind': 'quiz', 'count': 3, 'total_points': 10.01,
            'knowledge_ids': [1, 2], 'difficulty_counts': {'easy': 1, 'medium': 1, 'hard': 1},
            'seed': 42, 'confidential': True}, 201).json['data']
        self.assertEqual(first['points_hundredths'], [334, 334, 333])
        pid = first['paper_id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/quizzes', {
            'paper_id': pid, 'start_at': '2026-10-13T12:00:00Z', 'end_at': '2026-10-13T12:10:00Z',
            'confidentiality_note': '未公开且非简单复制确认'}, 201)
        before = self.facts()['generation_snapshot'][0]
        self.advance()
        values = [{'question_version_id': q['version_id'], 'value': v}
                  for q, v in zip(qs, ('A', False, '人工回答'), strict=True)]
        key = str(uuid4())
        submitted = self.call(self.student, 'POST', f'/quizzes/{pid}/attempts', {'answers': values}, 201, key=key)
        pending = submitted.json['data']
        self.call(self.outsider, 'POST', f'/quizzes/{pid}/attempts', {'answers': []}, 201, key=str(uuid4()))
        self.advance(601)
        stats = self.call(self.teacher, 'GET', f'/quizzes/{pid}/statistics').json['data']
        old = self.query('scores', kind='quiz')
        old_csv = self.export(old)
        self.assertEqual([old['metrics'][k] for k in ('expected_count', 'submitted_count', 'missing_count',
                                                     'graded_count', 'partial_count', 'mean_percentage')], [3, 2, 1, 1, 1, 0])
        for kind in ('exam', 'homework'):
            empty = self.query('scores', kind=kind)
            self.assertEqual(empty['metrics']['expected_count'], 0)
        self.assertEqual(stats['objective_correct_rate'], .25)
        self.phase('generated_pending', generation=first, stats=stats, scores=old)
        points = dict(zip(first['selected_version_ids'], first['points_hundredths'], strict=True))
        manual_points = points[qs[2]['version_id']]
        self.call(self.teacher, 'PATCH', f"/attempts/{pending['id']}/manual-scores", {
            'revision': 0, 'items': [{'question_version_id': qs[2]['version_id'],
                                    'score': manual_points / 100, 'comment': '生成卷按固定配分批阅'}]})
        self.call(self.teacher, 'POST', f'/quizzes/{pid}/review', {})
        self.call(self.teacher, 'PATCH', f"/questions/{qs[0]['id']}", {'answer': 'B', 'knowledge_ids': [2]})
        self.create_question(stem='后续新增候选', difficulty='hard')
        self.advance()
        newer = self.query('scores', kind='quiz')
        expected_percentage = round((points[qs[0]['version_id']] + manual_points) / 1001 * 100 / 2, 2)
        self.assertEqual(newer['metrics']['mean_percentage'], expected_percentage)
        self.assertEqual((newer['metrics']['graded_count'], newer['metrics']['partial_count']), (2, 0))
        self.assertEqual(self.restore(old).json['data'], old)
        self.assertEqual(self.export(old), old_csv)
        self.assertEqual(self.call(self.student, 'POST', f'/quizzes/{pid}/attempts',
                                   {'answers': values}, 201, key=key).data, submitted.data)
        detail = self.call(self.student, 'GET', f'/papers/{pid}').json['data']
        self.assertEqual(next(v for v in detail['items'] if v['question_version_id'] == qs[0]['version_id'])['answer'], 'A')
        # Actual student exposure makes the original identities public forever. A confidential
        # replay must reject current eligibility, while leaving the saved input and paper intact.
        replay = self.call(self.teacher, 'POST', f'/courses/{self.course_id}/generated-papers',
                           {'title': '已作答后严格重放', 'replay_of': first['generation_snapshot_id']}, 409).json
        self.assertEqual(replay['error']['code'], 'QUESTION_PUBLIC')
        rows = self.facts()['generation_snapshot']
        self.assertEqual(rows[0], before)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(self.facts()['paper']), 1)
        self.assertEqual(self.query('scores', kind='quiz')['metrics']['expected_count'], 3)
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{self.student_id}', status=204)
        self.call(self.student, 'GET', f'/papers/{pid}', status=404)
        self.assertEqual(self.query('scores', kind='quiz')['metrics']['expected_count'], 3)
        self.assertEqual(self.export(old), old_csv)
        self.phase('graded_replayed_revoked', generation=replay, current_scores=newer)
