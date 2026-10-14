"""C03b actual HTTP/SQLite grading; only SPEC-005 knowledge is an explicit fixture."""

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier
from uuid import uuid4

from backend.shared.db import connect, migrate
from tests import test_attempts
from tests.test_questions import ORIGIN


class ManualScoreTest(test_attempts.AttemptApiBase):
    create_question = test_attempts.KnowledgeFixtureAttemptTest.create_question
    make_paper = test_attempts.KnowledgeFixtureAttemptTest.make_paper
    at = test_attempts.KnowledgeFixtureAttemptTest.at
    answer = test_attempts.KnowledgeFixtureAttemptTest.answer

    def setUp(self):
        super().setUp()
        self.knowledge_fixture()
        self.qs = [self.create_question(), *[self.create_question(type='short', options=[], answer='参考') for _ in range(3)]]
        self.paper_id = self.make_paper(self.qs, points=[0.1, 1.01, 2.02, 3.03])
        self.at(13)
        self.key = str(uuid4())
        self.answers = [self.answer(q, value) for q, value in zip(self.qs, ['A', '甲', '乙', None])]
        self.original = self.submit(self.paper_id, self.answers, key=self.key)
        self.id = self.original.json['data']['id']
        self.url = f'/attempts/{self.id}/manual-scores'

    def item(self, index=1, score=0.5, comment='评语'):
        return {'question_version_id': self.qs[index]['version_id'], 'score': score, 'comment': comment}

    def grade(self, items, revision=0, status=200, client=None):
        return self.call(client or self.teacher, 'PATCH', self.url,
                         {'revision': revision, 'items': items}, status).json['data'] if status == 200 else self.call(
                             client or self.teacher, 'PATCH', self.url, {'revision': revision, 'items': items}, status)

    def state(self):
        with closing(connect(self.path)) as db:
            return (dict(db.execute('SELECT * FROM attempt WHERE id=?', (self.id,)).fetchone()),
                    [dict(r) for r in db.execute('SELECT * FROM answer WHERE attempt_id=? ORDER BY id', (self.id,))],
                    [dict(r) for r in db.execute("SELECT * FROM audit_event WHERE action='attempt.manual_scores'")])

    def test_partial_full_correction_exact_sum_and_audit(self):
        partial = self.grade([self.item(score=0)])
        self.assertEqual((partial['revision'], partial['status'], partial['score'], partial['partial_score']), (1, 'partial', None, 0.1))
        self.assertEqual(partial['answers'][1]['grading_status'], 'graded')
        self.assertIsNone(partial['answers'][1]['correct'])
        full = self.grade([self.item(2, 2.02)], revision=1)
        self.assertEqual((full['revision'], full['status'], full['score']), (2, 'graded', 2.12))
        corrected = self.grade([self.item(1, 1.01, '更正'), self.item(2, 0.01, '')], revision=2)
        self.assertEqual((corrected['revision'], corrected['score'], corrected['partial_score']), (3, 1.12, 1.12))
        fact, answers, events = self.state()
        self.assertEqual(fact['score_hundredths'], 112)
        self.assertEqual([a['graded_by'] for a in answers], [None, self.teacher_id, self.teacher_id, None])
        self.assertEqual(len(events), 3)
        self.assertEqual(events[-1]['actor_id'], self.teacher_id)
        before, after = json.loads(events[-1]['before_summary']), json.loads(events[-1]['after_summary'])
        self.assertEqual([v['score_hundredths'] for v in before['items']], [0, 202])
        self.assertEqual([v['score_hundredths'] for v in after['items']], [101, 1])
        self.assertEqual((before['revision'], after['revision']), (2, 3))

    def test_invalid_syntax_and_precision_whole_batch_400(self):
        original = self.state()
        for items in ([], None, [None], [self.item()] * 2, [self.item(), self.item(2, -1)],
                      [self.item(2, True)], [self.item(2, '1')], [self.item(2, 0.001)],
                      [self.item(2, float('nan'))], [self.item(2, float('inf'))],
                      [self.item(2, 10**400)], [self.item(comment=None)], [self.item(comment='字'*1001)],
                      [{**self.item(), 'question_version_id': True}], [{**self.item(), 'extra': 1}],
                      [{'question_version_id': 1, 'score': 0}]):
            with self.subTest(items=str(items)[:80]):
                self.grade(items, status=400)
                self.assertEqual(self.state(), original)
        for revision in (True, -1, 0.0, '0', None, 9223372036854775807):
            self.grade([self.item()], revision=revision, status=400)
        for body in ({}, {'revision': 0, 'items': [self.item()], 'score': 1}, []):
            self.call(self.teacher, 'PATCH', self.url, body, 400)
        self.assertEqual(self.state(), original)

    def test_nonmanual_outside_paper_and_over_max_whole_batch_422(self):
        newer = self.call(self.teacher, 'PATCH', f"/questions/{self.qs[1]['id']}", {'stem': '新版'}).json['data']
        original = self.state()
        for bad in (self.item(0, 0), self.item(3, 0), self.item(2, 2.03), self.item(2, 1e100),
                    {**self.item(), 'question_version_id': 999},
                    {**self.item(), 'question_version_id': newer['version_id']}):
            self.grade([self.item(), bad], status=422)
            self.assertEqual(self.state(), original)

    def test_stale_revision_no_overwrite_or_audit(self):
        self.grade([self.item()])
        current = self.state()
        self.grade([self.item(score=1)], status=409)
        self.assertEqual(self.state(), current)

    def test_latest_student_results_and_original_replay_after_grading(self):
        self.grade([self.item(), self.item(2, 1.02)])
        self.at(14)
        self.assertEqual(self.submit(self.paper_id, self.answers, key=self.key).data, self.original.data)
        result = self.call(self.student, 'GET', f'/attempts/{self.id}').json['data']
        self.assertEqual((result['revision'], result['score']), (1, 1.62))
        self.assertEqual(result['answers'][1]['comment'], '评语')
        for answer in result['answers']:
            self.assertNotIn('answer', answer)
            self.assertNotIn('explanation', answer)
        self.at(15)
        self.assertEqual(self.call(self.student, 'GET', f'/attempts/{self.id}').json['data']['answers'][1]['answer'], '参考')

    def test_current_teacher_membership_csrf_and_session_required(self):
        original = self.state()
        self.grade([self.item()], status=403, client=self.student)
        for client, status in ((self.outsider, 404), (self.admin, 404), (self.app.test_client(), 401)):
            self.grade([self.item()], status=status, client=client)
        for headers in ({'Origin': ORIGIN}, {'Origin': 'https://other.example', 'X-CSRF-Token': self.teacher.csrf}):
            response = self.teacher.patch('/api/v1'+self.url, json={'revision': 0, 'items': [self.item()]}, headers=headers)
            self.assertEqual(response.status_code, 403)
        self.call(self.teacher, 'PATCH', self.url+'?revision=0', {'revision': 0, 'items': [self.item()]}, 400)
        with closing(connect(self.path)) as db:
            db.execute('UPDATE course_member SET active=0 WHERE course_id=? AND user_id=?', (self.course_id, self.teacher_id))
        self.grade([self.item()], status=404)
        self.assertEqual(self.state(), original)
        with closing(connect(self.path)) as db:
            db.execute('UPDATE user SET active=0 WHERE id=?', (self.teacher_id,))
        self.grade([self.item()], status=401)

    def test_second_score_summary_and_audit_failures_roll_back_all(self):
        original = self.state()
        triggers = [f"CREATE TRIGGER fail BEFORE UPDATE ON answer WHEN NEW.question_version_id={self.qs[2]['version_id']} BEGIN SELECT RAISE(ABORT,'injected'); END;",
                    "CREATE TRIGGER fail BEFORE UPDATE ON attempt BEGIN SELECT RAISE(ABORT,'injected'); END;",
                    "CREATE TRIGGER fail BEFORE INSERT ON audit_event WHEN NEW.action='attempt.manual_scores' BEGIN SELECT RAISE(ABORT,'injected'); END;"]
        for sql in triggers:
            with closing(connect(self.path)) as db:
                db.execute(sql)
            self.grade([self.item(), self.item(2, 1)], status=409)
            self.assertEqual(self.state(), original)
            with closing(connect(self.path)) as db:
                db.execute('DROP TRIGGER fail')
        self.assertEqual(self.grade([self.item(), self.item(2, 1)])['revision'], 1)

    def test_two_sessions_same_revision_exactly_one_batch_commits(self):
        barrier = Barrier(2)
        clients = [self.app.test_client() for _ in range(2)]
        for client in clients:
            self.login(client, 'T006TEACH')

        def send(index):
            barrier.wait(timeout=10)
            return clients[index].patch('/api/v1'+self.url, json={'revision': 0, 'items': [self.item(score=index)]},
                                        headers={'Origin': ORIGIN, 'X-CSRF-Token': clients[index].csrf})

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(send, range(2)))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        fact, _, events = self.state()
        self.assertEqual((fact['revision'], len(events)), (1, 1))

    def test_populated_backup_restores_scores_audit_and_replay(self):
        self.grade([self.item(), self.item(2, 1)])
        backup = self.path.with_name('graded-backup.db')
        with closing(connect(self.path)) as source, closing(connect(backup)) as target:
            source.backup(target)
            self.assertEqual(target.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(target.execute('PRAGMA foreign_key_check').fetchall(), [])
        migrate(backup)
        self.app.config['DATABASE_PATH'] = str(backup)
        latest = self.call(self.student, 'GET', f'/attempts/{self.id}').json['data']
        self.assertEqual((latest['revision'], latest['score']), (1, 1.6))
        self.assertEqual(self.submit(self.paper_id, self.answers, key=self.key).data, self.original.data)
        with closing(connect(backup)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit_event WHERE action='attempt.manual_scores'").fetchone()[0], 1)
