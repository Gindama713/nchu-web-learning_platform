"""C11: algorithm fixtures and real 001/005/006/008 handlers/SQLite, separately named."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from backend.models import recommendation as model
from backend.shared.api import stamp
from backend.shared.db import connect, migrate
from tests import test_attempts, test_practices


def fixture(rows):
    """Algorithm-only counts, never represented as real learning events."""
    snapshot = {'knowledge': [], 'foundations': [], 'progress': [], 'samples': [], 'entries': {},
                'start': '2026-09-15T12:00:00.000Z', 'source_until': '2026-10-13T12:00:00.000Z',
                'subject_student_id': 1}
    # Metrics is substituted only in the algorithm component tests below.
    for kid, n, c, done, foundational in rows:
        snapshot['knowledge'].append({'id': kid, 'title': str(kid)})
        snapshot['foundations'].append({'id': kid, 'is_foundational': foundational})
        snapshot['progress'].append({'knowledge_id': kid, 'completed': done})
    metrics = {'items': [{'knowledge_id': k, 'answered_count': n, 'correct_count': c,
                          'mastery': c / n if n else None} for k, n, c, _, _ in rows]}
    return snapshot, metrics


class RecommendationAlgorithmTest(unittest.TestCase):
    def calc(self, rows, limit=20):
        snapshot, metrics = fixture(rows)
        with patch.object(model.knowledge_analysis, 'metrics', return_value=metrics):
            return model.calculate(snapshot, limit)

    def test_cold_start_flags_completed_and_empty_priority(self):
        data = self.calc([(3, 0, 0, False, True), (1, 0, 0, False, True), (2, 0, 0, True, True),
                          (4, 0, 0, False, False)])
        self.assertEqual(data['reason'], 'cold_start')
        self.assertEqual([r['knowledge_id'] for r in data['items']], [1, 3])
        self.assertTrue(all((r['score'], r['mastery'], r['reason']) == (1, None, 'foundational') for r in data['items']))
        for rows, reason in (([], 'no_published_knowledge'), ([(1, 0, 0, False, False)], 'no_foundational_candidates'),
                             ([(1, 0, 0, True, True)], 'no_foundational_candidates')):
            value = self.calc(rows)
            self.assertEqual((value['items'], value['reason'], value['algorithm_version']), ([], reason, model.VERSION))
            self.assertIn('source_until', value)

    def test_formula_reason_and_completed_mastery_combinations(self):
        data = self.calc([(1, 0, 0, False, False), (2, 1, 0, False, False), (3, 4, 4, True, False),
                          (4, 5, 4, True, False), (5, 5, 4, False, False), (6, 5, 3, True, False),
                          (7, 5, 5, True, False), (8, 0, 0, True, False)])
        by_id = {r['knowledge_id']: r for r in data['items']}
        self.assertEqual(set(by_id), {1, 2, 3, 5, 6, 8})
        for kid, score, reason in ((1, .6, 'insufficient_sample'), (2, 1, 'insufficient_sample'),
                                   (3, 0, 'insufficient_sample'), (5, .36, 'incomplete'),
                                   (6, .32, 'weakness'), (8, .4, 'insufficient_sample')):
            self.assertEqual((by_id[kid]['score'], by_id[kid]['reason']), (score, reason))
        self.assertEqual(self.calc([(1, 5, 4, True, False)])['reason'], 'all_mastered')

    def test_raw_score_before_rounding_tie_id_and_limit(self):
        # Both display .600000; higher raw score (ID 2) must still win.
        data = self.calc([(1, 20000001, 10000001, False, False), (2, 20000001, 10000000, False, False)], 1)
        self.assertEqual((data['items'][0]['knowledge_id'], data['items'][0]['score']), (2, .6))
        tie = self.calc([(9, 5, 2, False, False), (2, 10, 4, False, False)], 1)
        self.assertEqual(tie['items'][0]['knowledge_id'], 2)


class RecommendationApiTest(test_attempts.AttemptApiBase):
    create_question = test_attempts.KnowledgeFixtureAttemptTest.create_question
    make_paper = test_attempts.KnowledgeFixtureAttemptTest.make_paper
    at = test_attempts.KnowledgeFixtureAttemptTest.at
    answer = test_attempts.KnowledgeFixtureAttemptTest.answer
    practice = test_practices.KnowledgeFixturePracticeTest.practice

    def setUp(self):
        super().setUp()
        self.knowledge_fixture()  # Actual merged 005 handlers, no synthetic knowledge table.
        self.rec = f'/courses/{self.course_id}/recommendations'

    def query(self, suffix='', client=None, status=200):
        response = self.call(client or self.student, 'GET', self.rec + suffix, status=status)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return response

    def point(self, kid, **values):
        return self.call(self.teacher, 'PATCH', f'/knowledge-points/{kid}', values)

    def progress(self, kid, completed=True):
        return self.call(self.student, 'PUT', f'/knowledge-points/{kid}/progress', {'completed': completed})

    def advance(self):
        self.app.config['TEST_NOW'] += timedelta(milliseconds=1)

    def test_real_cold_foundations_progress_unpublish_empty(self):
        self.assertEqual(self.query().json['data']['reason'], 'no_foundational_candidates')
        self.point(2, is_foundational=True)
        self.point(1, is_foundational=True)
        self.assertEqual([r['knowledge_id'] for r in self.query().json['data']['items']], [1, 2])
        self.progress(1)
        self.assertEqual([r['knowledge_id'] for r in self.query().json['data']['items']], [2])
        self.progress(2)
        self.assertEqual(self.query().json['data']['reason'], 'no_foundational_candidates')
        self.point(1, published=False)
        self.point(2, published=False)
        self.assertEqual(self.query().json['data']['reason'], 'no_published_knowledge')
        self.point(2, published=True)
        self.assertEqual(self.query().json['data']['items'], [])  # Preserved completion.

    def test_real_practice_multitag_fixed_version_replay_blank_and_own_identity(self):
        q = self.create_question(practice_available=True, knowledge_ids=[1, 2])
        key = str(uuid4())
        self.practice(q, 'B', key=key)
        self.practice(q, 'B', key=key)
        self.practice(q, None)
        self.call(self.teacher, 'PATCH', f"/questions/{q['id']}", {'knowledge_ids': [2], 'answer': 'B'})
        other_id = self.outsider.get('/api/v1/auth/session').json['data']['user']['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members',
                  {'user_id': other_id, 'member_role': 'student'}, 201)
        self.practice(q, 'A', client=self.outsider)
        self.advance()
        data = self.query().json['data']
        self.assertEqual(data['reason'], 'ok')
        self.assertEqual([(r['sample_size'], r['mastery'], r['score']) for r in data['items']], [(1, 0, 1)] * 2)
        self.assertEqual(data['items'][0]['question_version_id'], None)  # Latest tags removed point 1.
        self.assertNotIn('answer', str(data))
        for suffix in ('?user_id=1', '?student_id=1', '?source_until=2026-10-14T00:00:00Z'):
            self.query(suffix, status=400)

    def test_real_n5_mastery_boundary_filter_and_uncompleted_mastered(self):
        q = self.create_question(practice_available=True, knowledge_ids=[1, 2])
        for value in ['B', 'A', 'A', 'A']:
            self.practice(q, value)
        self.progress(1)
        self.advance()
        self.assertEqual(self.query().json['data']['items'][-1]['sample_size'], 4)
        self.practice(q, 'A')
        self.advance()
        data = self.query().json['data']
        self.assertEqual([(r['knowledge_id'], r['mastery'], r['reason'], r['score']) for r in data['items']],
                         [(2, .8, 'incomplete', .36)])
        self.progress(2)
        self.assertEqual(self.query().json['data']['reason'], 'all_mastered')
        self.practice(q, 'B')
        self.advance()
        self.assertEqual([r['reason'] for r in self.query().json['data']['items']], ['weakness', 'weakness'])

    def test_real_28day_half_open_boundaries(self):
        q = self.create_question(practice_available=True)
        cutoff = datetime(2026, 10, 13, 12, tzinfo=UTC)
        start = cutoff - timedelta(days=28)
        for at, value in ((start - timedelta(milliseconds=1), 'A'), (start, 'B'),
                          (cutoff - timedelta(milliseconds=1), 'A'), (cutoff, 'B'),
                          (cutoff + timedelta(milliseconds=1), 'B')):
            self.app.config['TEST_NOW'] = at
            self.login(self.student, 'T006STUD1')
            self.practice(q, value)
        self.app.config['TEST_NOW'] = cutoff
        data = self.query().json['data']
        row = next(r for r in data['items'] if r['knowledge_id'] == 1)
        self.assertEqual((row['sample_size'], row['mastery'], data['source_until']), (2, .5, stamp(cutoff)))

    def test_real_008_partial_objective_omission_short_and_manual_grade(self):
        qs = [self.create_question(knowledge_ids=[1, 2]), self.create_question(),
              self.create_question(type='short', options=[], answer='参考')]
        draft = self.call(self.teacher, 'POST', f'/courses/{self.course_id}/papers', {
            'title': 'C11真实随堂测', 'kind': 'quiz', 'confidential': True,
            'items': [{'question_version_id': q['version_id'], 'points': 10} for q in qs]}, 201).json['data']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/quizzes', {
            'paper_id': draft['id'], 'start_at': '2026-10-13T13:00:00.000Z',
            'end_at': '2026-10-13T14:00:00.000Z', 'confidentiality_note': '未公开'}, 201)
        self.at(13)
        key = str(uuid4())
        answers = [self.answer(qs[0], 'B'), self.answer(qs[2], '学生文本')]
        attempt = self.submit(draft['id'], answers, key=key, quiz=True).json['data']
        self.submit(draft['id'], answers, key=key, quiz=True)
        public = self.create_question(practice_available=True)
        self.practice(public, 'A')  # practice id=1 and answer id=1 are distinct.
        self.advance()
        before = self.query().json['data']['items']
        self.assertEqual([(r['knowledge_id'], r['sample_size'], r['mastery']) for r in before], [(2, 1, 0), (1, 2, .5)])
        self.call(self.teacher, 'PATCH', f"/attempts/{attempt['id']}/manual-scores", {
            'revision': 0, 'items': [{'question_version_id': qs[2]['version_id'], 'score': 8, 'comment': ''}]})
        self.assertEqual(self.query().json['data']['items'], before)
        self.assertNotIn('answer', self.call(self.student, 'GET', f"/papers/{draft['id']}").json['data']['items'][0])

    def test_latest_eligible_version_minimum_id_private_short_archived_and_no_answer(self):
        first = self.create_question(practice_available=True)
        second = self.create_question(practice_available=True)
        newer = self.call(self.teacher, 'PATCH', f"/questions/{first['id']}", {'stem': '新版本'}).json['data']
        self.point(1, is_foundational=True)
        self.assertEqual(self.query().json['data']['items'][0]['question_version_id'], second['version_id'])
        self.call(self.teacher, 'PATCH', f"/questions/{second['id']}", {'practice_available': False})
        self.assertEqual(self.query().json['data']['items'][0]['question_version_id'], newer['version_id'])
        self.call(self.teacher, 'PATCH', f"/questions/{first['id']}",
                  {'type': 'short', 'options': [], 'answer': '参考', 'practice_available': False})
        self.assertIsNone(self.query().json['data']['items'][0]['question_version_id'])
        q = self.create_question(practice_available=True)
        with closing(connect(self.path)) as db:
            db.execute('UPDATE question SET archived=1 WHERE id=?', (q['id'],))  # Legacy archival fixture.
        self.assertIsNone(self.query().json['data']['items'][0]['question_version_id'])

    def test_identity_level_protection_excludes_entry_and_failure_does_not_block_submit(self):
        private = self.create_question()
        paper_id = self.make_paper([private])
        public = self.create_question(practice_available=True)
        self.point(1, is_foundational=True)
        # Explicit anomalous legacy identity fixture; ordinary 006 APIs forbid this transition.
        with closing(connect(self.path)) as db:
            db.execute('DROP TRIGGER question_version_no_update')
            db.execute('UPDATE question_version SET practice_available=1 WHERE id=?', (private['version_id'],))
        self.assertEqual(self.query().json['data']['items'][0]['question_version_id'], public['version_id'])
        with patch.object(model, 'calculate', side_effect=RuntimeError('injected C11 failure')):
            self.query(status=503)
            self.practice(public, 'B')
            self.at(13)
            self.submit(paper_id, [self.answer(private, 'A')])
        self.advance()
        self.assertEqual(self.query().json['data']['reason'], 'ok')

    def test_strict_limit_defaults_20_and_permissions(self):
        chapter = self.call(self.teacher, 'GET', f'/courses/{self.course_id}/chapters').json['data'][0]['id']
        for i in range(23):
            self.call(self.teacher, 'POST', f'/chapters/{chapter}/knowledge-points', {
                'title': str(i), 'content': '正文', 'published': True, 'is_foundational': True}, 201)
        self.assertEqual(len(self.query().json['data']['items']), 5)
        self.assertEqual(len(self.query('?limit=20').json['data']['items']), 20)
        self.assertEqual(len(self.query('?limit=1').json['data']['items']), 1)
        for suffix in ('?limit=0', '?limit=21', '?limit=-1', '?limit=1.0', '?limit=true', '?limit=',
                       '?limit=01', '?limit=1&limit=2', '?limit=999999999999999999999999', '?x=1'):
            self.query(suffix, status=400)
        for client, status in ((self.teacher, 403), (self.admin, 403), (self.outsider, 404), (self.app.test_client(), 401)):
            self.query(client=client, status=status)
        other = self.call(self.admin, 'POST', '/courses', {'title': '他课', 'teacher_id': self.teacher_id}, 201).json['data']['id']
        self.call(self.student, 'GET', f'/courses/{other}/recommendations', status=404)
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{self.student_id}', status=204)
        self.query(status=404)
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members',
                  {'user_id': self.student_id, 'member_role': 'student'}, 201)
        self.query()
        self.call(self.admin, 'PATCH', f'/users/{self.student_id}', {'active': False})
        self.query(status=401)

    def test_concurrent_unpublish_progress_entry_and_revoke_are_rechecked(self):
        self.point(1, is_foundational=True)
        original = model.calculate
        operations = [lambda: self.point(1, published=False), lambda: self.progress(1),
                      lambda: self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{self.student_id}', status=204)]
        for operation in operations:
            self.point(1, published=True)
            self.progress(1, False)
            once = [False]

            def calculate(*args, once=once, operation=operation):
                if not once[0]:
                    once[0] = True
                    with ThreadPoolExecutor(1) as pool:
                        pool.submit(operation).result()
                return original(*args)

            with patch.object(model, 'calculate', calculate):
                response = self.query(status=404 if operation is operations[-1] else 200)
            if response.status_code == 200:
                self.assertEqual(response.json['data']['items'], [])

    def test_current_entry_change_deactivation_continuous_change_dependency_and_backup(self):
        self.point(1, is_foundational=True)
        q = self.create_question(practice_available=True)
        original = model.calculate
        once = [False]

        def close_entry(*args):
            if not once[0]:
                once[0] = True
                with ThreadPoolExecutor(1) as pool:
                    pool.submit(self.call, self.teacher, 'PATCH', f"/questions/{q['id']}", {'practice_available': False}).result()
            return original(*args)

        with patch.object(model, 'calculate', close_entry):
            self.assertIsNone(self.query().json['data']['items'][0]['question_version_id'])

        def change(*args):
            with ThreadPoolExecutor(1) as pool:
                pool.submit(self.point, 1, title=str(uuid4())).result()
            return original(*args)

        with patch.object(model, 'calculate', change):
            self.query(status=503)
        saved = self.query().json['data']
        backup = self.path.with_name('recommend-backup.db')
        with closing(connect(self.path)) as db, closing(connect(backup)) as target:
            db.backup(target)
            self.assertEqual(target.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        migrate(backup)
        self.app.config['DATABASE_PATH'] = str(backup)
        self.assertEqual(self.query().json['data'], saved)
        with closing(connect(backup)) as db:
            db.execute('ALTER TABLE practice_attempt RENAME TO unavailable_practice')
        self.query(status=503)
        self.app.config['DATABASE_PATH'] = str(self.path)
        def deactivate(*args):
            with ThreadPoolExecutor(1) as pool:
                pool.submit(self.call, self.admin, 'PATCH', f'/users/{self.student_id}', {'active': False}).result()
            return original(*args)

        with patch.object(model, 'calculate', deactivate):
            self.query(status=401)
