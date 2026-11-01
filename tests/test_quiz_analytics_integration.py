"""R33 dedicated 008 HTTP -> immutable 010B knowledge/scores/CSV integration."""

from contextlib import closing
from datetime import UTC, datetime
from uuid import uuid4

from backend.shared.db import connect, migrate
from tests.test_attempts import AttemptApiBase
from tests.test_question_validation import question


class QuizAnalyticsIntegrationTest(AttemptApiBase):
    def setUp(self):
        super().setUp()
        self.knowledge_fixture()
        self.analytics = f'/courses/{self.course_id}/analytics'

    def create(self, **values):
        return self.call(self.teacher, 'POST', self.url, question(**values), 201).json['data']

    def query(self, dimension, client=None):
        suffix = '&kind=quiz' if dimension == 'scores' else ''
        return self.call(client or self.teacher, 'GET', self.analytics + '?dimension=' + dimension + suffix)

    def restore(self, run, client=None, status=200):
        return self.call(client or self.teacher, 'GET', self.analytics + f'?analysis_run_id={run}', status=status)

    def export(self, run, status=200):
        return self.call(self.teacher, 'GET', self.analytics + f'/export?analysis_run_id={run}&format=csv', status=status)

    def at(self, hour, minute=0):
        self.app.config['TEST_NOW'] = datetime(2026, 10, 13, hour, minute, tzinfo=UTC)
        self.login(self.teacher, 'T006TEACH')
        self.login(self.student, 'T006STUD1')
        self.login(self.outsider, 'T006STUD2')

    def test_real_dedicated_quiz_partial_missing_omitted_review_grade_old_ids_and_backup(self):
        other = self.outsider.get('/api/v1/auth/session').json['data']['user']['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members', {'user_id': other, 'member_role': 'student'}, 201)
        missing = self.app.test_client()
        self.call(missing, 'POST', '/auth/register', {
            'student_no': 'T010BQUIZ', 'name': 'missing', 'password': self.password}, 201)
        self.login(missing, 'T010BQUIZ')
        missing_id = missing.get('/api/v1/auth/session').json['data']['user']['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members', {'user_id': missing_id, 'member_role': 'student'}, 201)
        qs = [self.create(knowledge_ids=[1, 2]), self.create(), self.create(knowledge_ids=[2]),
              self.create(type='short', options=[], answer='参考')]
        draft = self.call(self.teacher, 'POST', f'/courses/{self.course_id}/papers', {
            'title': '真实008→010B', 'kind': 'quiz', 'confidential': True,
            'items': [{'question_version_id': q['version_id'], 'points': 10} for q in qs]}, 201).json['data']
        quiz_id = draft['id']
        published = self.call(self.teacher, 'POST', f'/courses/{self.course_id}/quizzes', {
            'paper_id': quiz_id, 'start_at': '2026-10-13T13:00:00.000Z', 'end_at': '2026-10-13T14:00:00.000Z',
            'confidentiality_note': '未公开确认'}, 201).json['data']
        self.assertIsNone(published['review_at'])
        self.assertEqual(self.call(self.student, 'GET', '/notifications').json['total'], 1)
        self.at(13)
        key = str(uuid4())
        answers = [{'question_version_id': q['version_id'], 'value': v}
                   for q, v in zip((qs[0], qs[1], qs[3]), ('A', 'B', '学生回答'), strict=True)]
        first = self.submit(quiz_id, answers, key=key, quiz=True)
        attempt_id = first.json['data']['id']
        self.assertEqual(first.json['data']['status'], 'partial')
        self.submit(quiz_id, [], client=self.outsider, quiz=True)
        self.at(14, 1)
        self.assertEqual(self.submit(quiz_id, answers, key=key, quiz=True).data, first.data)
        stats_path = f'/quizzes/{quiz_id}/statistics'
        stats = self.call(self.teacher, 'GET', stats_path).json['data']
        self.assertEqual([stats[k] for k in ('expected_count', 'submitted_count', 'missing_count')], [3, 2, 1])
        self.assertEqual(stats['objective_correct_rate'], 1 / 6)  # Quiz includes submitted omissions.
        self.assertEqual(stats['questions'][2]['unanswered_count'], 2)
        self.assertEqual(stats['questions'][3]['pending_count'], 1)
        self.assertIsNone(stats['questions'][3]['correct_rate'])
        self.call(self.student, 'GET', stats_path, status=403)
        self.assertNotIn('answer', self.call(self.student, 'GET', f'/papers/{quiz_id}').json['data']['items'][0])
        scores_response = self.query('scores')
        knowledge_response = self.query('knowledge')
        scores = scores_response.json['data']
        knowledge = knowledge_response.json['data']
        own = self.query('knowledge', self.student).json['data']
        m = scores['metrics']
        self.assertEqual([m[k] for k in ('expected_count', 'submitted_count', 'missing_count', 'graded_count', 'partial_count')], [3, 2, 1, 1, 1])
        self.assertEqual(m['mean_percentage'], 0)
        self.assertEqual((knowledge['sample_size'], knowledge['metrics']['correct_count'], knowledge['metrics']['mastery']), (2, 1, 0.5))
        self.assertEqual([(p['answered_count'], p['correct_count']) for p in knowledge['metrics']['items']], [(2, 1), (1, 1)])
        self.assertEqual(own['metrics']['mastery'], 0.5)
        score_csv = self.export(scores['analysis_run_id']).data
        knowledge_csv = self.export(knowledge['analysis_run_id']).data
        self.call(self.teacher, 'PATCH', f'/attempts/{attempt_id}/manual-scores', {'revision': 0, 'items': [
            {'question_version_id': qs[3]['version_id'], 'score': 8, 'comment': '已批'}]})
        review = self.call(self.teacher, 'POST', f'/quizzes/{quiz_id}/review', {}).json['data']
        self.assertIsNotNone(review['review_published_at'])
        self.assertIn('answer', self.call(self.student, 'GET', f'/papers/{quiz_id}').json['data']['items'][0])
        self.assertTrue(self.call(self.student, 'GET', '/users/me/wrong-questions').json['data'][0]['answer_visible'])
        self.call(self.teacher, 'PATCH', f"/questions/{qs[0]['id']}", {'answer': 'B', 'knowledge_ids': [2]})
        self.at(14, 2)
        newer = self.query('scores').json['data']['metrics']
        self.assertEqual([newer[k] for k in ('graded_count', 'partial_count', 'mean_percentage')], [2, 0, 22.5])
        self.assertEqual(self.query('knowledge').json['data']['metrics']['mastery'], 0.5)
        for original in (scores, knowledge):
            restored = self.restore(original['analysis_run_id'])
            self.assertEqual(restored.json['data'], original)
        self.assertEqual(self.export(scores['analysis_run_id']).data, score_csv)
        self.assertEqual(self.export(knowledge['analysis_run_id']).data, knowledge_csv)
        self.assertEqual(self.restore(own['analysis_run_id'], self.student).json['data'], own)
        self.assertEqual(self.submit(quiz_id, answers, key=key, quiz=True).data, first.data)
        after = self.call(self.teacher, 'GET', stats_path).json['data']
        self.assertEqual(after['questions'][3]['pending_count'], 0)
        self.assertEqual(after['questions'][3]['mean_score'], 4)
        self.assertEqual(after['objective_correct_rate'], 1 / 6)
        backup = self.temporary.name + '/quiz-backup.db'
        with closing(connect(self.path)) as db, closing(connect(backup)) as target:
            db.backup(target)
            self.assertEqual(target.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(target.execute('PRAGMA foreign_key_check').fetchall(), [])
        migrate(backup)
        self.app.config['DATABASE_PATH'] = backup
        self.assertEqual(self.restore(scores['analysis_run_id']).json['data'], scores)
        self.assertEqual(self.restore(knowledge['analysis_run_id']).json['data'], knowledge)
        self.assertEqual(self.export(scores['analysis_run_id']).data, score_csv)
        self.assertEqual(self.export(knowledge['analysis_run_id']).data, knowledge_csv)
