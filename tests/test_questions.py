"""Real SPEC-001/paper API tests, plus an explicitly isolated knowledge schema fixture.

FixtureVersionTest does NOT certify integration with unmerged SPEC-005.
"""

import secrets
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.models.question import CHECKSUM, VERSION
from backend.shared.db import connect, migrate
from tests.test_question_validation import question

ORIGIN = 'http://127.0.0.1:5173'


class QuestionApiBase(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'question.db'
        migrate(self.path)
        self.password = secrets.token_urlsafe(24)
        self.app = create_app({'TESTING': True, 'DATABASE_PATH': str(self.path),
                               'SECRET_KEY': secrets.token_hex(32), 'APP_ORIGIN': ORIGIN,
                               'TEST_NOW': datetime(2026, 10, 13, 12, tzinfo=UTC)})
        with closing(connect(self.path)) as db:
            for number, role in (('T006ADMIN', 'admin'), ('T006TEACH', 'teacher')):
                db.execute('INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) '
                           'VALUES(?,?,?,?,1,?,?)', (number, number, generate_password_hash(self.password), role,
                                                    '2026-10-13T00:00:00Z', '2026-10-13T00:00:00Z'))
        self.admin, self.teacher, self.student, self.outsider = [self.app.test_client() for _ in range(4)]
        self.login(self.admin, 'T006ADMIN')
        self.login(self.teacher, 'T006TEACH')
        for client, number in ((self.student, 'T006STUD1'), (self.outsider, 'T006STUD2')):
            self.call(client, 'POST', '/auth/register',
                      {'student_no': number, 'name': number, 'password': self.password}, 201)
            self.login(client, number)
        self.teacher_id = self.teacher.get('/api/v1/auth/session').json['data']['user']['id']
        self.student_id = self.student.get('/api/v1/auth/session').json['data']['user']['id']
        self.course_id = self.call(self.admin, 'POST', '/courses',
                                   {'title': 'C02a CPU', 'teacher_id': self.teacher_id}, 201).json['data']['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members',
                  {'user_id': self.student_id, 'member_role': 'student'}, 201)
        self.url = f'/courses/{self.course_id}/questions'

    def call(self, client, method, path, data=None, status=200):
        response = client.open('/api/v1' + path, method=method, json=data,
                               headers={'Origin': ORIGIN, 'X-CSRF-Token': getattr(client, 'csrf', '')})
        self.assertEqual(response.status_code, status, response.json)
        return response

    def login(self, client, number):
        data = self.call(client, 'POST', '/auth/login',
                         {'student_no': number, 'password': self.password}).json['data']
        client.csrf = data['csrf_token']

    def knowledge_fixture(self):
        with closing(connect(self.path)) as db:
            # Minimal DBD shape for isolated tests only. Not SPEC-005 implementation/migration.
            db.executescript('CREATE TABLE chapter(id INTEGER PRIMARY KEY,course_id INTEGER REFERENCES course(id));'
                             'CREATE TABLE knowledge_point(id INTEGER PRIMARY KEY,chapter_id INTEGER REFERENCES chapter(id));')
            db.execute('INSERT INTO chapter VALUES(1,?)', (self.course_id,))
            db.execute('INSERT INTO knowledge_point VALUES(1,1)')
            db.execute('INSERT INTO knowledge_point VALUES(2,1)')

class RealQuestionApiTest(QuestionApiBase):
    def test_real_auth_empty_list_missing_knowledge_rejects_without_partial_write(self):
        result = self.call(self.teacher, 'GET', self.url)
        self.assertEqual(result.json['data'], [])
        self.assertEqual(result.json['total'], 0)
        self.assertEqual(result.headers['Cache-Control'], 'no-store')
        self.call(self.student, 'GET', self.url)
        response = self.call(self.teacher, 'POST', self.url, question(), 503)
        self.assertEqual(response.json['error']['code'], 'DEPENDENCY_UNAVAILABLE')
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM question').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM question_version').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM audit_event WHERE action='question.create'").fetchone()[0], 0)

    def test_real_permissions_csrf_origin_revocation_and_strict_request(self):
        self.call(self.outsider, 'GET', self.url, status=404)
        self.call(self.admin, 'GET', self.url, status=404)
        self.call(self.student, 'POST', self.url, question(), 403)
        for headers in ({'Origin': ORIGIN}, {'Origin': 'https://foreign.example', 'X-CSRF-Token': self.teacher.csrf}):
            response = self.teacher.post('/api/v1'+self.url, json=question(), headers=headers)
            self.assertEqual(response.status_code, 403)
        self.call(self.teacher, 'POST', self.url, question(answer=True), 400)
        self.call(self.teacher, 'POST', self.url+'?page=1', question(), 400)
        for suffix in ('?page=0', '?page=1&page=2', '?page_size=101', '?page=9223372036854775808',
                       '?page=9223372036854775807', '?knowledge_id=true', '?type=invalid', '?x=1'):
            self.call(self.teacher, 'GET', self.url+suffix, status=400)
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{self.student_id}', status=204)
        self.call(self.student, 'GET', self.url, status=404)
        self.call(self.admin, 'PATCH', f'/users/{self.student_id}', {'active': False})
        self.call(self.student, 'GET', self.url, status=401)

    def test_real_migration_replay_checksum_and_backup(self):
        migrate(self.path)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT checksum FROM schema_migration WHERE version=?', (VERSION,)).fetchone()[0], CHECKSUM)
            backup = Path(self.temporary.name) / 'backup.db'
            with closing(connect(backup)) as target:
                db.backup(target)
                self.assertEqual(target.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(target.execute('PRAGMA foreign_key_check').fetchall(), [])
            db.execute("UPDATE schema_migration SET checksum='bad' WHERE version=?", (VERSION,))
        with self.assertRaises(RuntimeError):
            migrate(self.path)
        self.call(self.teacher, 'GET', self.url, status=503)


class FixtureVersionTest(QuestionApiBase):
    def setUp(self):
        super().setUp()
        self.knowledge_fixture()

    def create(self, **values):
        return self.call(self.teacher, 'POST', self.url, question(**values), 201).json['data']

    def test_new_version_retains_old_answers_tags_and_rejects_overwrite(self):
        old = self.create(knowledge_ids=[1, 2])
        updated = self.call(self.teacher, 'PATCH', f"/questions/{old['id']}",
                            {'answer': 'B', 'knowledge_ids': [2]}).json['data']
        self.assertEqual(updated['id'], old['id'])
        self.assertEqual(updated['version'], 2)
        self.assertNotEqual(updated['version_id'], old['version_id'])
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT answer_json FROM question_version WHERE id=?',
                                        (old['version_id'],)).fetchone()[0], '"A"')
            self.assertEqual([row[0] for row in db.execute('SELECT knowledge_id FROM question_knowledge '
                              'WHERE question_version_id=? ORDER BY knowledge_id', (old['version_id'],))], [1, 2])
            for sql in ('UPDATE question_version SET stem=\'overwrite\' WHERE id=?',
                        'DELETE FROM question_version WHERE id=?',
                        'UPDATE question_knowledge SET knowledge_id=99 WHERE question_version_id=?',
                        'DELETE FROM question_knowledge WHERE question_version_id=?'):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql, (old['version_id'],))
        self.assertEqual(self.call(self.teacher, 'GET', self.url).json['data'][0], updated)
        self.call(self.teacher, 'PATCH', f"/questions/{old['id']}", {}, 400)
        self.assertEqual(self.call(self.student, 'GET', self.url).json['total'], 0)

    def test_same_course_validation_and_failed_insert_roll_back(self):
        other_course = self.call(self.admin, 'POST', '/courses',
                                 {'title': 'other', 'teacher_id': self.teacher_id}, 201).json['data']['id']
        with closing(connect(self.path)) as db:
            db.execute('INSERT INTO chapter VALUES(2,?)', (other_course,))
            db.execute('INSERT INTO knowledge_point VALUES(3,2)')
            db.executescript("CREATE TRIGGER fail_version BEFORE INSERT ON question_version "
                             "WHEN NEW.stem='fail' BEGIN SELECT RAISE(ABORT,'fixture failure'); END;")
        self.call(self.teacher, 'POST', self.url, question(knowledge_ids=[1, 3]), 400)
        self.call(self.teacher, 'POST', self.url, question(knowledge_ids=[99]), 400)
        self.call(self.teacher, 'POST', self.url, question(stem='fail'), 409)
        self.assertEqual(self.call(self.teacher, 'GET', self.url).json['total'], 0)
        item = self.create()
        self.call(self.outsider, 'PATCH', f"/questions/{item['id']}", {'stem': 'steal'}, 404)
        self.call(self.student, 'PATCH', f"/questions/{item['id']}", {'stem': 'steal'}, 403)
        self.call(self.teacher, 'PATCH', f"/questions/{item['id']}", {'knowledge_ids': [3]}, 400)

    def test_opening_uses_real_paper_guard_and_public_history_is_monotonic(self):
        item = self.create()
        opened = self.call(self.teacher, 'PATCH', f"/questions/{item['id']}", {'practice_available': True}).json['data']
        student_item = self.call(self.student, 'GET', self.url).json['data'][0]
        self.assertEqual(student_item['version_id'], opened['version_id'])
        self.assertNotIn('answer', student_item)
        self.assertNotIn('explanation', student_item)
        self.call(self.teacher, 'PATCH', f"/questions/{item['id']}", {'practice_available': False})
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT ever_public FROM question WHERE id=?', (item['id'],)).fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('UPDATE question SET ever_public=0 WHERE id=?', (item['id'],))

    def test_reserved_identity_blocks_all_versions_and_abnormal_public_list(self):
        item = self.create(practice_available=True)
        self.call(self.teacher, 'PATCH', f"/questions/{item['id']}", {'stem': 'v2'})
        with closing(connect(self.path)) as db:
            # Deliberately abnormal historical data bypasses API public eligibility.
            db.execute("INSERT INTO paper(id,course_id,title,kind,confidential) VALUES(1,?,'legacy','quiz',1)",
                       (self.course_id,))
            db.execute('INSERT INTO paper_item VALUES(1,?,?,1,100)', (item['version_id'], item['id']))
            db.execute("UPDATE paper SET status='published',start_at='2026-10-13T10:00:00.000Z',"
                       "end_at='2026-10-13T11:00:00.000Z',confidentiality_note='legacy anomaly' WHERE id=1")
        self.call(self.teacher, 'PATCH', f"/questions/{item['id']}", {'practice_available': True}, 409)
        response = self.call(self.student, 'GET', self.url, status=409)
        self.assertEqual(response.json['error']['code'], 'QUESTION_RESERVED')
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM question_version').fetchone()[0], 2)
            db.execute("UPDATE paper SET review_at='2026-10-13T12:00:00.000Z'")
        self.assertEqual(self.call(self.student, 'GET', self.url).json['total'], 1)

    def test_filters_pagination_and_concurrent_edits_preserve_each_version(self):
        item = self.create()
        self.create(type='numeric', options=[], answer=8, difficulty='hard', knowledge_ids=[2])
        self.assertEqual(self.call(self.teacher, 'GET', self.url+'?type=numeric&difficulty=hard&knowledge_id=2').json['total'], 1)
        result = self.call(self.teacher, 'GET', self.url+'?page=99&page_size=1').json
        self.assertEqual(result['data'], [])
        self.assertEqual(result['total'], 2)
        def edit(stem):
            client = self.app.test_client()
            client.set_cookie('cpu_session', self.teacher.get_cookie('cpu_session').value)
            client.csrf = self.teacher.csrf
            return self.call(client, 'PATCH', f"/questions/{item['id']}", {'stem': stem}).json['data']['version']
        with ThreadPoolExecutor(max_workers=2) as pool:
            versions = list(pool.map(edit, ('v2', 'v3')))
        self.assertEqual(sorted(versions), [2, 3])
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM question_version WHERE question_id=?', (item['id'],)).fetchone()[0], 3)
