"""C09 real HTTP drafts/replay/publication plus explicit race/failure injection."""

import sqlite3
from contextlib import closing
from unittest.mock import patch
from uuid import uuid4

from backend.models import generation_solver
from backend.shared.db import connect, migrate
from tests.test_generation_input import parameters
from tests.test_question_validation import question
from tests.test_questions import ORIGIN, QuestionApiBase


class GeneratedPaperTest(QuestionApiBase):
    def setUp(self):
        super().setUp()
        self.knowledge_fixture()
        self.endpoint = f'/courses/{self.course_id}/generated-papers'

    def create(self, **values):
        return self.call(self.teacher, 'POST', self.url, question(**values), 201).json['data']

    def generate(self, status=201, **values):
        return self.call(self.teacher, 'POST', self.endpoint, {'title': '生成草稿', **parameters(), **values}, status)

    def counts(self):
        with closing(connect(self.path)) as db:
            return tuple(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                         for table in ('generation_snapshot', 'paper', 'paper_item', 'audit_event'))

    def replay(self, snapshot_id, status=201):
        return self.call(self.teacher, 'POST', self.endpoint,
                         {'title': '重放新标题', 'replay_of': snapshot_id}, status).json

    def test_draft_exact_scores_and_replay_after_new_facts_versions_backup(self):
        questions = [self.create(practice_available=True) for _ in range(3)]
        first = self.generate(count=3, difficulty_counts={'easy': 3, 'medium': 0, 'hard': 0}).json['data']
        self.assertEqual(first['points_hundredths'], [334, 334, 333])
        detail = self.call(self.teacher, 'GET', f"/papers/{first['paper_id']}").json['data']
        self.assertEqual((detail['status'], detail['participant_count'], detail['start_at']), ('draft', 0, None))
        self.assertEqual(sum(round(q['points'] * 100) for q in detail['items']), 1001)
        self.call(self.student, 'GET', f"/papers/{first['paper_id']}", status=404)
        self.create()
        self.call(self.teacher, 'PATCH', f"/questions/{questions[0]['id']}", {'stem': 'new version'})
        response = self.student.post(f"/api/v1/questions/{questions[0]['id']}/practice-attempts", json={
            'question_version_id': questions[0]['version_id'], 'answer': 'A'}, headers={
                'Origin': ORIGIN, 'X-CSRF-Token': self.student.csrf, 'Idempotency-Key': str(uuid4())})
        self.assertEqual(response.status_code, 201, response.json)
        with (patch('backend.models.generation_input.freeze', side_effect=AssertionError('no new bank/history')),
              patch('backend.models.generation_input.np.random.Generator', side_effect=AssertionError('no RNG'))):
            replay = self.replay(first['generation_snapshot_id'])['data']
        for key in ('selected_version_ids', 'points_hundredths', 'coverage', 'seed', 'algorithm_version'):
            self.assertEqual(first[key], replay[key])
        self.assertNotEqual(first['paper_id'], replay['paper_id'])
        with closing(connect(self.path)) as db:
            hashes = [row[0] for row in db.execute('SELECT input_sha256 FROM generation_snapshot')]
            self.assertEqual(hashes, [hashes[0]] * 2)
            self.assertEqual(db.execute("SELECT count(*) FROM audit_event WHERE action='paper.generate'").fetchone()[0], 2)
            backup = self.path.with_name('backup.db')
            with closing(connect(backup)) as target:
                db.backup(target)
                self.assertEqual(target.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(target.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.app.config['DATABASE_PATH'] = str(backup)
        restored = self.replay(first['generation_snapshot_id'])['data']
        self.assertEqual(restored['selected_version_ids'], first['selected_version_ids'])
        self.assertEqual(restored['points_hundredths'], first['points_hundredths'])

    def test_strict_combinations_and_permissions_write_nothing(self):
        self.create()
        before = self.counts()
        for body in ({'title': 'x', 'replay_of': 1, **parameters()}, {'title': 'x', 'replay_of': None},
                     {'title': 'x', 'replay_of': True}, {'title': 'x'}, {'replay_of': 1},
                     {'title': ' ', **parameters()}, {'title': 'x', **parameters(), 'seed': '42'},
                     {'title': 'x', **parameters(), 'extra': 1}):
            self.call(self.teacher, 'POST', self.endpoint, body, 400)
        for client, status in ((self.student, 403), (self.outsider, 404), (self.admin, 404)):
            self.call(client, 'POST', self.endpoint, {'title': 'x', **parameters()}, status)
        self.call(self.teacher, 'POST', self.endpoint + '?x=1', {'title': 'x', **parameters()}, 400)
        response = self.teacher.post('/api/v1' + self.endpoint, json={'title': 'x', **parameters()})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.counts(), before)

    def test_replay_cross_course_missing_and_revoked(self):
        self.create()
        first = self.generate().json['data']
        other = self.call(self.admin, 'POST', '/courses', {'title': 'other', 'teacher_id': self.teacher_id}, 201).json['data']['id']
        self.call(self.teacher, 'POST', f'/courses/{other}/generated-papers',
                  {'title': 'x', 'replay_of': first['generation_snapshot_id']}, 404)
        self.replay(999, 404)
        # Explicit revocation fixture: responsible-teacher DELETE correctly refuses.
        with closing(connect(self.path)) as db:
            db.execute('UPDATE course_member SET active=0 WHERE course_id=? AND user_id=?',
                       (self.course_id, self.teacher_id))
        self.replay(first['generation_snapshot_id'], 404)

    def test_solver_outside_transaction_and_permission_revoked_before_save(self):
        self.create()
        original = generation_solver.solve
        before = self.counts()

        def revoke(snapshot):
            # A second real connection can write while search is running.
            with closing(connect(self.path)) as db:
                db.execute('PRAGMA busy_timeout=50')
                db.execute('UPDATE course_member SET active=0 WHERE course_id=? AND user_id=?',
                           (self.course_id, self.teacher_id))
            return original(snapshot)

        with patch('backend.models.generation_solver.solve', side_effect=revoke):
            self.generate(status=404)
        self.assertEqual(self.counts(), before)

    def test_session_revoked_during_search(self):
        self.create()
        original = generation_solver.solve
        before = self.counts()

        def revoke(snapshot):
            with closing(connect(self.path)) as db:
                db.execute('DELETE FROM session WHERE user_id=?', (self.teacher_id,))
            return original(snapshot)

        with patch('backend.models.generation_solver.solve', side_effect=revoke):
            self.generate(status=401)
        self.assertEqual(self.counts(), before)

    def test_current_confidential_eligibility_rechecked_and_replay_rejected_after_public(self):
        q = self.create()
        original = generation_solver.solve
        before = self.counts()

        def expose(snapshot):
            self.call(self.teacher, 'PATCH', f"/questions/{q['id']}", {'practice_available': True})
            return original(snapshot)

        with patch('backend.models.generation_solver.solve', side_effect=expose):
            self.assertEqual(self.generate(status=409, confidential=True).json['error']['code'], 'QUESTION_PUBLIC')
        self.assertEqual(self.counts()[:3], before[:3])
        private = self.create()
        first = self.generate(confidential=True).json['data']
        self.call(self.teacher, 'PATCH', f"/questions/{private['id']}", {'practice_available': True})
        before = self.counts()
        self.assertEqual(self.replay(first['generation_snapshot_id'], 409)['error']['code'], 'QUESTION_PUBLIC')
        self.assertEqual(self.counts(), before)

    def test_no_solution_and_real_budget_http_leave_no_drafts(self):
        before = self.counts()
        self.assertEqual(self.generate(status=422).json['error']['code'], 'INFEASIBLE_CONSTRAINTS')
        # Explicit SQL scale fixture, same proven hard instance as C08; real solver/HTTP.
        for k in range(3, 12):
            self.call(self.teacher, 'POST', '/chapters/1/knowledge-points',
                      {'title': str(k), 'content': 'c', 'published': True}, 201)
        before = self.counts()
        with closing(connect(self.path)) as db:
            for i in range(1, 34):
                db.execute('INSERT INTO question(id,course_id) VALUES(?,?)', (i, self.course_id))
                db.execute("INSERT INTO question_version(id,question_id,version,type,stem,options_json,answer_json,difficulty) "
                           "VALUES(?,?,1,'boolean','q','[]','true','easy')", (i, i))
                db.execute('INSERT INTO question_knowledge(question_version_id,knowledge_id) VALUES(?,?)', (i, (i - 1) % 11 + 1))
        response = self.generate(status=503, count=10, knowledge_ids=list(range(1, 12)),
                                 difficulty_counts={'easy': 10, 'medium': 0, 'hard': 0})
        self.assertEqual(response.json['error']['code'], 'SEARCH_LIMIT')
        self.assertEqual(response.json['error']['details']['search_nodes'], 100000)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.counts(), before)

    def test_failure_after_snapshot_paper_items_or_audit_rolls_back_everything(self):
        self.create()
        before = self.counts()
        for table in ('paper', 'paper_item', 'audit_event'):
            with closing(connect(self.path)) as db:
                db.execute(f"CREATE TRIGGER fail_save BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'injected'); END")
            try:
                self.generate(status=409)
                self.assertEqual(self.counts(), before)
            finally:
                with closing(connect(self.path)) as db:
                    db.execute('DROP TRIGGER fail_save')

    def test_migration_guards_and_existing_publication_paths(self):
        q = self.create()
        first = self.generate(kind='quiz', confidential=True).json['data']
        migrate(self.path)
        with closing(connect(self.path)) as db:
            for sql, values in (
                ('UPDATE paper SET generation_snapshot_id=NULL WHERE id=?', (first['paper_id'],)),
                ('UPDATE paper SET seed=0 WHERE id=?', (first['paper_id'],)),
                (('INSERT INTO paper(course_id,title,kind,confidential,seed,algorithm_version,generation_snapshot_id) '
                  "VALUES(?,'bad','exam',1,42,'paper-backtrack-v1',?)"), (self.course_id, first['generation_snapshot_id'])),
                (('INSERT INTO paper(course_id,title,kind,confidential,generation_snapshot_id) '
                  "VALUES(?,'bad','quiz',1,999)"), (self.course_id,))):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql, values)
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/quizzes', {
            'paper_id': first['paper_id'], 'start_at': '2026-10-13T10:00:00.000Z',
            'end_at': '2026-10-13T13:00:00.000Z', 'confidentiality_note': '确认未公开'}, 201)
        self.call(self.teacher, 'PATCH', f"/questions/{q['id']}", {'practice_available': True}, 409)
        normal = self.generate(confidential=False, status=409)
        self.assertEqual(normal.json['error']['code'], 'QUESTION_RESERVED')
        self.assertEqual(self.call(self.teacher, 'GET', f"/papers/{first['paper_id']}").json['data']['review_at'], None)

    def test_ordinary_generated_draft_still_requires_publication_checks(self):
        q = self.create()
        first = self.generate(confidential=True).json['data']
        self.call(self.teacher, 'PATCH', f"/questions/{q['id']}", {'practice_available': True})
        body = {'start_at': '2026-10-13T10:00:00.000Z', 'end_at': '2026-10-13T13:00:00.000Z',
                'review_at': '2026-10-13T14:00:00.000Z', 'confidentiality_note': '确认'}
        self.call(self.teacher, 'POST', f"/papers/{first['paper_id']}/publish", body, 409)
        detail = self.call(self.teacher, 'GET', f"/papers/{first['paper_id']}").json['data']
        self.assertEqual((detail['status'], detail['participant_count']), ('draft', 0))
