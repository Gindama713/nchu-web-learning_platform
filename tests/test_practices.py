"""C04 actual SQLite/HTTP; knowledge schema only is an explicit SPEC-005 fixture."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from backend.models import paper, practice
from backend.shared.db import connect, migrate, write
from tests import test_attempts as fixtures
from tests.test_questions import ORIGIN, QuestionApiBase


class RealPracticeTest(QuestionApiBase):
    def test_empty_permissions_and_migration_checksum(self):
        response = self.call(self.student, 'GET', '/users/me/wrong-questions')
        self.assertEqual(response.json['data'], [])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        for client, status in ((self.teacher, 403), (self.admin, 403), (self.app.test_client(), 401)):
            self.call(client, 'GET', '/users/me/wrong-questions', status=status)
        for suffix in ('?student_id=1', '?knowledge_id=0', '?page=0', '?page_size=101', '?page=1&page=2',
                       '?page=9223372036854775807', '?knowledge_id=true'):
            self.call(self.student, 'GET', '/users/me/wrong-questions'+suffix, status=400)
        migrate(self.path)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            db.execute("UPDATE schema_migration SET checksum='bad' WHERE version=?", (practice.VERSION,))
        self.call(self.student, 'GET', '/users/me/wrong-questions', status=503)
        with self.assertRaises(RuntimeError):
            migrate(self.path)


class PracticeFixtureTest(fixtures.AttemptApiBase):
    create_question = fixtures.KnowledgeFixtureAttemptTest.create_question
    make_paper = fixtures.KnowledgeFixtureAttemptTest.make_paper
    at = fixtures.KnowledgeFixtureAttemptTest.at
    answer = fixtures.KnowledgeFixtureAttemptTest.answer
    counts = fixtures.KnowledgeFixtureAttemptTest.counts

    def setUp(self):
        super().setUp()
        self.knowledge_fixture()


class KnowledgeFixturePracticeTest(PracticeFixtureTest):
    def practice(self, q, value, *, key=None, client=None, status=201):
        client = client or self.student
        response = client.post(f"/api/v1/questions/{q['id']}/practice-attempts",
                               json={'question_version_id': q['version_id'], 'answer': value},
                               headers={'Origin': ORIGIN, 'X-CSRF-Token': client.csrf,
                                        'Idempotency-Key': str(uuid4()) if key is None else key})
        self.assertEqual(response.status_code, status, response.json)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return response

    def wrong(self, suffix=''):
        return self.call(self.student, 'GET', '/users/me/wrong-questions'+suffix).json

    def test_fixed_version_dedup_resolve_and_new_error(self):
        q = self.create_question(practice_available=True, knowledge_ids=[1, 2], explanation='原版解析')
        self.practice(q, 'B')
        row = self.wrong()['data'][0]
        self.assertEqual((row['question_version_id'], row['wrong_count'], row['resolved'], row['answer_visible']),
                         (q['version_id'], 1, False, True))
        new = self.call(self.teacher, 'PATCH', f"/questions/{q['id']}",
                        {'answer': 'B', 'knowledge_ids': [2], 'practice_available': False}).json['data']
        correct = self.practice(q, 'A').json['data']
        self.assertEqual((correct['score'], correct['correct'], correct['explanation']), (100, True, '原版解析'))
        self.assertEqual(self.wrong()['data'][0]['wrong_count'], 1)
        self.assertTrue(self.wrong()['data'][0]['resolved'])
        self.practice(new, 'B', status=409)
        self.practice(q, 'B')
        self.assertEqual(self.wrong()['total'], 1)
        self.assertEqual((self.wrong()['data'][0]['wrong_count'], self.wrong()['data'][0]['resolved']), (2, False))
        self.login(self.student, 'T006STUD1')
        self.assertEqual(self.wrong()['data'][0]['wrong_count'], 2)
        self.assertEqual(self.wrong('?knowledge_id=1')['total'], 1)  # source tags, not latest tags
        self.assertEqual(self.wrong('?knowledge_id=999')['total'], 0)
        self.assertEqual(self.wrong('?page=2&page_size=1')['data'], [])

    def test_objective_types_null_and_invalid_values(self):
        qs = [self.create_question(practice_available=True),
              self.create_question(type='multiple', answer=['A', 'B'], practice_available=True),
              self.create_question(type='boolean', options=[], answer=False, practice_available=True),
              self.create_question(type='numeric', options=[], answer=0.2, tolerance=0.1, practice_available=True)]
        for q, value in zip(qs, ['A', ['B', 'A'], False, 0.3]):
            self.assertTrue(self.practice(q, value).json['data']['correct'])
        self.practice(qs[1], ['A'])
        self.practice(qs[3], 0.30000000000000004)
        self.assertEqual(self.wrong()['total'], 2)
        for q in qs:
            self.practice(q, None)
        self.practice(qs[1], [])
        self.assertEqual(self.wrong()['total'], 2)
        self.assertEqual([r['wrong_count'] for r in self.wrong()['data']], [1, 1])
        for q, value in ((qs[0], True), (qs[0], 'Z'), (qs[1], ['A', 'A']), (qs[1], 'A'),
                         (qs[2], 0), (qs[2], 'false'), (qs[3], '0.2'), (qs[3], float('nan'))):
            self.practice(q, value, status=400)
        short = self.create_question(type='short', options=[], answer='参考')
        self.practice(short, '文本', status=409)
        private = self.create_question()
        self.practice(private, 'A', status=409)
        mismatch = {**qs[0], 'version_id': qs[1]['version_id']}
        self.practice(mismatch, 'A', status=404)

    def test_paper_errors_only_actual_objective_and_review_visibility(self):
        qs = [self.create_question(knowledge_ids=[1, 2]), self.create_question(),
              self.create_question(type='short', options=[], answer='参考')]
        paper_id = self.make_paper(qs)
        self.at(13)
        key = str(uuid4())
        response = self.submit(paper_id, [self.answer(qs[0], 'B'), self.answer(qs[2], '学生文本')], key=key)
        row = self.wrong()['data'][0]
        self.assertEqual(self.wrong()['total'], 1)
        self.assertEqual((row['last_attempt_type'], row['last_attempt_id'], row['wrong_count']),
                         ('paper', response.json['data']['id'], 1))
        self.assertFalse(row['answer_visible'])
        self.assertNotIn('answer', row)
        self.assertFalse(row['can_practice'])
        self.call(self.teacher, 'PATCH', f"/attempts/{response.json['data']['id']}/manual-scores",
                  {'revision': 0, 'items': [{'question_version_id': qs[2]['version_id'], 'score': 0, 'comment': ''}]})
        self.at(14)
        self.assertFalse(self.wrong()['data'][0]['answer_visible'])
        self.assertEqual(self.submit(paper_id, [self.answer(qs[0], 'B'), self.answer(qs[2], '学生文本')], key=key).data,
                         response.data)
        self.assertEqual(self.wrong()['data'][0]['wrong_count'], 1)
        self.at(15)
        self.assertEqual(self.wrong()['data'][0]['answer'], 'A')

    def test_error_counts_across_paper_and_practice_sources(self):
        q = self.create_question(practice_available=True)
        self.practice(q, 'B')
        self.practice(q, 'A')
        self.assertTrue(self.wrong()['data'][0]['resolved'])
        paper_id = self.make_paper([q], kind='homework')
        self.at(13)
        self.submit(paper_id, [self.answer(q, 'B')])
        row = self.wrong()['data'][0]
        self.assertEqual((row['wrong_count'], row['last_attempt_type'], row['resolved'], row['answer_visible']),
                         (2, 'paper', False, False))
        self.practice(q, 'A')
        self.assertTrue(self.wrong()['data'][0]['resolved'])
        self.practice(q, 'B')
        row = self.wrong()['data'][0]
        self.assertEqual((row['wrong_count'], row['last_attempt_type'], row['resolved']), (3, 'practice', False))

    def test_practice_idempotency_normalization_scope_expiry_and_concurrency(self):
        q = self.create_question(type='multiple', answer=['A', 'B'], practice_available=True)
        key = str(uuid4())
        first = self.practice(q, ['A'], key=key)
        self.assertEqual(self.practice(q, ['A'], key=key.upper()).data, first.data)
        self.practice(q, ['B'], key=key, status=409)
        other = self.create_question(practice_available=True)
        self.practice(other, 'A', key=key, status=409)
        numeric = self.create_question(type='numeric', options=[], answer=1, practice_available=True)
        num_key = str(uuid4())
        num = self.practice(numeric, 1, key=num_key)
        self.assertEqual(self.practice(numeric, 1.0, key=num_key).data, num.data)
        concurrent_key = str(uuid4())
        clients = [self.app.test_client() for _ in range(2)]
        for client in clients:
            self.login(client, 'T006STUD1')
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda client: self.practice(q, ['B', 'A'], key=concurrent_key, client=client).data, clients))
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.wrong()['data'][0]['wrong_count'], 1)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM practice_attempt').fetchone()[0], 3)
            db.execute("UPDATE idempotency_record SET expires_at='2026-10-12T00:00:00.000Z' WHERE key=?", (key,))
        self.practice(q, ['A'], key=key)
        self.assertEqual(self.wrong()['data'][0]['wrong_count'], 2)
        paper_id = self.make_paper([q], kind='homework')
        self.at(13)
        self.submit(paper_id, [], key=key)  # separate operation, same UUID allowed

    def test_current_access_csrf_revocation_and_other_student_isolation(self):
        q = self.create_question(practice_available=True)
        key = str(uuid4())
        self.practice(q, 'B', key=key)
        self.assertEqual(self.call(self.outsider, 'GET', '/users/me/wrong-questions').json['data'], [])
        self.practice(q, 'B', client=self.outsider, status=404)
        for client in (self.teacher, self.admin):
            self.practice(q, 'A', client=client, status=403)
        path = f"/api/v1/questions/{q['id']}/practice-attempts"
        for headers in ({'Origin': ORIGIN}, {'Origin': 'https://foreign.example', 'X-CSRF-Token': self.student.csrf}):
            self.assertEqual(self.student.post(path, json={'question_version_id': q['version_id'], 'answer': 'B'},
                                                headers=headers).status_code, 403)
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{self.student_id}', status=204)
        self.practice(q, 'B', key=key, status=404)
        self.assertEqual(self.wrong()['total'], 0)
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members',
                  {'user_id': self.student_id, 'member_role': 'student'}, 201)
        self.assertEqual(self.wrong()['total'], 1)
        self.call(self.admin, 'PATCH', f'/users/{self.student_id}', {'active': False})
        self.practice(q, 'B', key=key, status=401)
        self.call(self.student, 'GET', '/users/me/wrong-questions', status=401)

    def test_reserved_all_versions_anomalous_open_replay_and_all_read_paths(self):
        q = self.create_question()
        data = self.call(self.teacher, 'POST', f'/courses/{self.course_id}/papers',
                         {'title': '保密quiz', 'kind': 'quiz', 'confidential': True,
                          'items': [{'question_version_id': q['version_id'], 'points': 10}]}, 201).json['data']
        paper_id = data['id']
        with self.app.test_request_context(), write() as db:
            paper.publish(db, paper.find(db, paper_id),
                          {**{k: v for k, v in fixtures.WINDOW.items() if k != 'review_at'},
                           'confidentiality_note': '确认未公开'}, quiz=True)
        self.at(13)
        self.submit(paper_id, [self.answer(q, 'B')])
        new = self.call(self.teacher, 'PATCH', f"/questions/{q['id']}", {'stem': '新版本'}).json['data']
        # Explicitly anomalous legacy public flag, not a successful business opening.
        with closing(connect(self.path)) as db:
            db.execute('DROP TRIGGER question_version_no_update')
            db.execute('UPDATE question_version SET practice_available=1 WHERE question_id=?', (q['id'],))
        self.at(14)
        for version in (q, new):
            self.practice(version, 'B', status=409)
        self.call(self.student, 'GET', self.url, status=409)
        row = self.wrong()['data'][0]
        self.assertFalse(row['answer_visible'])
        self.assertFalse(row['can_practice'])
        self.assertNotIn('explanation', row)
        self.assertNotIn('answer', self.call(self.student, 'GET', f'/papers/{paper_id}').json['data']['items'][0])
        with closing(connect(self.path)) as db:
            # The actual C05 review endpoint is not claimed: controlled stored review boundary.
            db.execute("UPDATE paper SET review_at='2026-10-13T14:00:00.000Z' WHERE id=?", (paper_id,))
        key = str(uuid4())
        first = self.practice(q, 'B', key=key)
        self.assertTrue(self.wrong()['data'][0]['answer_visible'])
        self.assertEqual(self.practice(q, 'B', key=key).data, first.data)
        with closing(connect(self.path)) as db:
            db.execute('DROP TRIGGER paper_published_frozen')
            db.execute('UPDATE paper SET review_at=NULL WHERE id=?', (paper_id,))
        self.practice(q, 'B', key=key, status=409)
        self.assertFalse(self.wrong()['data'][0]['answer_visible'])

    def test_failure_rollbacks_do_not_consume_key_or_resolve_history(self):
        q = self.create_question(practice_available=True)
        self.practice(q, 'B')
        for table, action in (('wrong_question', 'UPDATE'), ('audit_event', 'INSERT'), ('idempotency_record', 'INSERT')):
            key = str(uuid4())
            with closing(connect(self.path)) as db:
                db.executescript(f"CREATE TRIGGER fail_c04 BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'injected'); END;")
            self.practice(q, 'A', key=key, status=409)
            self.assertFalse(self.wrong()['data'][0]['resolved'])
            with closing(connect(self.path)) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM practice_attempt').fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT count(*) FROM idempotency_record WHERE key=?', (key,)).fetchone()[0], 0)
                db.execute('DROP TRIGGER fail_c04')
        paper_id = self.make_paper([q], kind='homework')
        self.at(13)
        with closing(connect(self.path)) as db:
            db.executescript("CREATE TRIGGER fail_c04 BEFORE UPDATE ON wrong_question BEGIN SELECT RAISE(ABORT,'injected'); END;")
        self.submit(paper_id, [self.answer(q, 'B')], status=409)
        self.assertEqual(self.counts(), [0, 0, 1])
        with closing(connect(self.path)) as db:
            db.execute('DROP TRIGGER fail_c04')
        self.submit(paper_id, [self.answer(q, 'B')])

    def test_upgrade_backfill_retention_and_populated_backup_http(self):
        q = self.create_question()
        paper_id = self.make_paper([q])
        self.at(13)
        # Populate historical C03 facts without the C04 projection, then run the
        # actual new SQL via the migration runner against this old populated DB.
        with patch('backend.models.practice.record_paper_errors'):
            self.submit(paper_id, [self.answer(q, 'B')])
        with closing(connect(self.path)) as db:
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND (tbl_name='practice_attempt' OR tbl_name='wrong_question')").fetchall():
                db.execute(f'DROP TRIGGER {row[0]}')
            db.execute('DROP TABLE wrong_question')
            db.execute('DROP TABLE practice_attempt')
            db.execute('DELETE FROM schema_migration WHERE version=?', (practice.VERSION,))
        migrate(self.path)
        self.assertEqual(self.wrong()['data'][0]['wrong_count'], 1)
        migrate(self.path)
        self.at(15)
        public = self.create_question(practice_available=True)
        key = str(uuid4())
        first = self.practice(public, 'B', key=key)
        backup = Path(self.temporary.name) / 'c04-backup.db'
        with closing(connect(self.path)) as db:
            for sql in ('DELETE FROM practice_attempt', 'UPDATE practice_attempt SET correct=1', 'DELETE FROM wrong_question',
                        'UPDATE wrong_question SET last_attempt_id=999'):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql)
            with closing(connect(backup)) as target:
                db.backup(target)
                self.assertEqual(target.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(target.execute('PRAGMA foreign_key_check').fetchall(), [])
        migrate(backup)
        self.app.config['DATABASE_PATH'] = str(backup)
        self.assertEqual(self.wrong()['total'], 2)
        self.assertEqual(self.practice(public, 'B', key=key).data, first.data)

    def test_same_identity_private_new_version_cannot_become_confidential(self):
        q = self.create_question(practice_available=True)
        new = self.call(self.teacher, 'PATCH', f"/questions/{q['id']}", {'practice_available': False}).json['data']
        paper = self.call(self.teacher, 'POST', f'/courses/{self.course_id}/papers',
                          {'title': '不应保密', 'kind': 'exam',
                           'items': [{'question_version_id': new['version_id'], 'points': 10}]}, 201).json['data']
        self.call(self.teacher, 'POST', f"/papers/{paper['id']}/publish",
                  {**fixtures.WINDOW, 'confidentiality_note': '确认'}, 409)

    def test_strict_practice_request_failure_never_consumes_key(self):
        q = self.create_question(practice_available=True)
        key = str(uuid4())
        path = f"/api/v1/questions/{q['id']}/practice-attempts"
        headers = {'Origin': ORIGIN, 'X-CSRF-Token': self.student.csrf, 'Idempotency-Key': key}
        for body in (None, [], {}, {'answer': 'B'}, {'question_version_id': True, 'answer': 'B'},
                     {'question_version_id': q['version_id'], 'answer': 'B', 'score': 100}):
            self.assertEqual(self.student.post(path, json=body, headers=headers).status_code, 400)
        self.assertEqual(self.student.post(path+'?x=1', json={'question_version_id': q['version_id'], 'answer': 'B'},
                                          headers=headers).status_code, 400)
        for bad in ('', 'bad', key.replace('-', ''), '{'+key+'}'):
            self.practice(q, 'B', key=bad, status=400)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM practice_attempt').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM wrong_question').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM idempotency_record').fetchone()[0], 0)
        self.practice(q, 'B', key=key)

    def test_practice_conflicting_content_concurrent_only_one_success(self):
        q = self.create_question(practice_available=True)
        key = str(uuid4())
        clients = [self.app.test_client() for _ in range(2)]
        for client in clients:
            self.login(client, 'T006STUD1')

        def submit(pair):
            client, value = pair
            return client.post(f"/api/v1/questions/{q['id']}/practice-attempts",
                               json={'question_version_id': q['version_id'], 'answer': value},
                               headers={'Origin': ORIGIN, 'X-CSRF-Token': client.csrf, 'Idempotency-Key': key})

        with ThreadPoolExecutor(2) as pool:
            responses = list(pool.map(submit, zip(clients, ['A', 'B'])))
        self.assertEqual(sorted(r.status_code for r in responses), [201, 409])
        accepted = next(r.json['data'] for r in responses if r.status_code == 201)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM practice_attempt').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM wrong_question').fetchone()[0], int(not accepted['correct']))
            self.assertEqual(db.execute("SELECT count(*) FROM audit_event WHERE action='practice.submit'").fetchone()[0], 1)

    def test_timed_review_applies_to_all_versions_and_wrong_answer_reads(self):
        q = self.create_question()
        paper_id = self.make_paper([q])
        self.at(13)
        submitted = self.submit(paper_id, [self.answer(q, 'B')]).json['data']
        new = self.call(self.teacher, 'PATCH', f"/questions/{q['id']}", {'stem': '另一个固定版本'}).json['data']
        self.at(14)
        self.call(self.teacher, 'PATCH', f"/questions/{q['id']}", {'practice_available': True}, 409)
        with closing(connect(self.path)) as db:
            db.execute('DROP TRIGGER question_version_no_update')
            db.execute('UPDATE question_version SET practice_available=1 WHERE question_id=?', (q['id'],))
        for item in (q, new):
            self.practice(item, 'B', status=409)
        self.assertFalse(self.wrong()['data'][0]['answer_visible'])
        self.assertNotIn('answer', self.call(self.student, 'GET', f"/attempts/{submitted['id']}").json['data']['answers'][0])
        self.at(15)
        for item in (q, new):
            self.practice(item, 'B')
        self.assertTrue(self.wrong()['data'][0]['answer_visible'])
        self.assertEqual(self.wrong()['data'][0]['wrong_count'], 3)
