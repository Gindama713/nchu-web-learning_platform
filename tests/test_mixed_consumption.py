"""Two finite consumption seams; all business facts use actual API handlers."""

import hashlib
import json
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from backend.shared.db import connect
from tests.test_generation_input import parameters
from tests.test_question_validation import question
from tests.test_questions import ORIGIN, QuestionApiBase


def redact(value):
    if isinstance(value, dict):
        return {k: '[REDACTED]' if k.lower() in {
            'password', 'csrf_token', 'secret', 'secret_key', 'cookie', 'set-cookie',
            'authorization', 'x-csrf-token', 'password_hash'} else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


class MixedConsumptionTest(QuestionApiBase):
    output = None
    hook = None

    def setUp(self):
        self.requests, self.stages = [], {}
        super().setUp()
        self.knowledge_fixture()
        self.analytics = f'/courses/{self.course_id}/analytics'
        self.addCleanup(self.save_evidence)

    def record(self, client, method, path, body, response):
        self.requests.append({'transport': 'real Flask handler', 'actor':
            next((name for name in ('admin', 'teacher', 'student', 'outsider', 'third')
                  if client is getattr(self, name, None)), 'bootstrap'),
            'at': self.app.config['TEST_NOW'].isoformat(), 'method': method, 'path': path,
            'request': redact(body), 'status': response.status_code,
            'response_sha256': hashlib.sha256(response.data).hexdigest(),
            'response': redact(response.json) if response.is_json else response.get_data(as_text=True)})

    def call(self, client, method, path, data=None, status=200):
        response = super().call(client, method, path, data, status)
        self.record(client, method, path, data, response)
        return response

    def post_fact(self, client, path, payload):
        response = client.post('/api/v1' + path, json=payload, headers={
            'Origin': ORIGIN, 'X-CSRF-Token': client.csrf, 'Idempotency-Key': str(uuid4())})
        self.record(client, 'POST', path, payload, response)
        self.assertEqual(response.status_code, 201, response.json)
        return response.json['data']

    def clock(self, value):
        self.app.config['TEST_NOW'] = datetime.fromisoformat(value)
        for name, number in (('admin', 'T006ADMIN'), ('teacher', 'T006TEACH'),
                             ('student', 'T006STUD1'), ('outsider', 'T006STUD2'), ('third', 'MIXSTUD3')):
            if hasattr(self, name):
                self.login(getattr(self, name), number)

    def create(self, **values):
        return self.call(self.teacher, 'POST', self.url, question(**values), 201).json['data']

    def facts(self):
        tables = ('question', 'question_version', 'question_knowledge', 'paper', 'paper_item',
                  'paper_participant', 'attempt', 'answer', 'practice_attempt', 'wrong_question',
                  'generation_snapshot', 'analysis_run', 'audit_event')
        with closing(connect(self.path)) as db:
            result = {table: [dict(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]
                      for table in tables}
            result['foreign_key_check'] = [list(row) for row in db.execute('PRAGMA foreign_key_check')]
        return result

    def stage(self, name, **values):
        self.stages[name] = {'values': values, 'facts': self.facts()}
        if self.hook:
            self.hook(name, values)

    def save_evidence(self):
        if self.output:
            destination = Path(self.output)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / (self._testMethodName + '.json')).write_text(json.dumps({
                'requests': self.requests, 'stages': self.stages}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def query(self, dimension, suffix='', client=None):
        return self.call(client or self.teacher, 'GET', self.analytics +
                         '?dimension=' + dimension + suffix).json['data']

    def export(self, data):
        return self.call(self.teacher, 'GET', self.analytics +
                         f"/export?analysis_run_id={data['analysis_run_id']}&format=csv").data

    def restore(self, data, client=None):
        restored = self.call(client or self.teacher, 'GET', self.analytics +
                             f"?analysis_run_id={data['analysis_run_id']}").json['data']
        self.assertEqual(restored, data)

    def grade(self, attempt, version, score):
        return self.call(self.teacher, 'PATCH', f"/attempts/{attempt['id']}/manual-scores", {
            'revision': attempt['revision'], 'items': [
                {'question_version_id': version, 'score': score, 'comment': '受控消费核对'}]}).json['data']

    def generate(self, kind, total, difficulty):
        return self.call(self.teacher, 'POST', f'/courses/{self.course_id}/generated-papers', {
            'title': f'消费接缝 {kind} {total}', **parameters(kind=kind, total_points=total, count=2,
            difficulty_counts=difficulty, knowledge_ids=[1, 2])}, 201).json['data']

    def publish(self, paper, start):
        at = datetime.fromisoformat(start)
        return self.call(self.teacher, 'POST', f"/papers/{paper['paper_id']}/publish", {
            'start_at': start, 'end_at': (at + timedelta(hours=1)).isoformat(),
            'review_at': (at + timedelta(hours=2)).isoformat(),
            'confidentiality_note': '受控私有题，未公开且非简单复制'}).json['data']

    def submit(self, paper, answers, client=None, quiz=False):
        return self.post_fact(client or self.student, f"/{'quizzes' if quiz else 'papers'}/{paper}/attempts",
                              {'answers': [{'question_version_id': q['version_id'], 'value': v}
                                           for q, v in answers]})

    def test_generated_homework_exam_cross_paper_scores_and_saved_snapshots(self):
        self.clock('2026-10-05T12:00:00Z')
        self.third = self.app.test_client()
        self.call(self.third, 'POST', '/auth/register', {
            'student_no': 'MIXSTUD3', 'name': '受控学生三', 'password': self.password}, 201)
        self.login(self.third, 'MIXSTUD3')
        for client in (self.outsider, self.third):
            student = self.call(client, 'GET', '/auth/session').json['data']['user']['id']
            self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members',
                      {'user_id': student, 'member_role': 'student'}, 201)
        objective = self.create(knowledge_ids=[1, 2])
        short = self.create(type='short', difficulty='medium', options=[], answer='受控参考')
        hw1 = self.generate('homework', 10.01, {'easy': 1, 'medium': 1, 'hard': 0})
        hw2 = self.generate('homework', 20.02, {'easy': 1, 'medium': 1, 'hard': 0})
        exam_q = self.create(difficulty='hard', knowledge_ids=[1, 2])
        exam_short = self.create(type='short', difficulty='hard', options=[], answer='受控参考')
        exam = self.generate('exam', 30.03, {'easy': 0, 'medium': 0, 'hard': 2})
        self.assertEqual(hw1['points_hundredths'], [501, 500])
        self.assertEqual(hw2['points_hundredths'], [1001, 1001])
        self.assertEqual(exam['points_hundredths'], [1502, 1501])
        self.stage('a-generated-drafts', generated=[hw1, hw2, exam])
        for paper, start in ((hw1, '2026-10-06T12:00:00Z'), (hw2, '2026-10-13T12:00:00Z'),
                             (exam, '2026-10-13T12:00:00Z')):
            self.publish(paper, start)
        frozen = self.facts()['generation_snapshot']
        self.stage('a-published', generated=[hw1, hw2, exam])
        self.clock('2026-10-06T12:30:00Z')
        pending = self.submit(hw1['paper_id'], [(objective, 'A'), (short, '受控作答一')])
        self.submit(hw1['paper_id'], [], self.outsider)
        self.clock('2026-10-13T12:30:00Z')
        full = self.submit(hw2['paper_id'], [(objective, 'A'), (short, '受控作答二')])
        self.grade(full, short['version_id'], 10.01)
        exam_pending = self.submit(exam['paper_id'], [(exam_q, 'B'), (exam_short, '受控考试作答')])
        self.submit(exam['paper_id'], [(exam_q, 'A')], self.outsider)
        self.clock('2026-10-13T13:30:00Z')
        old_hw = self.query('scores', '&kind=homework')
        old_exam = self.query('scores', '&kind=exam')
        old_csv = [self.export(value) for value in (old_hw, old_exam)]
        fields = ('expected_count', 'submitted_count', 'missing_count', 'graded_count', 'partial_count')
        self.assertEqual([old_hw['metrics'][k] for k in fields], [6, 3, 3, 2, 1])
        self.assertEqual([old_exam['metrics'][k] for k in fields], [3, 2, 1, 1, 1])
        self.assertEqual(old_hw['metrics']['mean_percentage'], 50)
        self.assertIsNone(old_hw['metrics']['mean_score'])
        self.assertEqual(self.query('scores', '&kind=quiz')['metrics']['expected_count'], 0)
        self.stage('a-pending-scores', homework=old_hw, exam=old_exam)
        self.grade(pending, short['version_id'], 3)
        exam_points = self.call(self.teacher, 'GET', f"/papers/{exam['paper_id']}").json['data']['items']
        manual_max = next(row['points'] for row in exam_points if row['question_version_id'] == exam_short['version_id'])
        self.grade(exam_pending, exam_short['version_id'], manual_max)
        newer = self.call(self.teacher, 'PATCH', f"/questions/{objective['id']}",
                          {'answer': 'B', 'knowledge_ids': [2]}).json['data']
        new_hw = self.query('scores', '&kind=homework')
        new_exam = self.query('scores', '&kind=exam')
        single = self.query('scores', f"&kind=homework&paper_id={hw2['paper_id']}")
        self.assertEqual([new_hw['metrics'][k] for k in fields], [6, 3, 3, 3, 0])
        self.assertEqual(new_hw['metrics']['mean_percentage'], 59.97)
        self.assertIsNone(new_hw['metrics']['mean_score'])
        self.assertEqual(single['metrics']['mean_score'], 20.02)
        self.assertEqual(new_exam['metrics']['mean_percentage'], 50)
        self.assertEqual([b['count'] for b in new_hw['metrics']['score_bins']], [1, 0, 1, 0, 1])
        self.assertEqual(self.facts()['generation_snapshot'], frozen)
        detail = self.call(self.teacher, 'GET', f"/papers/{hw1['paper_id']}").json['data']
        original = next(row for row in detail['items'] if row['question_version_id'] == objective['version_id'])
        self.assertEqual(original['answer'], 'A')
        self.assertNotEqual(newer['version_id'], original['question_version_id'])
        for value, csv_bytes in zip((old_hw, old_exam), old_csv, strict=True):
            self.restore(value)
            self.assertEqual(self.export(value), csv_bytes)
        self.stage('a-new-scores', homework=new_hw, exam=new_exam, single=single,
                   old_homework=old_hw, old_exam=old_exam)

    def test_mixed_practice_quiz_versions_recommendation_and_weekly_knowledge(self):
        self.clock('2026-10-11T15:50:00Z')
        public = self.create(practice_available=True, knowledge_ids=[1, 2])
        objective = self.create(knowledge_ids=[1, 2])
        omitted = self.create(type='boolean', options=[], answer=True, knowledge_ids=[2])
        short = self.create(type='short', options=[], answer='受控参考')
        quiz = self.call(self.teacher, 'POST', f'/courses/{self.course_id}/papers', {
            'title': '两周混合来源测验', 'kind': 'quiz', 'confidential': True,
            'items': [{'question_version_id': q['version_id'], 'points': 10}
                      for q in (objective, omitted, short)]}, 201).json['data']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/quizzes', {
            'paper_id': quiz['id'], 'start_at': '2026-10-11T15:55:00Z',
            'end_at': '2026-10-11T16:10:00Z', 'confidentiality_note': '受控未公开题'}, 201)
        self.clock('2026-10-11T15:58:00Z')
        self.post_fact(self.student, f"/questions/{public['id']}/practice-attempts", {
            'question_version_id': public['version_id'], 'answer': 'B'})
        self.app.config['TEST_NOW'] += timedelta(milliseconds=1)
        before = self.call(self.student, 'GET', f'/courses/{self.course_id}/recommendations').json['data']
        self.assertEqual([(r['sample_size'], r['mastery']) for r in before['items']], [(1, 0), (1, 0)])
        self.clock('2026-10-11T15:59:00Z')
        attempt = self.submit(quiz['id'], [(objective, 'A'), (short, '受控简答')], quiz=True)
        self.app.config['TEST_NOW'] += timedelta(milliseconds=1)
        after_quiz = self.call(self.student, 'GET', f'/courses/{self.course_id}/recommendations').json['data']
        self.assertEqual([(r['sample_size'], r['mastery']) for r in after_quiz['items']], [(2, .5), (2, .5)])
        old = self.query('knowledge', client=self.student)
        teacher_old = self.query('knowledge', f'&student_id={self.student_id}')
        old_csv = self.export(teacher_old)
        self.stage('b-first-week', recommendation=after_quiz, knowledge=old)
        self.clock('2026-10-12T00:05:00Z')
        v2 = self.call(self.teacher, 'PATCH', f"/questions/{public['id']}",
                       {'answer': 'B', 'knowledge_ids': [2]}).json['data']
        self.call(self.teacher, 'PATCH', f"/questions/{objective['id']}", {'answer': 'B', 'knowledge_ids': [2]})
        self.post_fact(self.student, f"/questions/{public['id']}/practice-attempts", {
            'question_version_id': v2['version_id'], 'answer': 'B'})
        self.post_fact(self.student, f"/questions/{public['id']}/practice-attempts", {
            'question_version_id': v2['version_id'], 'answer': None})
        self.app.config['TEST_NOW'] += timedelta(milliseconds=1)
        suffix = '&from=2026-10-04T16:00:00Z&to=2026-10-12T00:05:00.001Z'
        new = self.query('knowledge', suffix, self.student)
        recommendation = self.call(self.student, 'GET', f'/courses/{self.course_id}/recommendations').json['data']
        self.assertEqual((new['sample_size'], new['metrics']['correct_count']), (3, 2))
        self.assertEqual([(p['answered_count'], p['correct_count']) for p in new['metrics']['items']], [(2, 1), (3, 2)])
        self.assertEqual([(s['metrics']['answered_count'], s['metrics']['correct_count']) for s in new['series']],
                         [(2, 1), (1, 1)])
        self.assertEqual(new['series'][0]['period_end'], '2026-10-11T16:00:00.000Z')
        self.assertEqual([(r['knowledge_id'], r['sample_size'], r['mastery'], r['score'], r['question_version_id'])
                          for r in recommendation['items']], [(1, 2, .5, .6, None), (2, 3, 2 / 3, .466667, v2['version_id'])])
        self.grade(attempt, short['version_id'], 8)
        self.assertEqual(self.query('knowledge', suffix, self.student)['metrics'], new['metrics'])
        self.assertEqual(self.call(self.student, 'GET', f'/courses/{self.course_id}/recommendations').json['data'],
                         recommendation)
        self.restore(old, self.student)
        self.restore(teacher_old)
        self.assertEqual(self.export(teacher_old), old_csv)
        with closing(connect(self.path)) as db:
            raw = json.loads(db.execute('SELECT input_snapshot_json FROM analysis_run WHERE id=?',
                                        (new['analysis_run_id'],)).fetchone()[0])
        self.assertEqual({(r['source'], r['sample_id']) for r in raw['samples']},
                         {('practice', 1), ('practice', 2), ('answer', 1)})
        self.assertEqual([r['knowledge_ids'] for r in raw['samples']], [[1, 2], [1, 2], [2]])
        self.stage('b-second-week', knowledge=new, recommendation=recommendation,
                   old_knowledge=old, old_teacher=teacher_old, quiz_id=quiz['id'])
