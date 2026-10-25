"""C08 persisted evidence/backup/rollback, distinct from C09 HTTP acceptance."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

from backend.models import generation_snapshot as store
from backend.models.generation_input import freeze
from backend.models.generation_solver import solve
from backend.shared.api import ApiError
from backend.shared.db import connect, migrate
from tests.test_generation_input import UNTIL, parameters
from tests.test_question_validation import question
from tests.test_questions import ORIGIN, QuestionApiBase


class GenerationSnapshotTest(QuestionApiBase):
    def setUp(self):
        super().setUp()
        self.knowledge_fixture()
        self.q = self.create(practice_available=True)
        self.other = self.create()

    def create(self, **values):
        return self.call(self.teacher, 'POST', self.url, question(**values), 201).json['data']

    def practice(self, value):
        response = self.student.post(f"/api/v1/questions/{self.q['id']}/practice-attempts", json={
            'question_version_id': self.q['version_id'], 'answer': value}, headers={
                'Origin': ORIGIN, 'X-CSRF-Token': self.student.csrf, 'Idempotency-Key': str(uuid4())})
        self.assertEqual(response.status_code, 201, response.json)

    def test_saved_all_candidates_recalculate_after_new_questions_versions_and_answers_and_backup(self):
        self.practice('A')
        with closing(connect(self.path)) as db:
            frozen = freeze(db, self.course_id, parameters(), source_until=UNTIL)
            original = solve(frozen)
            with self.assertRaises(RuntimeError):
                store.save(db, frozen, original)
            db.execute('BEGIN IMMEDIATE')
            snapshot_id = store.save(db, frozen, original)
            db.commit()
            self.assertEqual(len(frozen.candidates), 2)
            self.call(self.teacher, 'PATCH', f"/questions/{self.q['id']}", {'stem': 'new version'})
            self.create()
            self.practice('B')
            current = freeze(db, self.course_id, parameters(), source_until=UNTIL)
            self.assertNotEqual(current.input_sha256, frozen.input_sha256)
            with patch('backend.models.generation_input.np.random.Generator', side_effect=AssertionError('no RNG')):
                self.assertEqual(store.replay(db, snapshot_id, self.course_id), (frozen, original))
            backup_path = self.temporary.name + '/backup.db'
            with closing(connect(backup_path)) as backup:
                db.backup(backup)
                migrate(backup_path)
                self.assertEqual(backup.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(backup.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(store.replay(backup, snapshot_id, self.course_id), (frozen, original))
            self.assertEqual(db.execute('SELECT count(*) FROM paper').fetchone()[0], 0)
            with self.assertRaises(ApiError) as caught:
                store.load(db, snapshot_id, self.course_id + 1)
            self.assertEqual(caught.exception.status, 404)

    def test_transaction_failure_rolls_back_and_table_is_immutable(self):
        with closing(connect(self.path)) as db:
            frozen = freeze(db, self.course_id, parameters(), source_until=UNTIL)
            result = solve(frozen)
            db.execute('BEGIN IMMEDIATE')
            store.save(db, frozen, result)
            db.rollback()  # C09's subsequent paper/audit failure must roll back snapshot too.
            self.assertEqual(db.execute('SELECT count(*) FROM generation_snapshot').fetchone()[0], 0)
            db.execute('BEGIN IMMEDIATE')
            store.save(db, frozen, result)
            db.commit()
            for statement in ("UPDATE generation_snapshot SET seed=1", 'DELETE FROM generation_snapshot'):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(statement)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM question_version WHERE id=?', (self.q['version_id'],))

    def test_version_course_guards_and_migration_checksum(self):
        with closing(connect(self.path)) as db:
            frozen = freeze(db, self.course_id, parameters(), source_until=UNTIL)
            result = solve(frozen)
            invalid = replace(frozen, course_id=self.course_id + 1)
            db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(ApiError) as caught:
                store.save(db, invalid, result)
            self.assertEqual(caught.exception.status, 422)
            db.rollback()
            db.execute('BEGIN IMMEDIATE')
            snapshot_id = store.save(db, frozen, result)
            db.commit()
            other_course = self.call(self.admin, 'POST', '/courses', {'title': 'other', 'teacher_id': self.teacher_id}, 201).json['data']['id']
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('INSERT INTO generation_snapshot(course_id,seed,algorithm_version,parameters_json,candidates_json,'
                           'history_json,source_until,input_sha256,selected_ids_json) '
                           'SELECT ?,seed,algorithm_version,parameters_json,candidates_json,history_json,source_until,input_sha256,'
                           'selected_ids_json FROM generation_snapshot WHERE id=?', (other_course, snapshot_id))
            migrate(self.path)
            self.assertEqual(db.execute('SELECT checksum FROM schema_migration WHERE version=?', (store.VERSION,)).fetchone()[0], store.CHECKSUM)
            db.execute("UPDATE schema_migration SET checksum='bad' WHERE version=?", (store.VERSION,))
            with self.assertRaises(ApiError) as caught:
                store.load(db, snapshot_id, self.course_id)
            self.assertEqual(caught.exception.code, 'MAINTENANCE')
            with self.assertRaises(RuntimeError):
                migrate(self.path)

    def test_read_transaction_freezes_concurrent_version_and_history_changes(self):
        self.practice('A')
        with closing(connect(self.path)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            test = self

            class InterleavedReader:
                changed = False

                @property
                def in_transaction(self):
                    return db.in_transaction

                def execute(self, sql, args=()):
                    if sql.startswith('SELECT v.*') and not self.changed:
                        self.changed = True
                        test.call(test.teacher, 'PATCH', f"/questions/{test.q['id']}", {'stem': 'concurrent v2'})
                        test.practice('B')
                    return db.execute(sql, args)

                def rollback(self):
                    db.rollback()

            reader = InterleavedReader()
            frozen = freeze(reader, self.course_id, parameters(), source_until=UNTIL)
            self.assertTrue(reader.changed)
            old = next(r for r in frozen.candidates if r.question_id == self.q['id'])
            self.assertEqual((old.version_id, old.correct_count, old.sample_size), (self.q['version_id'], 1, 1))
            current = freeze(db, self.course_id, parameters(), source_until=UNTIL)
            new = next(r for r in current.candidates if r.question_id == self.q['id'])
            self.assertNotEqual(new.version_id, old.version_id)
            self.assertEqual(new.sample_size, 0)
            self.assertFalse(db.in_transaction)
