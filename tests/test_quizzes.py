"""C05a real 001/005/006/008 HTTP, publication, notifications and deadline tests."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from uuid import uuid4

from backend.shared.db import connect
from tests.test_attempts import AttemptApiBase
from tests.test_papers import END, START
from tests.test_question_validation import question
from tests.test_questions import ORIGIN


class QuizApiTest(AttemptApiBase):
    def setUp(self):
        super().setUp()
        # This helper now uses the actual chapter and knowledge APIs, not SQL doubles.
        self.knowledge_fixture()
        self.quizzes = f'/courses/{self.course_id}/quizzes'
        self.q = self.new_question()

    def new_question(self, **values):
        return self.call(self.teacher, 'POST', self.url, question(**values), 201).json['data']

    def draft(self, questions=None, **values):
        return self.call(self.teacher, 'POST', f'/courses/{self.course_id}/papers',
                         {'title': 'CPU随堂测', 'kind': 'quiz', 'confidential': True,
                          'items': [{'question_version_id': q['version_id'], 'points': 10}
                                    for q in questions or [self.q]], **values}, 201).json['data']

    def publish(self, row, status=201, **values):
        return self.call(self.teacher, 'POST', self.quizzes,
                         {'paper_id': row['id'], 'start_at': START, 'end_at': END,
                          'confidentiality_note': '确认未公开且非简单复制', **values}, status)

    def at(self, hour):
        self.app.config['TEST_NOW'] = datetime(2026, 10, 13, hour, tzinfo=UTC)
        self.login(self.teacher, 'T006TEACH')
        self.login(self.student, 'T006STUD1')
        self.login(self.outsider, 'T006STUD2')

    def test_publication_same_paper_null_review_and_frozen_notification_recipients(self):
        row = self.draft()
        response = self.publish(row, start_at='2026-10-13T21:00:00+08:00')
        data = response.json['data']
        self.assertEqual((data['id'], data['paper_id'], data['status'], data['review_at']),
                         (row['id'], row['id'], 'upcoming', None))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.publish(row, 409)
        metadata = self.call(self.student, 'GET', self.quizzes).json['data'][0]
        self.assertEqual((metadata['status'], metadata['window_state']), ('published', 'upcoming'))
        self.assertNotIn('items', metadata)
        self.assertNotIn('items', self.call(self.student, 'GET', f"/papers/{row['id']}").json['data'])
        notifications = self.call(self.student, 'GET', '/notifications').json['data']
        self.assertEqual(len(notifications), 1)
        self.assertEqual((notifications[0]['target_type'], notifications[0]['target_id']), ('quiz', row['id']))
        self.assertEqual(self.call(self.teacher, 'GET', '/notifications').json['total'], 0)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT event_key FROM notification').fetchone()[0], f"quiz.published:{row['id']}")
            self.assertEqual(db.execute('SELECT count(*) FROM paper').fetchone()[0], 1)
        late_id = self.outsider.get('/api/v1/auth/session').json['data']['user']['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members',
                  {'user_id': late_id, 'member_role': 'student'}, 201)
        self.assertEqual(self.call(self.outsider, 'GET', self.quizzes).json['total'], 0)
        self.assertEqual(self.call(self.outsider, 'GET', '/notifications').json['total'], 0)
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{self.student_id}', status=204)
        self.call(self.student, 'GET', self.quizzes, status=404)
        self.submit(row['id'], [], quiz=True, status=404)
        self.assertEqual(self.call(self.teacher, 'GET', self.quizzes).json['data'][0]['participant_count'], 1)

    def test_exact_start_end_shared_replay_and_manual_scores_do_not_rewrite_snapshot(self):
        short = self.new_question(type='short', options=[], answer='参考答案')
        row = self.draft([self.q, short])
        self.publish(row)
        key = str(uuid4())
        answers = [{'question_version_id': self.q['version_id'], 'value': 'A'},
                   {'question_version_id': short['version_id'], 'value': '学生文本'}]
        self.submit(row['id'], answers, key=key, quiz=True, status=409)
        self.at(13)
        first = self.submit(row['id'], answers, key=key, quiz=True)
        self.assertEqual(first.json['data']['status'], 'partial')
        self.assertIsNone(first.json['data']['score'])
        self.assertEqual(self.submit(row['id'], answers, key=key).data, first.data)
        self.submit(row['id'], [], quiz=True, status=409)
        self.at(14)
        self.submit(row['id'], [], client=self.outsider, quiz=True, status=404)
        self.assertEqual(self.submit(row['id'], answers, key=key).data, first.data)
        self.submit(row['id'], [], key=key, quiz=True, status=409)
        self.submit(row['id'], [], quiz=True, status=409)
        attempt_id = first.json['data']['id']
        self.call(self.teacher, 'PATCH', f'/attempts/{attempt_id}/manual-scores',
                  {'revision': 0, 'items': [{'question_version_id': short['version_id'], 'score': 8, 'comment': '已批阅'}]})
        latest = self.call(self.student, 'GET', f'/attempts/{attempt_id}').json['data']
        self.assertEqual((latest['score'], latest['revision']), (18, 1))
        self.assertEqual(self.submit(row['id'], answers, key=key, quiz=True).data, first.data)
        self.assertEqual(self.call(self.student, 'GET', f'/courses/{self.course_id}/attempts').json['total'], 1)
        for answer in latest['answers']:
            self.assertNotIn('answer', answer)
            self.assertNotIn('explanation', answer)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM attempt').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM idempotency_record').fetchone()[0], 1)

    def test_new_submission_at_end_is_rejected_without_consuming_key(self):
        row = self.draft()
        self.publish(row)
        self.at(14)
        self.submit(row['id'], [], quiz=True, status=409)
        with closing(connect(self.path)) as db:
            for table in ('attempt', 'answer', 'idempotency_record'):
                self.assertEqual(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0], 0)

    def test_closed_unreviewed_quiz_protects_all_versions_and_wrong_question_entry(self):
        v2 = self.call(self.teacher, 'PATCH', f"/questions/{self.q['id']}", {'stem': '新版PC'}).json['data']
        row = self.draft()
        self.publish(row)
        self.at(13)
        response = self.submit(row['id'], [{'question_version_id': self.q['version_id'], 'value': 'B'}], quiz=True)
        self.at(15)
        detail = self.call(self.student, 'GET', f"/papers/{row['id']}").json['data']
        self.assertEqual(detail['window_state'], 'closed')
        self.assertIsNone(detail['review_at'])
        self.assertNotIn('answer', detail['items'][0])
        self.assertNotIn('answer', self.call(self.student, 'GET', f"/attempts/{response.json['data']['id']}").json['data']['answers'][0])
        wrong = self.call(self.student, 'GET', '/users/me/wrong-questions').json['data'][0]
        self.assertFalse(wrong['answer_visible'])
        self.assertNotIn('answer', wrong)
        self.call(self.teacher, 'PATCH', f"/questions/{self.q['id']}", {'practice_available': True}, 409)
        other = self.draft([v2], confidential=False)
        self.assertEqual(self.publish(other, 409).json['error']['code'], 'QUESTION_RESERVED')

    def test_strict_fields_permissions_filters_and_cross_course(self):
        row = self.draft()
        self.call(self.student, 'POST', self.quizzes, {'paper_id': row['id']}, 403)
        self.call(self.outsider, 'POST', self.quizzes, {'paper_id': row['id']}, 404)
        self.assertEqual(self.teacher.post('/api/v1'+self.quizzes, json={}).status_code, 403)
        self.call(self.app.test_client(), 'GET', self.quizzes, status=401)
        for values in ({'paper_id': True}, {'paper_id': '1'}, {'review_at': END}, {'end_at': START},
                       {'start_at': '2026-10-13T13:00:00'}, {'start_at': '2026-10-13T13:00:00.000001Z'},
                       {'confidentiality_note': ''}, {'participants': [self.student_id]}):
            self.publish(row, 400, **values)
        self.call(self.teacher, 'POST', self.quizzes, {'start_at': START, 'end_at': END}, 400)
        self.publish(self.draft(kind='homework'), 409)
        other_course = self.call(self.admin, 'POST', '/courses', {'title': 'other', 'teacher_id': self.teacher_id}, 201).json['data']['id']
        self.call(self.teacher, 'POST', f'/courses/{other_course}/quizzes',
                  {'paper_id': row['id'], 'start_at': START, 'end_at': END}, 404)
        for suffix in ('?kind=quiz', '?status=open', '?status=draft&status=published', '?page=0', '?page_size=101', '?x=1'):
            self.call(self.teacher, 'GET', self.quizzes+suffix, status=400)
        self.assertEqual(self.call(self.teacher, 'GET', self.quizzes+'?status=draft&page_size=1').json['total'], 1)
        self.call(self.teacher, 'POST', self.quizzes+'?x=1', {}, 400)

    def test_public_identity_rejected_and_notification_failure_rolls_back_publication(self):
        public = self.new_question(practice_available=True)
        private = self.call(self.teacher, 'PATCH', f"/questions/{public['id']}", {'practice_available': False}).json['data']
        self.assertEqual(self.publish(self.draft([private]), 409).json['error']['code'], 'QUESTION_PUBLIC')
        row = self.draft()
        with closing(connect(self.path)) as db:
            db.executescript("CREATE TRIGGER fail_notification BEFORE INSERT ON notification BEGIN SELECT RAISE(ABORT,'test fault'); END;")
        self.publish(row, 409)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT status FROM paper WHERE id=?', (row['id'],)).fetchone()[0], 'draft')
            self.assertEqual(db.execute('SELECT count(*) FROM paper_participant').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM audit_event WHERE action='paper.publish'").fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM notification').fetchone()[0], 0)
            db.execute('DROP TRIGGER fail_notification')
        self.publish(row)

    def test_concurrent_publication_keeps_one_event_roster_and_notification(self):
        row = self.draft()
        def operation(_index):
            client = self.app.test_client()
            client.set_cookie('cpu_session', self.teacher.get_cookie('cpu_session').value)
            return client.post('/api/v1'+self.quizzes, json={'paper_id': row['id'], 'start_at': START,
                               'end_at': END, 'confidentiality_note': '未公开'},
                               headers={'Origin': ORIGIN, 'X-CSRF-Token': self.teacher.csrf}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(operation, (1, 2))), [201, 409])
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM paper_participant').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM notification').fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM audit_event WHERE action='paper.publish'").fetchone()[0], 1)
