"""C03a actual 001/005/006 session, knowledge, paper and attempt HTTP tests."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from uuid import uuid4

from backend.models import attempt, paper
from backend.shared.db import connect, migrate, write
from tests.test_papers import WINDOW
from tests.test_question_validation import question
from tests.test_questions import ORIGIN, QuestionApiBase


class AttemptApiBase(QuestionApiBase):
    def submit(self, paper_id, answers, *, key=None, client=None, quiz=False, status=201):
        client = client or self.student
        key = str(uuid4()) if key is None else key
        response = client.post(f"/api/v1/{'quizzes' if quiz else 'papers'}/{paper_id}/attempts",
                               json={'answers': answers}, headers={'Origin': ORIGIN,
                               'X-CSRF-Token': client.csrf, 'Idempotency-Key': key})
        self.assertEqual(response.status_code, status, response.json)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return response


class RealAttemptApiTest(AttemptApiBase):
    def test_real_empty_permissions_and_missing_knowledge_tag(self):
        path = f'/courses/{self.course_id}/attempts'
        for client in (self.teacher, self.student):
            self.assertEqual(self.call(client, 'GET', path).json['data'], [])
        self.call(self.outsider, 'GET', path, status=404)
        self.call(self.app.test_client(), 'GET', path, status=401)
        self.call(self.student, 'GET', '/attempts/999', status=404)
        self.submit(999, [], status=404)
        self.call(self.teacher, 'POST', self.url, question(), 400)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM attempt').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM idempotency_record').fetchone()[0], 0)

    def test_real_migration_replay_and_checksum_failure(self):
        migrate(self.path)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT checksum FROM schema_migration WHERE version=?',
                                        (attempt.VERSION,)).fetchone()[0], attempt.CHECKSUM)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            db.execute("UPDATE schema_migration SET checksum='bad' WHERE version=?", (attempt.VERSION,))
        self.call(self.student, 'GET', f'/courses/{self.course_id}/attempts', status=503)
        with self.assertRaises(RuntimeError):
            migrate(self.path)


class KnowledgeFixtureAttemptTest(AttemptApiBase):
    def setUp(self):
        super().setUp()
        self.knowledge_fixture()

    def create_question(self, **values):
        return self.call(self.teacher, 'POST', self.url, question(**values), 201).json['data']

    def make_paper(self, questions, *, kind='exam', points=None, quiz_publish=False):
        items = [{'question_version_id': q['version_id'], 'points': points[i] if points else 10.01}
                 for i, q in enumerate(questions)]
        row = self.call(self.teacher, 'POST', f'/courses/{self.course_id}/papers',
                        {'title': 'C03a卷', 'kind': kind, 'items': items}, 201).json['data']
        if quiz_publish:
            with self.app.test_request_context(), write() as db:
                paper.publish(db, paper.find(db, row['id']),
                              {k: v for k, v in WINDOW.items() if k != 'review_at'}, quiz=True)
        else:
            self.call(self.teacher, 'POST', f"/papers/{row['id']}/publish",
                      {**WINDOW, 'confidentiality_note': '确认未公开且非简单复制'})
        return row['id']

    def at(self, hour, *, day=13):
        self.app.config['TEST_NOW'] = datetime(2026, 10, day, hour, tzinfo=UTC)
        self.login(self.teacher, 'T006TEACH')
        self.login(self.student, 'T006STUD1')

    def answer(self, question, value):
        return {'question_version_id': question['version_id'], 'value': value}

    def counts(self):
        with closing(connect(self.path)) as db:
            return [db.execute(f'SELECT count(*) FROM {name}').fetchone()[0]
                    for name in ('attempt', 'answer', 'idempotency_record')]

    def test_five_types_old_version_exact_scores_and_read_protection(self):
        qs = [self.create_question(), self.create_question(type='multiple', answer=['A', 'B']),
              self.create_question(type='boolean', options=[], answer=False),
              self.create_question(type='numeric', options=[], answer=0.2, tolerance=0.1),
              self.create_question(type='short', options=[], answer='参考')]
        paper_id = self.make_paper(qs, points=[0.1, 0.2, 1.01, 2.02, 5])
        self.call(self.teacher, 'PATCH', f"/questions/{qs[0]['id']}", {'answer': 'B'})
        self.at(13)
        response = self.submit(paper_id, [self.answer(q, v) for q, v in zip(qs, ['A', ['B', 'A'], False, 0.3, ' 学生文本 '])])
        data = response.json['data']
        self.assertEqual((data['status'], data['score'], data['partial_score'], data['total_points'], data['revision']),
                         ('partial', None, 3.33, 8.33, 0))
        self.assertEqual([a['correct'] for a in data['answers']], [True, True, True, True, None])
        self.assertEqual(data['answers'][-1]['grading_status'], 'pending')
        self.assertIsNone(data['answers'][-1]['score'])
        self.assertEqual(data['answers'][-1]['value'], '学生文本')
        for item in data['answers']:
            self.assertNotIn('answer', item)
            self.assertNotIn('explanation', item)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT partial_score_hundredths FROM attempt').fetchone()[0], 333)
            self.assertEqual([r[0] for r in db.execute('SELECT score_hundredths FROM answer ORDER BY id')], [10, 20, 101, 202, None])
        path = f"/attempts/{data['id']}"
        self.assertEqual(self.call(self.student, 'GET', path).json['data'], data)
        teacher = self.call(self.teacher, 'GET', path).json['data']
        self.assertEqual(teacher['answers'][0]['answer'], 'A')
        self.at(14)
        self.assertNotIn('answer', self.call(self.student, 'GET', path).json['data']['answers'][0])
        self.at(15)
        self.assertEqual(self.call(self.student, 'GET', path).json['data']['answers'][0]['answer'], 'A')

    def test_blank_paper_unanswered_normalizations_share_fingerprint(self):
        qs = [self.create_question(), self.create_question(type='multiple', answer=['A']),
              self.create_question(type='short', options=[], answer='参考')]
        paper_id = self.make_paper(qs, kind='homework')
        self.at(13)
        key = str(uuid4())
        first = self.submit(paper_id, [], key=key)
        data = first.json['data']
        self.assertEqual((data['status'], data['score'], data['partial_score']), ('graded', 0, 0))
        self.assertEqual([a['grading_status'] for a in data['answers']], ['unanswered'] * 3)
        self.assertEqual([a['correct'] for a in data['answers']], [False, False, None])
        second = self.submit(paper_id, [self.answer(q, v) for q, v in zip(qs, [None, [], ' \t\n '])], key=key)
        self.assertEqual(first.data, second.data)
        self.assertEqual(self.counts(), [1, 3, 1])

    def test_incorrect_values_zero_no_multiple_partial_credit(self):
        qs = [self.create_question(), self.create_question(type='multiple', answer=['A', 'B']),
              self.create_question(type='boolean', options=[], answer=True),
              self.create_question(type='numeric', options=[], answer=0.2, tolerance=0.1)]
        paper_id = self.make_paper(qs)
        self.at(13)
        data = self.submit(paper_id, [self.answer(q, v) for q, v in zip(qs, ['B', ['A'], False, 0.30000000000000004])]).json['data']
        self.assertEqual(data['score'], 0)
        self.assertEqual([a['correct'] for a in data['answers']], [False] * 4)

    def test_invalid_batches_leave_no_answers_audit_or_success_keys(self):
        qs = [self.create_question(), self.create_question(type='multiple', answer=['A']),
              self.create_question(type='boolean', options=[], answer=True),
              self.create_question(type='numeric', options=[], answer=1),
              self.create_question(type='short', options=[], answer='参考')]
        paper_id = self.make_paper(qs)
        self.at(13)
        key = str(uuid4())
        invalid_values = [(0, True), (0, 'missing'), (0, []), (1, ['A', 'A']), (1, ['missing']),
                          (1, [['A']]), (1, 'A'), (2, 0), (2, 'true'), (3, True), (3, '1'),
                          (3, float('nan')), (3, float('inf')), (3, 10**400), (4, 1), (4, 'x'*5001)]
        for index, value in invalid_values:
            with self.subTest(index=index, value=str(value)[:30]):
                self.submit(paper_id, [self.answer(qs[0], 'A'), self.answer(qs[index], value)]
                            if index else [self.answer(qs[0], value)], key=key, status=400)
        for answers in ([self.answer(qs[0], 'A')] * 2, [{'question_version_id': 999, 'value': 'A'}],
                        [{'question_version_id': True, 'value': 'A'}], [{'question_version_id': 1.0, 'value': 'A'}],
                        [{'question_version_id': qs[0]['version_id']}], [None], [{}], 'answers'):
            self.submit(paper_id, answers, key=key, status=400)
        for payload in (None, [], {}, {'answers': [], 'score': 100}):
            response = self.student.post(f'/api/v1/papers/{paper_id}/attempts', json=payload,
                                         headers={'Origin': ORIGIN, 'X-CSRF-Token': self.student.csrf, 'Idempotency-Key': key})
            self.assertEqual(response.status_code, 400)
        for bad_key in ('', 'not-uuid', key.replace('-', ''), '{'+key+'}'):
            self.submit(paper_id, [], key=bad_key, status=400)
        self.assertEqual(self.counts(), [0, 0, 0])
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit_event WHERE action='attempt.submit'").fetchone()[0], 0)
        # An earlier failed request did not consume the key.
        self.submit(paper_id, [], key=key)

    def test_window_boundaries_replay_exact_snapshot_after_deadline_and_review(self):
        q = self.create_question()
        paper_id = self.make_paper([q])
        key = str(uuid4())
        answers = [self.answer(q, 'A')]
        self.submit(paper_id, answers, key=key, status=409)
        self.assertEqual(self.counts(), [0, 0, 0])
        self.at(13)  # start inclusive
        original = self.submit(paper_id, answers, key=key)
        self.at(14)  # end exclusive
        self.assertEqual(self.submit(paper_id, answers, key=key).data, original.data)
        self.submit(paper_id, answers, status=409)
        self.submit(paper_id, [self.answer(q, 'B')], key=key, status=409)
        self.at(15)
        self.assertEqual(self.submit(paper_id, answers, key=key).data, original.data)
        self.assertNotIn('answer', original.json['data']['answers'][0])
        # A new student with no submission is also rejected exactly at end.
        other_q = self.create_question()
        other_id = self.make_paper([other_q])
        self.at(14)
        self.submit(other_id, [], status=409)
        self.assertEqual(self.counts(), [1, 1, 1])

    def test_quiz_alias_same_operation_and_null_review_remains_hidden(self):
        q = self.create_question()
        paper_id = self.make_paper([q], kind='quiz', quiz_publish=True)
        self.at(13)
        key = str(uuid4())
        first = self.submit(paper_id, [self.answer(q, 'A')], key=key, quiz=True)
        self.at(15)
        self.assertEqual(self.submit(paper_id, [self.answer(q, 'A')], key=key).data, first.data)
        data = self.call(self.student, 'GET', f"/attempts/{first.json['data']['id']}").json['data']
        self.assertNotIn('answer', data['answers'][0])
        self.submit(paper_id, [], quiz=True, status=409)
        normal = self.make_paper([self.create_question()])
        self.submit(normal, [], quiz=True, status=404)
        self.assertEqual(self.counts(), [1, 1, 1])

    def test_replay_uses_saved_revision_and_numeric_semantics(self):
        qs = [self.create_question(type='numeric', options=[], answer=1),
              self.create_question(type='multiple', answer=['A', 'B']),
              self.create_question(type='short', options=[], answer='参考')]
        paper_id = self.make_paper(qs)
        self.at(13)
        key = str(uuid4())
        answers = [self.answer(q, v) for q, v in zip(qs, [1, ['A', 'B'], '文本'])]
        first = self.submit(paper_id, answers, key=key)
        # Simulate C03b's later persisted grade; not a manual-scores API acceptance claim.
        with closing(connect(self.path)) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE answer SET score_hundredths=500,graded_by=? WHERE question_version_id=?',
                       (self.teacher_id, qs[-1]['version_id']))
            db.execute("UPDATE attempt SET status='graded',score_hundredths=2502,partial_score_hundredths=2502,revision=1")
            db.commit()
        replay = self.submit(paper_id, [self.answer(qs[2], ' 文本 '), self.answer(qs[1], ['B', 'A']),
                                      self.answer(qs[0], 1.0)], key=key.upper())
        self.assertEqual(replay.data, first.data)
        latest = self.call(self.student, 'GET', f"/attempts/{first.json['data']['id']}").json['data']
        self.assertEqual((latest['revision'], latest['status'], latest['score']), (1, 'graded', 25.02))
        self.assertEqual(self.counts(), [1, 3, 1])

    def test_expired_key_cannot_bypass_unique_submission_and_fingerprint_preserves_text(self):
        qs = [self.create_question(type='numeric', options=[], answer=10**100),
              self.create_question(type='short', options=[], answer='参考')]
        paper_id = self.make_paper(qs)
        self.at(13)
        key = str(uuid4())
        original = [self.answer(qs[0], 10**100), self.answer(qs[1], 'text a')]
        self.submit(paper_id, original, key=key)
        self.submit(paper_id, [self.answer(qs[0], 10**100+1), self.answer(qs[1], 'text a')], key=key, status=409)
        self.submit(paper_id, [self.answer(qs[0], 10**100), self.answer(qs[1], 'text  a')], key=key, status=409)
        with closing(connect(self.path)) as db:
            expiry = db.execute('SELECT expires_at FROM idempotency_record').fetchone()[0]
        self.assertEqual(expiry, '2026-10-14T13:00:00.000Z')
        self.at(13, day=14)
        self.submit(paper_id, original, key=key, status=409)
        # Keep window open in a separate long-window paper to isolate uniqueness after expiry.
        q = self.create_question()
        row = self.call(self.teacher, 'POST', f'/courses/{self.course_id}/papers',
                        {'title': 'long', 'kind': 'homework', 'items': [{'question_version_id': q['version_id'], 'points': 1}]}, 201).json['data']
        self.call(self.teacher, 'POST', f"/papers/{row['id']}/publish", {
                  'start_at': '2026-10-14T13:00:00Z', 'end_at': '2026-10-16T13:00:00Z', 'review_at': '2026-10-16T13:00:00Z'})
        key2 = str(uuid4())
        self.submit(row['id'], [], key=key2)
        self.at(13, day=15)
        self.submit(row['id'], [], key=key2, status=409)
        self.submit(row['id'], [], status=409)
        self.assertEqual(self.counts(), [2, 3, 2])

    def test_current_access_and_frozen_roster_precede_replay(self):
        q = self.create_question()
        paper_id = self.make_paper([q])
        self.at(13)
        key = str(uuid4())
        first = self.submit(paper_id, [], key=key)
        self.submit(paper_id, [], client=self.teacher, status=403)
        self.submit(paper_id, [], client=self.outsider, status=404)
        self.call(self.outsider, 'GET', f"/attempts/{first.json['data']['id']}", status=404)
        late_id = self.outsider.get('/api/v1/auth/session').json['data']['user']['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members', {'user_id': late_id, 'member_role': 'student'}, 201)
        self.submit(paper_id, [], client=self.outsider, status=404)
        self.call(self.outsider, 'GET', f"/attempts/{first.json['data']['id']}", status=404)
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{self.student_id}', status=204)
        self.submit(paper_id, [], key=key, status=404)
        self.call(self.student, 'GET', f"/attempts/{first.json['data']['id']}", status=404)
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members',
                  {'user_id': self.student_id, 'member_role': 'student'}, 201)
        self.assertEqual(self.submit(paper_id, [], key=key).data, first.data)
        self.login(self.admin, 'T006ADMIN')
        self.call(self.admin, 'PATCH', f'/users/{self.student_id}', {'active': False})
        self.submit(paper_id, [], key=key, status=401)
        self.assertEqual(self.counts(), [1, 1, 1])

    def test_csrf_origin_draft_and_nonpaper_versions(self):
        q = self.create_question()
        paper_id = self.make_paper([q])
        self.at(13)
        for headers in ({'Origin': ORIGIN}, {'Origin': 'https://foreign.example', 'X-CSRF-Token': self.student.csrf}):
            response = self.student.post(f'/api/v1/papers/{paper_id}/attempts', json={'answers': []}, headers=headers)
            self.assertEqual(response.status_code, 403)
        row = self.call(self.teacher, 'POST', f'/courses/{self.course_id}/papers',
                        {'title': 'draft', 'kind': 'homework', 'items': [{'question_version_id': q['version_id'], 'points': 1}]}, 201).json['data']
        self.submit(row['id'], [], status=404)
        other = self.create_question()
        self.submit(paper_id, [self.answer(other, 'A')], status=400)
        newer = self.call(self.teacher, 'PATCH', f"/questions/{q['id']}", {'stem': 'new'}).json['data']
        self.submit(paper_id, [self.answer(newer, 'A')], status=400)
        self.assertEqual(self.counts(), [0, 0, 0])

    def test_history_filters_pagination_and_other_students_are_hidden(self):
        q = self.create_question()
        late_id = self.outsider.get('/api/v1/auth/session').json['data']['user']['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members', {'user_id': late_id, 'member_role': 'student'}, 201)
        paper_id = self.make_paper([q], kind='homework')
        self.at(13)
        key = str(uuid4())
        mine = self.submit(paper_id, [], key=key).json['data']
        other = self.submit(paper_id, [self.answer(q, 'A')], key=key, client=self.outsider).json['data']
        path = f'/courses/{self.course_id}/attempts'
        self.assertEqual(self.call(self.teacher, 'GET', path+'?page_size=1').json['total'], 2)
        self.assertEqual(self.call(self.teacher, 'GET', path+'?page_size=1&page=2').json['data'][0]['id'], mine['id'])
        self.assertEqual(self.call(self.student, 'GET', path).json['total'], 1)
        self.assertEqual(self.call(self.student, 'GET', path+f'?student_id={late_id}').json['data'], [])
        self.assertEqual(self.call(self.teacher, 'GET', path+f'?paper_id={paper_id}&status=graded&student_id={late_id}').json['data'][0]['id'], other['id'])
        self.call(self.student, 'GET', f"/attempts/{other['id']}", status=404)
        for suffix in ('?page=0', '?page=1&page=2', '?page_size=101', '?student_id=true', '?status=complete', '?x=1', '?page=9223372036854775807'):
            self.call(self.teacher, 'GET', path+suffix, status=400)
        self.call(self.student, 'GET', f"/attempts/{mine['id']}?x=1", status=400)

    def test_answer_audit_and_ledger_failures_roll_back_whole_submission(self):
        qs = [self.create_question(), self.create_question(type='boolean', options=[], answer=True)]
        paper_id = self.make_paper(qs)
        self.at(13)
        key = str(uuid4())
        for table, condition in (('answer', f'NEW.question_version_id={qs[1]["version_id"]}'),
                                 ('audit_event', "NEW.action='attempt.submit'"), ('idempotency_record', '1')):
            with closing(connect(self.path)) as db:
                db.executescript(f"CREATE TRIGGER fail_submission BEFORE INSERT ON {table} WHEN {condition} "
                                 "BEGIN SELECT RAISE(ABORT,'injected test failure'); END;")
            self.submit(paper_id, [], key=key, status=409)
            self.assertEqual(self.counts(), [0, 0, 0])
            with closing(connect(self.path)) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM audit_event WHERE action='attempt.submit'").fetchone()[0], 0)
                db.execute('DROP TRIGGER fail_submission')
        self.submit(paper_id, [], key=key)

    def test_database_constraints_retention_and_populated_backup(self):
        q = self.create_question()
        other = self.create_question()
        paper_id = self.make_paper([q])
        self.at(13)
        key = str(uuid4())
        original = self.submit(paper_id, [], key=key)
        data = original.json['data']
        with closing(connect(self.path)) as db:
            for sql, args in (("INSERT INTO attempt(paper_id,student_id,status,score_hundredths,partial_score_hundredths,submitted_at) VALUES(?,999,'graded',0,0,'now')", (paper_id,)),
                              ('DELETE FROM attempt WHERE id=?', (data['id'],)), ('DELETE FROM answer WHERE attempt_id=?', (data['id'],)),
                              ('UPDATE answer SET score_hundredths=1 WHERE attempt_id=?', (data['id'],)),
                              ("UPDATE answer SET value_json='true' WHERE attempt_id=?", (data['id'],)),
                              ("UPDATE attempt SET status='partial' WHERE id=?", (data['id'],)),
                              ("UPDATE attempt SET submitted_at='later' WHERE id=?", (data['id'],)),
                              ("INSERT INTO answer(attempt_id,question_version_id,value_json,answered,score_hundredths) VALUES(?,?,'null',0,0)", (data['id'], other['version_id']))):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql, args)
            with closing(connect(self.temporary.name + '/attempt-backup.db')) as target:
                db.backup(target)
                self.assertEqual(target.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(target.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(target.execute('SELECT value_json FROM answer').fetchone()[0], 'null')
                self.assertEqual(target.execute('SELECT response_json FROM idempotency_record').fetchone()[0],
                                 db.execute('SELECT response_json FROM idempotency_record').fetchone()[0])
        restored = self.temporary.name + '/attempt-backup.db'
        migrate(restored)
        self.app.config['DATABASE_PATH'] = restored
        try:
            self.assertEqual(self.call(self.student, 'GET', f"/attempts/{data['id']}").json['data'], data)
            self.assertEqual(self.submit(paper_id, [], key=key).data, original.data)
        finally:
            self.app.config['DATABASE_PATH'] = str(self.path)

    def test_concurrent_same_key_changed_content_and_different_keys(self):
        # Real separate SQLite connections, same authenticated user; no mutex fixture.
        for mode in ('same', 'changed', 'different'):
            q = self.create_question()
            paper_id = self.make_paper([q], kind='quiz')
            self.at(13)
            key = str(uuid4())
            cookie = self.student.get_cookie('cpu_session').value
            csrf = self.student.csrf
            def send(index, cookie=cookie, mode=mode, paper_id=paper_id, q=q, csrf=csrf, key=key):
                client = self.app.test_client()
                client.set_cookie('cpu_session', cookie)
                value = 'B' if mode == 'changed' and index else 'A'
                return client.post(f"/api/v1/{'quizzes' if index else 'papers'}/{paper_id}/attempts",
                                   json={'answers': [self.answer(q, value)]}, headers={'Origin': ORIGIN,
                                   'X-CSRF-Token': csrf, 'Idempotency-Key': str(uuid4()) if mode == 'different' else key})
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(send, (0, 1)))
            self.assertEqual(sorted(r.status_code for r in results), [201, 201] if mode == 'same' else [201, 409])
            if mode == 'same':
                self.assertEqual(results[0].data, results[1].data)
            with closing(connect(self.path)) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM attempt WHERE paper_id=?', (paper_id,)).fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT count(*) FROM answer a JOIN attempt t ON t.id=a.attempt_id '
                                            'WHERE t.paper_id=?', (paper_id,)).fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT count(*) FROM audit_event WHERE action='attempt.submit' AND object_id IN "
                                            '(SELECT id FROM attempt WHERE paper_id=?)', (paper_id,)).fetchone()[0], 1)

    def test_late_protected_identity_cannot_leak_via_attempt_reads(self):
        q = self.create_question()
        paper_id = self.make_paper([q], kind='homework')
        self.at(13)
        data = self.submit(paper_id, []).json['data']
        self.at(15)
        # Deliberately corrupt historical qualification; real APIs prohibit this state.
        with closing(connect(self.path)) as db:
            new_id = db.execute("INSERT INTO paper(course_id,title,kind,confidential) VALUES(?,'bad history','quiz',1)",
                                (self.course_id,)).lastrowid
            db.execute('INSERT INTO paper_item VALUES(?,?,?,1,100)', (new_id, q['version_id'], q['id']))
            db.execute("UPDATE paper SET status='published',start_at=?,end_at=?,confidentiality_note='test' WHERE id=?",
                       ('2026-10-13T14:00:00.000Z', '2026-10-13T15:00:00.000Z', new_id))
        self.call(self.student, 'GET', f"/attempts/{data['id']}", status=409)
        self.call(self.student, 'GET', f'/courses/{self.course_id}/attempts', status=409)
        self.assertEqual(self.call(self.teacher, 'GET', f"/attempts/{data['id']}").json['data']['answers'][0]['answer'], 'A')

    def test_key_scope_includes_target_and_expired_key_can_accept_another_paper(self):
        ids = [self.make_paper([self.create_question()], kind='homework') for _ in range(2)]
        self.at(13)
        key = str(uuid4())
        self.submit(ids[0], [], key=key)
        conflict = self.submit(ids[1], [], key=key, status=409)
        self.assertEqual(conflict.json['error']['code'], 'IDEMPOTENCY_CONFLICT')
        self.at(13, day=14)
        q = self.create_question()
        row = self.call(self.teacher, 'POST', f'/courses/{self.course_id}/papers', {
                        'title': 'reuse', 'kind': 'homework', 'items': [{'question_version_id': q['version_id'], 'points': 1}]}, 201).json['data']
        self.call(self.teacher, 'POST', f"/papers/{row['id']}/publish", {
                  'start_at': '2026-10-14T13:00:00Z', 'end_at': '2026-10-14T14:00:00Z', 'review_at': '2026-10-14T15:00:00Z'})
        self.submit(row['id'], [], key=key)
        self.assertEqual(self.counts(), [2, 2, 1])
        self.submit(ids[0], [], status=409)

    def test_busy_database_returns_bounded_503_without_consuming_success_key(self):
        paper_id = self.make_paper([self.create_question()])
        self.at(13)
        key = str(uuid4())
        with closing(connect(self.path)) as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            response = self.submit(paper_id, [], key=key, status=503)
            self.assertEqual(response.json['error']['code'], 'DB_BUSY')
            blocker.rollback()
        self.assertEqual(self.counts(), [0, 0, 0])
        self.submit(paper_id, [], key=key)
