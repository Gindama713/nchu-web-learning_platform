"""C02b real SPEC-001/005/006 knowledge, paper and publication API tests."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime

from backend.models.paper import CHECKSUM, VERSION, find, publish
from backend.shared.db import connect, migrate, write
from tests.test_question_validation import question
from tests.test_questions import QuestionApiBase

START = '2026-10-13T13:00:00.000Z'
END = '2026-10-13T14:00:00.000Z'
REVIEW = '2026-10-13T15:00:00.000Z'
WINDOW = {'start_at': START, 'end_at': END, 'review_at': REVIEW}


class RealPaperApiTest(QuestionApiBase):
    def test_real_empty_lists_permissions_and_missing_knowledge_tag(self):
        path = f'/courses/{self.course_id}/papers'
        for client in (self.teacher, self.student):
            response = self.call(client, 'GET', path)
            self.assertEqual(response.json['data'], [])
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.call(self.outsider, 'GET', path, status=404)
        self.call(self.student, 'POST', path, {'title': 'x', 'kind': 'exam', 'items': []}, 403)
        self.call(self.teacher, 'POST', self.url, question(), 400)
        self.call(self.teacher, 'POST', path, {'title': 'x', 'kind': 'exam',
                                            'items': [{'question_version_id': 1, 'points': 1}]}, 400)
        self.call(self.app.test_client(), 'GET', path, status=401)
        self.call(self.teacher, 'GET', '/papers/999', status=404)

    def test_real_migration_replay_checksum_and_backup(self):
        migrate(self.path)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT checksum FROM schema_migration WHERE version=?',
                                        (VERSION,)).fetchone()[0], CHECKSUM)
            with closing(connect(self.temporary.name + '/backup.db')) as target:
                db.backup(target)
                self.assertEqual(target.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(target.execute('PRAGMA foreign_key_check').fetchall(), [])
            db.execute("UPDATE schema_migration SET checksum='bad' WHERE version=?", (VERSION,))
        self.call(self.teacher, 'GET', f'/courses/{self.course_id}/papers', status=503)
        with self.assertRaises(RuntimeError):
            migrate(self.path)


class KnowledgeFixturePaperTest(QuestionApiBase):
    def setUp(self):
        super().setUp()
        self.knowledge_fixture()
        self.papers = f'/courses/{self.course_id}/papers'
        self.q = self.create_question()

    def create_question(self, **values):
        return self.call(self.teacher, 'POST', self.url, question(**values), 201).json['data']

    def draft(self, questions=None, **values):
        items = [{'question_version_id': q['version_id'], 'points': 10.01} for q in questions or [self.q]]
        return self.call(self.teacher, 'POST', self.papers,
                         {'title': 'CPU卷', 'kind': 'exam', 'items': items, **values}, 201).json['data']

    def publish(self, item, status=200, **values):
        return self.call(self.teacher, 'POST', f"/papers/{item['id']}/publish",
                         {**WINDOW, 'confidentiality_note': '确认未公开且非简单复制', **values}, status)

    def at(self, hour):
        self.app.config['TEST_NOW'] = datetime(2026, 10, 13, hour, tzinfo=UTC)
        self.login(self.teacher, 'T006TEACH')
        self.login(self.student, 'T006STUD1')

    def test_fixed_old_version_positions_and_integer_totals(self):
        newer = self.call(self.teacher, 'PATCH', f"/questions/{self.q['id']}", {'stem': 'v2', 'answer': 'B'}).json['data']
        second = self.create_question(type='boolean', options=[], answer=True)
        item = self.draft([self.q, second])
        self.assertEqual(item['total_points'], 20.02)
        self.assertEqual([q['position'] for q in item['items']], [1, 2])
        self.assertEqual(item['items'][0]['question_version_id'], self.q['version_id'])
        self.assertEqual(item['items'][0]['answer'], 'A')
        self.assertNotEqual(item['items'][0]['question_version_id'], newer['version_id'])
        self.publish(item)
        with closing(connect(self.path)) as db:
            self.assertEqual([r[0] for r in db.execute('SELECT points_hundredths FROM paper_item ORDER BY position')], [1001, 1001])

    def test_invalid_draft_is_atomic_and_same_identity_cannot_repeat(self):
        v2 = self.call(self.teacher, 'PATCH', f"/questions/{self.q['id']}", {'stem': 'v2'}).json['data']
        items = [{'question_version_id': self.q['version_id'], 'points': 1},
                 {'question_version_id': v2['version_id'], 'points': 1}]
        self.call(self.teacher, 'POST', self.papers, {'title': 'x', 'kind': 'exam', 'items': items}, 400)
        for value in (True, '1', 0, -1, 0.001, 1.111, 1e100, None):
            self.call(self.teacher, 'POST', self.papers, {'title': 'x', 'kind': 'exam',
                      'items': [{'question_version_id': self.q['version_id'], 'points': value}]}, 400)
        for payload in ({'title': '', 'kind': 'exam', 'items': items[:1]},
                        {'title': 'x', 'kind': 'practice', 'items': items[:1]},
                        {'title': 'x', 'kind': 'exam', 'items': []},
                        {'title': 'x', 'kind': 'exam', 'items': items[:1], 'confidential': 1},
                        {'title': 'x', 'kind': 'exam', 'items': items[:1], 'status': 'published'},
                        {'title': 'x', 'kind': 'exam', 'items': [{'question_version_id': 999, 'points': 1}]}):
            self.call(self.teacher, 'POST', self.papers, payload, 400)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM paper').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM audit_event WHERE action='paper.create'").fetchone()[0], 0)
        item = self.draft()
        with closing(connect(self.path)) as db:
            other = self.call(self.admin, 'POST', '/courses', {'title': 'other', 'teacher_id': self.teacher_id}, 201).json['data']['id']
            db.execute('INSERT INTO question(id,course_id) VALUES(99,?)', (other,))
            db.execute("INSERT INTO question_version(id,question_id,version,type,stem,options_json,answer_json,difficulty) "
                       "VALUES(99,99,1,'boolean','cross','[]','true','easy')")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('INSERT INTO paper_item VALUES(?,99,99,2,100)', (item['id'],))
        self.call(self.teacher, 'POST', self.papers, {'title': 'x', 'kind': 'exam',
                  'items': [{'question_version_id': 99, 'points': 1}]}, 400)

    def test_publication_validation_and_quiz_route_boundary(self):
        item = self.draft()
        for values in ({'review_at': None}, {'review_at': '2026-10-13T13:30:00Z'},
                       {'end_at': START}, {'start_at': '2026-10-13T13:00:00'},
                       {'start_at': '2026-10-13T13:00:00.000001Z'}, {'confidentiality_note': ''},
                       {'participant_ids': [self.student_id]}):
            self.publish(item, 400, **values)
        self.call(self.teacher, 'POST', f"/papers/{item['id']}/publish", {'start_at': START, 'end_at': END}, 400)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM paper_participant').fetchone()[0], 0)
        self.publish(item, start_at='2026-10-13T21:00:00+08:00')
        self.publish(item, 409)
        quiz = self.draft([self.create_question()], kind='quiz')
        self.publish(quiz, review_at=None, status=400)
        self.publish(quiz)
        self.assertEqual(self.call(self.teacher, 'GET', f"/papers/{quiz['id']}").json['data']['review_at'], REVIEW)

    def test_frozen_roster_current_access_and_prestart_metadata(self):
        item = self.draft()
        self.call(self.student, 'GET', f"/papers/{item['id']}", status=404)
        self.publish(item)
        for response in (self.call(self.student, 'GET', f"/papers/{item['id']}"),
                         self.call(self.student, 'GET', self.papers)):
            value = response.json['data']
            value = value[0] if isinstance(value, list) else value
            self.assertEqual(value['window_state'], 'upcoming')
            self.assertNotIn('items', value)
            self.assertNotIn('confidentiality_note', value)
            self.assertNotIn('participant_count', value)
        late_id = self.outsider.get('/api/v1/auth/session').json['data']['user']['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members', {'user_id': late_id, 'member_role': 'student'}, 201)
        self.assertEqual(self.call(self.outsider, 'GET', self.papers).json['total'], 0)
        self.call(self.outsider, 'GET', f"/papers/{item['id']}", status=404)
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{self.student_id}', status=204)
        self.call(self.student, 'GET', self.papers, status=404)
        self.call(self.student, 'GET', f"/papers/{item['id']}", status=404)
        self.assertEqual(self.call(self.teacher, 'GET', f"/papers/{item['id']}").json['data']['participant_count'], 1)
        with closing(connect(self.path)) as db:
            self.assertEqual([r[0] for r in db.execute('SELECT student_id FROM paper_participant')], [self.student_id])

    def test_exact_window_review_boundary_and_history_eligibility(self):
        item = self.draft()
        self.publish(item)
        for hour, state in ((13, 'open'), (14, 'closed')):
            self.at(hour)
            detail = self.call(self.student, 'GET', f"/papers/{item['id']}").json['data']
            self.assertEqual(detail['window_state'], state)
            self.assertNotIn('answer', detail['items'][0])
            self.assertNotIn('explanation', detail['items'][0])
            self.call(self.teacher, 'PATCH', f"/questions/{self.q['id']}", {'practice_available': True}, 409)
        shared = self.draft(kind='homework')
        self.publish(shared, 409)
        self.at(15)
        self.assertEqual(self.call(self.student, 'GET', f"/papers/{item['id']}").json['data']['items'][0]['answer'], 'A')
        self.call(self.teacher, 'PATCH', f"/questions/{self.q['id']}", {'practice_available': True})
        secret = self.draft()
        response = self.publish(secret, 409)
        self.assertEqual(response.json['error']['code'], 'QUESTION_PUBLIC')

    def test_public_old_identity_and_started_papers_never_regain_secrecy(self):
        public = self.create_question(practice_available=True)
        private = self.call(self.teacher, 'PATCH', f"/questions/{public['id']}", {'practice_available': False}).json['data']
        self.publish(self.draft([private]), 409)
        prior = self.draft(confidential=False)
        self.publish(prior)
        other = self.draft()
        self.publish(other, 409)  # Confidential publication cannot share protected ordinary paper.
        self.at(15)
        response = self.publish(other, 409)
        self.assertEqual(response.json['error']['code'], 'QUESTION_PUBLIC')
        # No async flag is needed: the earlier published paper is the source of history.
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT ever_public FROM question WHERE id=?', (self.q['id'],)).fetchone()[0], 0)
        self.publish(self.draft(kind='homework'), review_at=REVIEW)

    def test_publish_and_practice_race_has_only_one_winner(self):
        item = self.draft()
        cookie = self.teacher.get_cookie('cpu_session').value
        def operation(which):
            client = self.app.test_client()
            client.set_cookie('cpu_session', cookie)
            client.csrf = self.teacher.csrf
            path, body = (f"/papers/{item['id']}/publish", {**WINDOW, 'confidentiality_note': '未公开'}) if which == 0 else (
                f"/questions/{self.q['id']}", {'practice_available': True})
            return client.open('/api/v1'+path, method='POST' if which == 0 else 'PATCH', json=body,
                               headers={'Origin': self.app.config['APP_ORIGIN'], 'X-CSRF-Token': client.csrf}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(operation, (0, 1))), [200, 409])
        with closing(connect(self.path)) as db:
            published = db.execute("SELECT status='published' FROM paper WHERE id=?", (item['id'],)).fetchone()[0]
            opened = db.execute('SELECT ever_public FROM question WHERE id=?', (self.q['id'],)).fetchone()[0]
            self.assertEqual(published + opened, 1)

    def test_two_confidential_publications_race_has_only_one_winner(self):
        first, second = self.draft(), self.draft()
        def operation(item):
            client = self.app.test_client()
            client.set_cookie('cpu_session', self.teacher.get_cookie('cpu_session').value)
            return client.post(f"/api/v1/papers/{item['id']}/publish", json={**WINDOW, 'confidentiality_note': '未公开'},
                               headers={'Origin': self.app.config['APP_ORIGIN'], 'X-CSRF-Token': self.teacher.csrf}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(operation, (first, second))), [200, 409])
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM paper_participant').fetchone()[0], 1)

    def test_publication_failed_roster_insert_rolls_back_and_database_freezes(self):
        item = self.draft()
        with closing(connect(self.path)) as db:
            db.executescript("CREATE TRIGGER fail_roster BEFORE INSERT ON paper_participant BEGIN SELECT RAISE(ABORT,'test'); END;")
        self.publish(item, 409)
        self.assertEqual(self.call(self.teacher, 'GET', f"/papers/{item['id']}").json['data']['status'], 'draft')
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit_event WHERE action='paper.publish'").fetchone()[0], 0)
            db.execute('DROP TRIGGER fail_roster')
        self.publish(item)
        with closing(connect(self.path)) as db:
            for sql in ("UPDATE paper SET title='x' WHERE id=?", 'DELETE FROM paper WHERE id=?',
                        'UPDATE paper_item SET points_hundredths=1 WHERE paper_id=?', 'DELETE FROM paper_item WHERE paper_id=?',
                        'UPDATE paper_participant SET student_id=99 WHERE paper_id=?', 'DELETE FROM paper_participant WHERE paper_id=?',
                        'INSERT INTO paper_item VALUES(?,999,999,2,100)', 'INSERT INTO paper_participant VALUES(?,999)'):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql, (item['id'],))
            with closing(connect(self.temporary.name + '/populated-backup.db')) as target:
                db.backup(target)
                self.assertEqual(target.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(target.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(target.execute('SELECT status FROM paper').fetchone()[0], 'published')

    def test_shared_quiz_service_keeps_null_review_reserved_after_deadline(self):
        item = self.draft(kind='quiz', confidential=True)
        with self.app.test_request_context(), write() as db:
            publish(db, find(db, item['id']), {'start_at': START, 'end_at': END, 'confidentiality_note': '未公开'}, quiz=True)
        self.at(15)
        self.assertNotIn('answer', self.call(self.student, 'GET', f"/papers/{item['id']}").json['data']['items'][0])
        self.call(self.teacher, 'PATCH', f"/questions/{self.q['id']}", {'practice_available': True}, 409)
        self.publish(self.draft(kind='homework'), 409)

    def test_filters_csrf_revocation_and_published_permissions(self):
        draft = self.draft(kind='homework')
        self.publish(self.draft([self.create_question()]))
        response = self.call(self.teacher, 'GET', self.papers+'?kind=homework&status=draft&page_size=1').json
        self.assertEqual(response['total'], 1)
        self.assertEqual(response['data'][0]['id'], draft['id'])
        for query in ('?kind=x', '?status=open', '?page=0', '?page_size=101', '?kind=exam&kind=quiz', '?x=1', '?page=9223372036854775807'):
            self.call(self.teacher, 'GET', self.papers+query, status=400)
        self.call(self.student, 'POST', f"/papers/{draft['id']}/publish", WINDOW, 403)
        self.call(self.outsider, 'POST', f"/papers/{draft['id']}/publish", WINDOW, 404)
        self.assertEqual(self.teacher.post('/api/v1'+self.papers, json={}).status_code, 403)
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{self.student_id}', status=204)
        self.call(self.admin, 'PATCH', f'/users/{self.student_id}', {'active': False})
        self.call(self.student, 'GET', self.papers, status=401)
