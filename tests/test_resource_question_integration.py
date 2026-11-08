"""R01 only: real 003 upload/import -> 006/008 -> 004 protection seams."""

import hashlib
import json
import os
from contextlib import closing
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from backend.shared.db import connect
from tests.test_questions import ORIGIN, QuestionApiBase


def bank(knowledge_id, **updates):
    return {'type': 'boolean', 'stem': 'R01 PC保存指令地址？', 'options': [],
            'answer': True, 'explanation': 'R01_SECRET_EXPLANATION', 'difficulty': 'easy',
            'knowledge_ids': [knowledge_id], **updates}


def facts(path):
    with closing(connect(path)) as db:
        tables = ('question', 'question_version', 'question_knowledge', 'question_import',
                  'idempotency_record', 'audit_event', 'resource_event', 'preparation',
                  'preparation_resource', 'preparation_quiz', 'paper', 'paper_participant', 'attempt', 'answer')
        result = {'counts': {t: db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in tables}}
        for name, sql in {
            'imports': 'SELECT id,resource_version_id,actor_id,count FROM question_import ORDER BY id',
            'resources': 'SELECT id,kind,visibility FROM resource ORDER BY id',
            'versions': 'SELECT id,resource_id,version,file_id FROM resource_version ORDER BY id',
            'papers': 'SELECT id,status,start_at,end_at,review_at FROM paper ORDER BY id',
            'preparations': 'SELECT id,status FROM preparation ORDER BY id',
            'audit': 'SELECT id,action,object_type,object_id FROM audit_event ORDER BY id',
            'idempotency': 'SELECT operation,resource_type,resource_id,response_status FROM idempotency_record ORDER BY id',
        }.items():
            result[name] = [dict(r) for r in db.execute(sql)]
        result['foreign_key_check'] = [list(r) for r in db.execute('PRAGMA foreign_key_check')]
        return result


