"""C05a real 001/005/006/008 HTTP, publication, notifications and deadline tests."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from backend.models import quiz
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
        self.assertNotIn('explanation', detail['items'][0])
        latest = self.call(self.student, 'GET', f"/attempts/{response.json['data']['id']}").json['data']
        self.assertNotIn('answer', latest['answers'][0])
        self.assertNotIn('explanation', latest['answers'][0])
        wrong = self.call(self.student, 'GET', '/users/me/wrong-questions').json['data'][0]
        self.assertFalse(wrong['answer_visible'])
        self.assertNotIn('answer', wrong)
        self.assertNotIn('explanation', wrong)
        for version in (self.q, v2):
            practice = self.student.post(
                f"/api/v1/questions/{self.q['id']}/practice-attempts",
                json={'question_version_id': version['version_id'], 'answer': 'B'},
                headers={'Origin': ORIGIN, 'X-CSRF-Token': self.student.csrf, 'Idempotency-Key': str(uuid4())})
            self.assertEqual((practice.status_code, practice.json['error']['code']),
                             (409, 'PRACTICE_UNAVAILABLE'))
        with closing(connect(self.path)) as db:
            db.execute('DROP TRIGGER question_version_no_update')
            db.execute('UPDATE question_version SET practice_available=1 WHERE question_id=?', (self.q['id'],))
        for version in (self.q, v2):
            practice = self.student.post(
                f"/api/v1/questions/{self.q['id']}/practice-attempts",
                json={'question_version_id': version['version_id'], 'answer': 'B'},
                headers={'Origin': ORIGIN, 'X-CSRF-Token': self.student.csrf, 'Idempotency-Key': str(uuid4())})
            self.assertEqual((practice.status_code, practice.json['error']['code']),
                             (409, 'QUESTION_RESERVED'))
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

    def stats(self, row):
        return self.call(self.teacher, 'GET', f"/quizzes/{row['id']}/statistics").json['data']

    def test_statistics_five_types_omissions_options_pending_and_frozen_population(self):
        other_id = self.outsider.get('/api/v1/auth/session').json['data']['user']['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members',
                  {'user_id': other_id, 'member_role': 'student'}, 201)
        qs = [self.q, self.new_question(type='multiple', answer=['A', 'B']),
              self.new_question(type='boolean', options=[], answer=False),
              self.new_question(type='numeric', options=[], answer=0.2, tolerance=0.1),
              self.new_question(type='short', options=[], answer='参考')]
        row = self.draft(qs)
        self.publish(row)
        self.call(self.teacher, 'PATCH', f"/questions/{self.q['id']}", {'answer': 'B'})
        zero = self.stats(row)
        self.assertEqual((zero['expected_count'], zero['submitted_count'], zero['missing_count']), (2, 0, 2))
        self.assertIsNone(zero['objective_correct_rate'])
        for q in zero['questions']:
            self.assertIsNone(q['correct_rate'])
            self.assertIsNone(q['mean_score'])
            for option in q['options']:
                self.assertEqual(option['selected_count'], 0)
                self.assertIsNone(option['selection_rate'])
        self.at(13)
        values = ['A', ['B', 'A'], False, 0.3, '学生解释']
        first = self.submit(row['id'], [{'question_version_id': q['version_id'], 'value': value}
                                       for q, value in zip(qs, values)], quiz=True).json['data']
        one = self.stats(row)
        self.assertEqual(sum(o['selection_rate'] for o in one['questions'][1]['options']), 2)
        self.assertEqual(one['objective_correct_rate'], 1)
        self.submit(row['id'], [], client=self.outsider, quiz=True)
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{other_id}', status=204)
        stats = self.stats(row)
        self.assertEqual((stats['expected_count'], stats['submitted_count'], stats['missing_count']), (2, 2, 0))
        self.assertEqual(stats['objective_correct_rate'], 0.5)
        self.assertEqual([q['question_version_id'] for q in stats['questions']], [q['version_id'] for q in qs])
        for q in stats['questions'][:4]:
            self.assertEqual((q['submitted_count'], q['answered_count'], q['unanswered_count'],
                              q['graded_count'], q['pending_count'], q['correct_count'], q['correct_rate'],
                              q['mean_score']), (2, 1, 1, 2, 0, 1, 0.5, 5))
        short = stats['questions'][-1]
        self.assertEqual((short['graded_count'], short['pending_count'], short['mean_score']), (1, 1, 0))
        self.assertIsNone(short['correct_count'])
        self.assertIsNone(short['correct_rate'])
        self.assertEqual([o['key'] for o in stats['questions'][0]['options']], ['A', 'B'])
        self.assertEqual([o['selected_count'] for o in stats['questions'][0]['options']], [1, 0])
        self.assertTrue(all(not q['options'] for q in stats['questions'][2:]))
        self.call(self.teacher, 'PATCH', f"/attempts/{first['id']}/manual-scores",
                  {'revision': 0, 'items': [{'question_version_id': qs[-1]['version_id'], 'score': 7.01, 'comment': ''}]})
        short = self.stats(row)['questions'][-1]
        self.assertEqual((short['graded_count'], short['pending_count'], short['mean_score']), (2, 0, 3.505))
        self.assertNotIn('student_id', str(stats))

    def test_statistics_only_short_no_objective_denominator_and_empty_roster(self):
        short = self.new_question(type='short', options=[], answer='参考')
        row = self.draft([short])
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{self.student_id}', status=204)
        self.publish(row)
        stats = self.stats(row)
        self.assertEqual((stats['expected_count'], stats['missing_count']), (0, 0))
        self.assertIsNone(stats['objective_correct_rate'])
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members',
                  {'user_id': self.student_id, 'member_role': 'student'}, 201)
        self.assertEqual(self.stats(row)['expected_count'], 0)
        self.submit(row['id'], [], quiz=True, status=404)

    def test_review_exact_end_durable_repeat_and_all_answer_entries_release(self):
        v2 = self.call(self.teacher, 'PATCH', f"/questions/{self.q['id']}", {'stem': '新版'}).json['data']
        row = self.draft()
        path = f"/quizzes/{row['id']}/review"
        self.call(self.teacher, 'POST', path, {}, 409)
        self.publish(row)
        self.at(13)
        key = str(uuid4())
        answers = [{'question_version_id': self.q['version_id'], 'value': 'B'}]
        first = self.submit(row['id'], answers, key=key, quiz=True)
        self.call(self.teacher, 'POST', path, {}, 409)
        self.call(self.teacher, 'PATCH', f"/questions/{self.q['id']}", {'practice_available': True}, 409)
        self.at(14)
        self.assertNotIn('answer', self.call(self.student, 'GET', f"/papers/{row['id']}").json['data']['items'][0])
        reviewed = self.call(self.teacher, 'POST', path, {}).json['data']['review_published_at']
        self.assertEqual(reviewed, '2026-10-13T14:00:00.000Z')
        self.at(15)
        self.assertEqual(self.call(self.teacher, 'POST', path).json['data']['review_published_at'], reviewed)
        self.assertEqual(self.submit(row['id'], answers, key=key, quiz=True).data, first.data)
        self.assertEqual(self.call(self.student, 'GET', f"/papers/{row['id']}").json['data']['items'][0]['answer'], 'A')
        latest = self.call(self.student, 'GET', f"/attempts/{first.json['data']['id']}").json['data']
        self.assertEqual(latest['answers'][0]['answer'], 'A')
        wrong = self.call(self.student, 'GET', '/users/me/wrong-questions').json['data'][0]
        self.assertTrue(wrong['answer_visible'])
        self.assertEqual(wrong['answer'], 'A')
        self.call(self.teacher, 'PATCH', f"/questions/{self.q['id']}", {'practice_available': True})
        self.publish(self.draft([v2], confidential=False))
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit_event WHERE action='quiz.review'").fetchone()[0], 1)
            restored = self.path.with_name('review-backup.db')
            with closing(connect(restored)) as target:
                db.backup(target)
                self.assertEqual(target.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(target.execute('PRAGMA foreign_key_check').fetchall(), [])
        original = self.app.config['DATABASE_PATH']
        self.app.config['DATABASE_PATH'] = str(restored)
        try:
            self.assertEqual(self.call(self.teacher, 'POST', path, {}).json['data']['review_published_at'], reviewed)
            self.assertEqual(self.call(self.student, 'GET', f"/attempts/{first.json['data']['id']}").json['data']['answers'][0]['answer'], 'A')
        finally:
            self.app.config['DATABASE_PATH'] = original

    def test_review_permissions_strict_payload_and_ordinary_schedule_retained(self):
        row = self.draft()
        self.publish(row)
        for endpoint, method in (('statistics', 'GET'), ('review', 'POST')):
            path = f"/quizzes/{row['id']}/{endpoint}"
            self.call(self.student, method, path, {} if method == 'POST' else None, 403)
            self.call(self.outsider, method, path, {} if method == 'POST' else None, 404)
            self.call(self.admin, method, path, {} if method == 'POST' else None, 404)
            self.call(self.app.test_client(), method, path, {} if method == 'POST' else None, 401)
            self.call(self.teacher, method, path+'?x=1', {} if method == 'POST' else None, 400)
            self.call(self.teacher, method, f'/quizzes/999/{endpoint}', {} if method == 'POST' else None, 404)
        path = f"/quizzes/{row['id']}/review"
        self.at(14)
        for headers in ({}, {'Origin': ORIGIN}, {'X-CSRF-Token': self.teacher.csrf},
                        {'Origin': 'https://foreign.example', 'X-CSRF-Token': self.teacher.csrf}):
            self.assertEqual(self.teacher.post('/api/v1'+path, json={}, headers=headers).status_code, 403)
        for body in ([], {'review_at': END}, {'confirmed': True}):
            self.call(self.teacher, 'POST', path, body, 400)
        other = self.draft([self.new_question()], kind='homework')
        self.call(self.teacher, 'GET', f"/quizzes/{other['id']}/statistics", status=409)
        self.call(self.teacher, 'POST', f"/quizzes/{other['id']}/review", {}, 409)
        ordinary = self.draft([self.new_question()])
        scheduled = '2026-10-13T16:00:00.000Z'
        self.call(self.teacher, 'POST', f"/papers/{ordinary['id']}/publish",
                  {'start_at': START, 'end_at': END, 'review_at': scheduled, 'confidentiality_note': '未公开'})
        self.at(14)
        self.assertEqual(self.call(self.teacher, 'POST', f"/quizzes/{ordinary['id']}/review", {}).json['data']['review_published_at'], scheduled)
        self.assertNotIn('answer', self.call(self.student, 'GET', f"/papers/{ordinary['id']}").json['data']['items'][0])
        self.at(16)
        self.assertEqual(self.call(self.teacher, 'GET', f"/papers/{ordinary['id']}").json['data']['review_at'], scheduled)
        self.assertEqual(self.call(self.student, 'GET', f"/papers/{ordinary['id']}").json['data']['items'][0]['answer'], 'A')
        self.call(self.teacher, 'POST', '/auth/logout', status=204)
        self.call(self.teacher, 'GET', f"/quizzes/{row['id']}/statistics", status=401)

    def test_review_failure_rolls_back_and_parallel_retries_audit_once(self):
        row = self.draft()
        self.publish(row)
        self.at(14)
        path = f"/quizzes/{row['id']}/review"
        with closing(connect(self.path)) as db:
            db.executescript("CREATE TRIGGER fail_review BEFORE INSERT ON audit_event WHEN NEW.action='quiz.review' "
                             "BEGIN SELECT RAISE(ABORT,'test fault'); END;")
        self.call(self.teacher, 'POST', path, {}, 409)
        with closing(connect(self.path)) as db:
            self.assertIsNone(db.execute('SELECT review_at FROM paper WHERE id=?', (row['id'],)).fetchone()[0])
            db.execute('DROP TRIGGER fail_review')
        def operation(_index):
            client = self.app.test_client()
            client.set_cookie('cpu_session', self.teacher.get_cookie('cpu_session').value)
            response = client.post('/api/v1'+path, json={}, headers={'Origin': ORIGIN, 'X-CSRF-Token': self.teacher.csrf})
            return response.status_code, response.json['data']['review_published_at']
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(operation, (1, 2)))
        self.assertEqual(results, [(200, '2026-10-13T14:00:00.000Z')] * 2)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit_event WHERE action='quiz.review'").fetchone()[0], 1)

    def test_statistics_read_snapshot_survives_concurrent_manual_score(self):
        short = self.new_question(type='short', options=[], answer='参考')
        row = self.draft([short])
        self.publish(row)
        self.at(13)
        first = self.submit(row['id'], [{'question_version_id': short['version_id'], 'value': '作答'}], quiz=True).json['data']
        with closing(connect(self.path)) as db:
            db.execute('PRAGMA journal_mode=WAL')
        original = quiz.statistics
        def during_read(db, paper, at):
            # A real second request in its own thread has an independent Flask g/connection.
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(self.call, self.teacher, 'PATCH', f"/attempts/{first['id']}/manual-scores",
                            {'revision': 0, 'items': [{'question_version_id': short['version_id'], 'score': 8, 'comment': ''}]}).result()
            return original(db, paper, at)
        with patch('backend.models.quiz.statistics', side_effect=during_read):
            old = self.stats(row)
        self.assertEqual((old['questions'][0]['pending_count'], old['questions'][0]['mean_score']), (1, None))
        self.assertIsNone(old['objective_correct_rate'])
        current = self.stats(row)
        self.assertEqual((current['questions'][0]['pending_count'], current['questions'][0]['mean_score']), (0, 8))

    def test_quiz_publication_and_practice_opening_share_identity_lock(self):
        row = self.draft()
        def operation(index):
            client = self.app.test_client()
            client.set_cookie('cpu_session', self.teacher.get_cookie('cpu_session').value)
            headers = {'Origin': ORIGIN, 'X-CSRF-Token': self.teacher.csrf}
            if index == 0:
                return client.post('/api/v1'+self.quizzes, json={'paper_id': row['id'], 'start_at': START,
                                   'end_at': END, 'confidentiality_note': '未公开'}, headers=headers).status_code
            return client.patch(f"/api/v1/questions/{self.q['id']}", json={'practice_available': True},
                                headers=headers).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(operation, (0, 1)))
        self.assertIn(results, ([201, 409], [409, 200]))
        with closing(connect(self.path)) as db:
            published = db.execute('SELECT status FROM paper WHERE id=?', (row['id'],)).fetchone()[0] == 'published'
            public = db.execute('SELECT max(practice_available) FROM question_version WHERE question_id=?',
                                (self.q['id'],)).fetchone()[0]
            self.assertFalse(published and public)

    def test_statistics_mean_does_not_overflow_for_valid_large_scores(self):
        other_id = self.outsider.get('/api/v1/auth/session').json['data']['user']['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members',
                  {'user_id': other_id, 'member_role': 'student'}, 201)
        points = 92233720368547758
        row = self.draft(items=[{'question_version_id': self.q['version_id'], 'points': points}])
        self.publish(row)
        self.at(13)
        for client in (self.student, self.outsider):
            self.submit(row['id'], [{'question_version_id': self.q['version_id'], 'value': 'A'}], client=client, quiz=True)
        stats = self.stats(row)
        self.assertEqual(stats['objective_correct_rate'], 1)
        self.assertEqual(stats['questions'][0]['mean_score'], float(points))
