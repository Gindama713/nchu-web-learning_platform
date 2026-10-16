"""R37 actual 001/005/006/008/004 handlers; known 004 failures stay explicit.

Only initial admin/teacher bootstrap comes from QuestionApiBase. Business objects
and membership changes use HTTP. SQL writes below are rollback/failure fixtures.
"""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from unittest import expectedFailure

from backend.shared.db import connect
from tests.test_attempts import AttemptApiBase
from tests.test_papers import END, START
from tests.test_question_validation import question


class PreparationQuizIntegrationTest(AttemptApiBase):
    def setUp(self):
        self.trace, self.snapshots = [], []
        super().setUp()
        self.addCleanup(self.snapshot, 'final')
        self.knowledge_fixture()
        self.q = self.call(self.teacher, 'POST', self.url,
                           question(explanation='R37讲评解析'), 201).json['data']
        self.base = f'/courses/{self.course_id}/preparations'
        self.quiz = self.paper()

    def call(self, client, method, path, data=None, status=200):
        # Save actual responses even when an assertion fails, never credentials.
        from tests.test_questions import ORIGIN
        response = client.open('/api/v1' + path, method=method, json=data,
                               headers={'Origin': ORIGIN, 'X-CSRF-Token': getattr(client, 'csrf', '')})
        if not path.startswith('/auth/'):
            self.trace.append({'method': method, 'path': path, 'request': data,
                               'status': response.status_code, 'response': response.json,
                               'cache_control': response.headers.get('Cache-Control')})
        self.assertEqual(response.status_code, status, response.json)
        return response

    def snapshot(self, label):
        with closing(connect(self.path)) as db:
            queries = {
                'preparations': 'SELECT id,course_id,status,source_id FROM preparation ORDER BY id',
                'links': 'SELECT * FROM preparation_quiz ORDER BY preparation_id,paper_id',
                'papers': 'SELECT id,course_id,kind,status,start_at,end_at,review_at FROM paper ORDER BY id',
                'roster': 'SELECT * FROM paper_participant ORDER BY paper_id,student_id',
                'attempts': 'SELECT id,paper_id,student_id,status,submitted_at FROM attempt ORDER BY id',
                'audit': 'SELECT action,object_id FROM audit_event WHERE action LIKE \'preparation.%\' '
                         'OR action IN (\'paper.publish\',\'quiz.review\') ORDER BY id',
            }
            item = {name: [dict(row) for row in db.execute(sql)] for name, sql in queries.items()}
            item['foreign_key_check'] = [list(row) for row in db.execute('PRAGMA foreign_key_check')]
        self.snapshots.append({'label': label, **item})
        return item

    def paper(self, **values):
        return self.call(self.teacher, 'POST', f'/courses/{self.course_id}/papers', {
            'title': 'R37随堂测', 'kind': 'quiz', 'confidential': True,
            'items': [{'question_version_id': self.q['version_id'], 'points': 10}],
            **values}, 201).json['data']

    def prep(self, **values):
        return self.call(self.teacher, 'POST', self.base, {
            'title': 'R37备课', 'knowledge_ids': [1], 'resource_version_ids': [],
            'question_version_ids': [], 'quiz_ids': [self.quiz['id']], **values}, 201).json['data']

    def publish_quiz(self):
        return self.call(self.teacher, 'POST', f'/courses/{self.course_id}/quizzes', {
            'paper_id': self.quiz['id'], 'start_at': START, 'end_at': END,
            'confidentiality_note': '确认未公开且非简单复制'}, 201).json['data']

    def published_prep(self):
        self.publish_quiz()
        prep = self.prep()
        self.call(self.teacher, 'POST', f"/preparations/{prep['id']}/publish", {})
        return prep

    def at(self, hour):
        self.app.config['TEST_NOW'] = datetime(2026, 10, 13, hour, tzinfo=UTC)
        for client, number in ((self.admin, 'T006ADMIN'), (self.teacher, 'T006TEACH'),
                               (self.student, 'T006STUD1'), (self.outsider, 'T006STUD2')):
            self.login(client, number)

    def assert_no_answers(self, value):
        if isinstance(value, dict):
            self.assertTrue({'answer', 'explanation'}.isdisjoint(value), value)
            for child in value.values():
                self.assert_no_answers(child)
        elif isinstance(value, list):
            for child in value:
                self.assert_no_answers(child)

    def test_same_course_links_and_invalid_create_patch_are_atomic(self):
        prep = self.prep()
        other_course = self.call(self.admin, 'POST', '/courses', {
            'title': 'R37其他课程', 'teacher_id': self.teacher_id}, 201).json['data']['id']
        chapter = self.call(self.teacher, 'POST', f'/courses/{other_course}/chapters',
                            {'title': '其他'}, 201).json['data']['id']
        kid = self.call(self.teacher, 'POST', f'/chapters/{chapter}/knowledge-points', {
            'title': '其他知识', 'content': '正文', 'published': True}, 201).json['data']['id']
        q = self.call(self.teacher, 'POST', f'/courses/{other_course}/questions',
                      question(knowledge_ids=[kid]), 201).json['data']
        foreign = self.call(self.teacher, 'POST', f'/courses/{other_course}/papers', {
            'title': '跨课quiz', 'kind': 'quiz',
            'items': [{'question_version_id': q['version_id'], 'points': 10}]}, 201).json['data']
        homework = self.paper(kind='homework')
        before = self.snapshot('before_invalid_links')
        for ids, status in (([foreign['id']], 404), ([homework['id']], 404),
                            ([self.quiz['id'], self.quiz['id']], 400)):
            with self.subTest(ids=ids):
                payload = {'title': 'invalid', 'knowledge_ids': [], 'resource_version_ids': [],
                           'question_version_ids': [], 'quiz_ids': ids}
                self.call(self.teacher, 'POST', self.base, payload, status)
                self.call(self.teacher, 'PATCH', f"/preparations/{prep['id']}", {'quiz_ids': ids}, status)
        after = self.snapshot('after_invalid_links')
        self.assertEqual(before, after)

    def test_copy_draft_preserves_links_without_copying_or_publishing_quiz(self):
        prep = self.prep()
        copy = self.call(self.teacher, 'POST', f"/preparations/{prep['id']}/copy",
                         {'title': 'R37草稿副本'}, 201).json['data']
        self.assertEqual((copy['status'], copy['source_id'], copy['quiz_ids']),
                         ('draft', prep['id'], [self.quiz['id']]))
        for row in (prep, copy):
            # Barrier works; exact 409 contract is the separate known-failure test.
            self.call(self.teacher, 'POST', f"/preparations/{row['id']}/publish", {}, 404)
        state = self.snapshot('draft_copy_and_blocked_publish')
        self.assertEqual(len(state['papers']), 1)
        self.assertEqual(state['papers'][0]['status'], 'draft')
        self.assertEqual(state['roster'], [])
        self.assertTrue(all(p['status'] == 'draft' for p in state['preparations']))
        self.assertFalse(any(a['action'] == 'preparation.publish' for a in state['audit']))

    def test_published_copy_and_http_and_database_update_freeze(self):
        prep = self.published_prep()
        before = self.snapshot('published')
        copy = self.call(self.teacher, 'POST', f"/preparations/{prep['id']}/copy",
                         {'title': 'R37发布后副本'}, 201).json['data']
        self.assertEqual(copy['quiz_ids'], [self.quiz['id']])
        self.assertEqual(copy['status'], 'draft')
        self.call(self.teacher, 'PATCH', f"/preparations/{prep['id']}", {'quiz_ids': []}, 409)
        with closing(connect(self.path)) as db:
            # Fault fixture only: attempt UPDATE then rollback; no bypassed business creation.
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('UPDATE preparation_quiz SET paper_id=paper_id WHERE preparation_id=?', (prep['id'],))
            db.rollback()
        after = self.snapshot('published_copy_and_refused_mutation')
        self.assertEqual(before['papers'], after['papers'])
        self.assertEqual(before['roster'], after['roster'])
        self.assertEqual(len(after['links']), 2)

    def test_frozen_roster_filters_detail_and_list_before_start(self):
        self.publish_quiz()
        late_id = self.outsider.get('/api/v1/auth/session').json['data']['user']['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members',
                  {'user_id': late_id, 'member_role': 'student'}, 201)
        prep = self.prep()
        self.call(self.teacher, 'POST', f"/preparations/{prep['id']}/publish", {})
        for client, expected in ((self.student, [self.quiz['id']]), (self.outsider, [])):
            for path in (self.base, f"/preparations/{prep['id']}"):
                data = self.call(client, 'GET', path).json['data']
                item = data[0] if isinstance(data, list) else data
                self.assertEqual(item['quiz_ids'], expected)
                self.assertEqual([q['id'] for q in item['quizzes']], expected)
                self.assert_no_answers(item)
                self.assertNotIn('items', str(item))
        self.call(self.outsider, 'GET', f"/papers/{self.quiz['id']}", status=404)
        self.assertNotIn('items', self.call(self.student, 'GET', f"/papers/{self.quiz['id']}").json['data'])
        self.assertEqual(self.call(self.outsider, 'GET', f'/courses/{self.course_id}/quizzes').json['total'], 0)
        self.assertEqual(len(self.snapshot('late_member_not_in_roster')['roster']), 1)

    def test_preparation_entry_respects_deadline_review_and_revocation(self):
        prep = self.published_prep()
        paper_path = f"/papers/{self.quiz['id']}"
        self.at(13)
        attempt = self.submit(self.quiz['id'], [{'question_version_id': self.q['version_id'], 'value': 'B'}], quiz=True)
        attempt_path = f"/attempts/{attempt.json['data']['id']}"
        self.trace.append({'method': 'POST', 'path': f"/quizzes/{self.quiz['id']}/attempts",
                           'status': attempt.status_code, 'response': attempt.json})
        self.call(self.teacher, 'POST', f"/quizzes/{self.quiz['id']}/review", {}, 409)
        self.at(14)
        for path in (paper_path, attempt_path, '/users/me/wrong-questions', f"/preparations/{prep['id']}"):
            self.assert_no_answers(self.call(self.student, 'GET', path).json['data'])
        self.call(self.teacher, 'PATCH', f"/questions/{self.q['id']}", {'practice_available': True}, 409)
        self.assertIsNone(self.snapshot('closed_unreviewed')['papers'][0]['review_at'])
        self.call(self.teacher, 'POST', f"/quizzes/{self.quiz['id']}/review", {})
        self.assertEqual(self.call(self.student, 'GET', paper_path).json['data']['items'][0]['answer'], 'A')
        self.assertEqual(self.call(self.student, 'GET', attempt_path).json['data']['answers'][0]['answer'], 'A')
        self.assertTrue(self.call(self.student, 'GET', '/users/me/wrong-questions').json['data'][0]['answer_visible'])
        self.assert_no_answers(self.call(self.student, 'GET', f"/preparations/{prep['id']}").json['data'])
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{self.student_id}', status=204)
        for path in (self.base, f"/preparations/{prep['id']}", paper_path, attempt_path):
            self.call(self.student, 'GET', path, status=404)
        self.assertEqual(len(self.snapshot('revoked_access_roster_retained')['roster']), 1)

    def test_permissions_and_publication_notification_failure_rollback(self):
        prep = self.prep()
        for client, status in ((self.student, 403), (self.outsider, 404), (self.app.test_client(), 401)):
            for action in ('publish', 'copy'):
                self.call(client, 'POST', f"/preparations/{prep['id']}/{action}", {'title': 'x'} if action == 'copy' else {}, status)
        self.publish_quiz()
        before = self.snapshot('before_injected_notification_failure')
        with closing(connect(self.path)) as db:
            db.executescript("CREATE TRIGGER r37_fail_notification BEFORE INSERT ON notification "
                             "WHEN NEW.target_type='preparation' BEGIN SELECT RAISE(ABORT,'R37 fault'); END;")
        self.call(self.teacher, 'POST', f"/preparations/{prep['id']}/publish", {}, 409)
        self.assertEqual(before, self.snapshot('after_injected_notification_failure'))
        with closing(connect(self.path)) as db:
            db.execute('DROP TRIGGER r37_fail_notification')
        self.call(self.teacher, 'POST', f"/preparations/{prep['id']}/publish", {})

    @expectedFailure
    def test_r37_004_01_unpublished_quiz_requires_contract_409(self):
        """R37-004-01, owner 罗浩铭: actual 404 NOT_FOUND, APIC§3 requires 409."""
        prep = self.prep()
        response = self.call(self.teacher, 'POST', f"/preparations/{prep['id']}/publish", {}, 409)
        self.assertEqual(response.json['error']['code'], 'QUIZ_NOT_PUBLISHED')

    @expectedFailure
    def test_r37_004_02_prestart_metadata_requires_window_state(self):
        """R37-004-02, owner 罗浩铭: APIC§3 metadata omits window_state."""
        prep = self.published_prep()
        item = self.call(self.student, 'GET', f"/preparations/{prep['id']}").json['data']['quizzes'][0]
        self.assertEqual(set(item), {'id', 'title', 'window_state', 'start_at', 'end_at'})
        self.assertEqual(item['window_state'], 'upcoming')