class ResourceQuestionSeamTest(QuestionApiBase):
    def setUp(self):
        self.requests, self.checkpoints = [], []
        super().setUp()
        self.app.config['UPLOAD_ROOT'] = str(Path(self.temporary.name)/'uploads')
        self.addCleanup(self.report)
        self.knowledge_fixture()

    def report(self):
        directory = os.environ.get('R01_EVIDENCE_DIR')
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
            payload = {'test': self._testMethodName, 'requests': self.requests,
                       'checkpoints': self.checkpoints, 'final_db': facts(self.path)}
            (Path(directory)/(self._testMethodName+'.json')).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

    def record(self, method, path, response):
        if not path.startswith('/auth/'):
            self.requests.append({'method': method, 'path': path, 'status': response.status_code,
                                  'body': response.get_json(silent=True),
                                  'bytes': len(response.data),
                                  'sha256': hashlib.sha256(response.data).hexdigest()})
        return response

    def call(self, client, method, path, data=None, status=200):
        response = client.open('/api/v1'+path, method=method, json=data,
                               headers={'Origin': ORIGIN, 'X-CSRF-Token': getattr(client, 'csrf', '')})
        self.record(method, path, response)
        self.assertEqual(response.status_code, status, response.json)
        return response

    def checkpoint(self, label):
        value = facts(self.path)
        self.checkpoints.append({'label': label, 'db': value})
        self.assertEqual(value['foreign_key_check'], [])
        return value

    def upload(self, items, resource_id=None, *, kind='question_bank'):
        content = json.dumps(items, ensure_ascii=False).encode() if kind == 'question_bank' else b'%PDF-1.4 R01'
        path = f'/resources/{resource_id}/versions' if resource_id else f'/courses/{self.course_id}/resources'
        data = {'file': (BytesIO(content), 'bank.json' if kind == 'question_bank' else 'guide.pdf',
                         'application/json' if kind == 'question_bank' else 'application/pdf')}
        if resource_id is None:
            data.update(title='R01源文件', kind=kind)
        response = self.teacher.post('/api/v1'+path, data=data,
            headers={'Origin': ORIGIN, 'X-CSRF-Token': self.teacher.csrf})
        self.record('POST multipart', path, response)
        self.assertEqual(response.status_code, 201, response.json)
        return response.json['data'], content

    def import_bank(self, resource, *, key=None, client=None, status=201):
        client = client or self.teacher
        path = f"/resources/{resource['resource_id']}/question-imports"
        response = client.post('/api/v1'+path, json={'resource_version_id': resource['id']},
            headers={'Origin': ORIGIN, 'X-CSRF-Token': getattr(client, 'csrf', ''),
                     'Idempotency-Key': key or str(uuid4())})
        self.record('POST', path, response)
        self.assertEqual(response.status_code, status, response.json)
        return response

    def prep(self, *, resources=None, questions=None, quizzes=None):
        return self.call(self.teacher, 'POST', f'/courses/{self.course_id}/preparations',
            {'title': 'R01备课', 'knowledge_ids': [1], 'resource_version_ids': resources or [],
             'question_version_ids': questions or [], 'quiz_ids': quizzes or []}, 201).json['data']

    def assert_secret_absent(self, data):
        if isinstance(data, dict):
            self.assertNotIn('answer', data)
            self.assertNotIn('explanation', data)
            for value in data.values():
                self.assert_secret_absent(value)
        elif isinstance(data, list):
            for value in data:
                self.assert_secret_absent(value)

    def test_r01_import_invalid_atomic_and_original_key_bytes(self):
        bad, _ = self.upload([bank(1), bank(1, answer='invalid')])
        before = self.checkpoint('before invalid second item')
        key = str(uuid4())
        rejected = self.import_bank(bad, key=key, status=400)
        self.assertIn('题目[1]', rejected.json['error']['message'])
        self.assertEqual(before, self.checkpoint('after invalid second item: no writes'))
        valid, _ = self.upload([bank(1), bank(2, stem='第二题')], bad['resource_id'])
        first = self.import_bank(valid, key=key)
        after = self.checkpoint('valid same previously rejected key')
        replay = self.import_bank(valid, key=key)
        self.assertEqual(first.data, replay.data)
        self.assertEqual(after, self.checkpoint('byte exact successful replay: no writes'))
        self.import_bank(bad, key=key, status=409)
        self.assertEqual(after, self.checkpoint('same key different version conflict'))
        self.assertEqual(after['counts']['question'], 2)
        self.assertEqual(after['counts']['question_version'], 2)
        self.assertEqual(after['counts']['question_import'], 1)
        self.assertEqual(after['counts']['idempotency_record'], 1)
        self.import_bank(valid, client=self.student, status=403)
        self.import_bank(valid, client=self.outsider, status=404)
        self.assertEqual(after, self.checkpoint('unauthorized imports: no writes'))

    def test_r01_all_source_versions_and_preparation_rejected(self):
        first, raw = self.upload([bank(1)])
        rid = first['resource_id']
        second, _ = self.upload([bank(1, stem='第二版')], rid)
        third, _ = self.upload([bank(1, stem='第三版')], rid)
        versions = [first['id'], second['id'], third['id']]
        self.assertEqual(len(self.call(self.teacher, 'GET', f'/resources/{rid}/versions').json['data']), 3)
        path = f"/resource-versions/{first['id']}/content?intent=download&event_id={uuid4()}"
        response = self.teacher.get('/api/v1'+path)
        self.record('GET', path, response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, raw)
        before = self.checkpoint('teacher old source download succeeded')
        for suffix in ('', '?kind=question_bank', '?q=R01'):
            data = self.call(self.student, 'GET', f'/courses/{self.course_id}/resources'+suffix).json['data']
            self.assertEqual(data, [])
        self.call(self.student, 'GET', f'/resources/{rid}/versions', status=404)
        for vid in versions:
            for method, intent, extra in [('GET', 'download', {}), ('GET', 'view', {}),
                                          ('HEAD', 'download', {}), ('GET', 'download', {'Range': 'bytes=0-20'})]:
                path = f'/resource-versions/{vid}/content?intent={intent}&event_id={uuid4()}'
                response = self.student.open('/api/v1'+path, method=method, headers={'Origin': ORIGIN, **extra})
                self.record(method, path, response)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(b'R01_SECRET', response.data)
        self.call(self.teacher, 'PATCH', f'/resources/{rid}', {'visibility': 'students'}, 422)
        self.assertEqual(before, self.checkpoint('all student source attempts rejected without events'))
        for vid in versions:
            prep = self.prep(resources=[vid])
            state = self.checkpoint('source linked in teacher draft')
            self.call(self.teacher, 'POST', f"/preparations/{prep['id']}/publish", {}, 404)
            self.assertEqual(state, self.checkpoint('source preparation publication rejected'))
            self.call(self.student, 'GET', f"/preparations/{prep['id']}", status=404)
        self.assertEqual(self.call(self.student, 'GET', f'/courses/{self.course_id}/preparations').json['data'], [])
        with closing(connect(self.path)) as db:
            keys = [r[0] for r in db.execute('SELECT storage_key FROM file_object')]
        for key in keys:
            for path in (f'/uploads/{key}', f'/api/v1/files/{key}'):
                self.assertEqual(self.student.get(path).status_code, 404)

    def test_r01_import_write_fault_rolls_back_and_key_retries(self):
        resource, _ = self.upload([bank(1), bank(2)])
        key = str(uuid4())
        before = self.checkpoint('before import audit fault')
        with closing(connect(self.path)) as db:
            db.executescript("CREATE TRIGGER r01_import_fault BEFORE INSERT ON audit_event "
                             "WHEN NEW.action='resource.question_import' BEGIN SELECT RAISE(ABORT,'R01 fault'); END;")
        try:
            self.import_bank(resource, key=key, status=409)
            self.assertEqual(before, self.checkpoint('after late audit fault: questions batch key all rolled back'))
        finally:
            with closing(connect(self.path)) as db:
                db.execute('DROP TRIGGER r01_import_fault')
        first = self.import_bank(resource, key=key)
        self.assertEqual(first.json['data']['count'], 2)
        after = self.checkpoint('fault removed: original key accepted')
        self.assertEqual(first.data, self.import_bank(resource, key=key).data)
        self.assertEqual(after, self.checkpoint('fault recovery replay unchanged'))

    def test_r01_imported_quiz_old_question_version_and_unreviewed_answers(self):
        source, _ = self.upload([bank(1)])
        vid = self.import_bank(source).json['data']['question_version_ids'][0]
        q = self.call(self.teacher, 'GET', self.url).json['data'][0]
        self.assertEqual(q['version_id'], vid)
        v2 = self.call(self.teacher, 'PATCH', f"/questions/{q['id']}", {'stem': 'R01题目第二版'}).json['data']
        draft = self.call(self.teacher, 'POST', f'/courses/{self.course_id}/papers',
            {'title': 'R01导入随堂测', 'kind': 'quiz', 'confidential': True,
             'items': [{'question_version_id': vid, 'points': 10}]}, 201).json['data']
        pid = draft['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/quizzes',
            {'paper_id': pid, 'start_at': '2026-10-13T12:10:00Z', 'end_at': '2026-10-13T12:20:00Z',
             'confidentiality_note': '未公开且非简单复制'}, 201)
        prep = self.prep(quizzes=[pid])
        self.call(self.teacher, 'POST', f"/preparations/{prep['id']}/publish", {})
        for path in (f"/preparations/{prep['id']}", f'/courses/{self.course_id}/preparations'):
            self.assert_secret_absent(self.call(self.student, 'GET', path).json['data'])
        prestart = self.call(self.student, 'GET', f'/papers/{pid}').json['data']
        self.assertNotIn('items', prestart)
        for value in (q, v2):
            self.call(self.teacher, 'PATCH', f"/questions/{value['id']}", {'practice_available': True}, 409)
        private = self.prep(questions=[vid])
        self.call(self.teacher, 'POST', f"/preparations/{private['id']}/publish", {}, 404)
        self.app.config['TEST_NOW'] = datetime(2026, 10, 13, 12, 11, tzinfo=UTC)
        path = f'/quizzes/{pid}/attempts'
        response = self.student.post('/api/v1'+path,
            json={'answers': [{'question_version_id': vid, 'value': False}]},
            headers={'Origin': ORIGIN, 'X-CSRF-Token': self.student.csrf, 'Idempotency-Key': str(uuid4())})
        self.record('POST', path, response)
        self.assertEqual(response.status_code, 201, response.json)
        aid = response.json['data']['id']
        self.app.config['TEST_NOW'] = datetime(2026, 10, 13, 12, 21, tzinfo=UTC)
        for path in (f'/papers/{pid}', f'/attempts/{aid}', '/users/me/wrong-questions', self.url,
                     f"/preparations/{prep['id']}", f'/courses/{self.course_id}/preparations'):
            self.assert_secret_absent(self.call(self.student, 'GET', path).json['data'])
        self.assertIsNone(self.checkpoint('closed unreviewed imported quiz')['papers'][0]['review_at'])
        self.call(self.teacher, 'POST', f'/quizzes/{pid}/review', {})
        released = self.call(self.student, 'GET', f'/papers/{pid}').json['data']['items'][0]
        self.assertIs(released['answer'], True)
        self.assertEqual(released['question_version_id'], vid)
        self.assertEqual(released['explanation'], 'R01_SECRET_EXPLANATION')
        self.assertEqual(self.checkpoint('explicit review releases original imported version')['counts']['question_import'], 1)
