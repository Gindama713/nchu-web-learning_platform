"""One finite 005 -> 010B lifecycle with real business handlers and retained facts."""

import hashlib
import json
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from backend.shared.db import connect
from tests.test_question_validation import question
from tests.test_questions import ORIGIN, QuestionApiBase


def sanitized(value):
    if isinstance(value, dict):
        return {key: '[REDACTED]' if key.lower() in {
            'password', 'csrf_token', 'password_hash', 'cookie', 'set-cookie', 'authorization', 'secret_key'
        } else sanitized(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitized(item) for item in value]
    return value


class KnowledgeLifecycleTest(QuestionApiBase):
    output = None
    observer = None

    def setUp(self):
        self.requests, self.stages = [], {}
        super().setUp()
        self.addCleanup(self.save)
        self.knowledge_fixture()
        self.base = f'/courses/{self.course_id}/analytics'

    def record(self, client, method, path, body, response):
        self.requests.append({'transport': 'real Flask handler',
            'actor': next((name for name in ('admin', 'teacher', 'student', 'outsider')
                           if client is getattr(self, name, None)), 'bootstrap'),
            'test_now': self.app.config['TEST_NOW'].isoformat(),
            'method': method, 'path': path, 'request': sanitized(body), 'status': response.status_code,
            'response_sha256': hashlib.sha256(response.data).hexdigest(),
            'response': sanitized(response.json) if response.is_json else response.get_data(as_text=True)})

    def call(self, client, method, path, data=None, status=200):
        result = super().call(client, method, path, data, status)
        self.record(client, method, path, data, result)
        return result

    def facts(self):
        tables = ('knowledge_point', 'learning_progress', 'question', 'question_version',
                  'question_knowledge', 'practice_attempt', 'analysis_run', 'audit_event')
        with closing(connect(self.path)) as db:
            values = {table: [dict(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]
                      for table in tables}
            values['foreign_key_check'] = [list(row) for row in db.execute('PRAGMA foreign_key_check')]
        return sanitized(values)

    def save(self):
        if self.output:
            folder = Path(self.output)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'lifecycle.json').write_text(json.dumps({
                'requests': self.requests, 'stages': self.stages}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def edit(self, kid, **changes):
        return self.call(self.teacher, 'PATCH', f'/knowledge-points/{kid}', changes).json['data']

    def analysis(self, teacher=False, suffix=''):
        scope = f'&student_id={self.student_id}' if teacher else ''
        return self.call(self.teacher if teacher else self.student, 'GET',
                         self.base + '?dimension=knowledge' + scope + suffix).json['data']

    def export(self, value):
        return self.call(self.teacher, 'GET', self.base +
            f"/export?analysis_run_id={value['analysis_run_id']}&format=csv").data

    def practice(self, q, answer):
        path = f"/questions/{q['id']}/practice-attempts"
        body = {'question_version_id': q['version_id'], 'answer': answer}
        result = self.student.post('/api/v1' + path, json=body, headers={
            'Origin': ORIGIN, 'X-CSRF-Token': self.student.csrf, 'Idempotency-Key': str(uuid4())})
        self.record(self.student, 'POST', path, body, result)
        self.assertEqual(result.status_code, 201, result.json)

    def checkpoint(self, name, ids, progress):
        student, teacher = self.analysis(), self.analysis(teacher=True)
        for value in (student, teacher):
            m = value['metrics']
            self.assertEqual((value['sample_size'], m['answered_count'], m['correct_count'], m['mastery']),
                             (2, 2, 1, .5))
            self.assertEqual([row['knowledge_id'] for row in m['items']], ids)
            self.assertEqual((m['completed_knowledge_count'], m['published_knowledge_count'], m['progress']), progress)
            self.assertEqual([(row['answered_count'], row['correct_count']) for row in m['items']],
                             [(1, 0) if kid == 1 else (2, 1) for kid in ids])
        for client, old in ((self.student, self.old_student), (self.teacher, self.old_teacher)):
            restored = self.call(client, 'GET', self.base + f"?analysis_run_id={old['analysis_run_id']}").json['data']
            self.assertEqual(restored, old)
        self.assertEqual(self.export(self.old_teacher), self.old_csv)
        facts = self.facts()
        for table in ('question_version', 'question_knowledge', 'practice_attempt', 'learning_progress'):
            self.assertEqual(facts[table], self.original[table])
        old_ids = {self.old_student['analysis_run_id'], self.old_teacher['analysis_run_id']}
        self.assertEqual([row for row in facts['analysis_run'] if row['id'] in old_ids],
                         [row for row in self.original['analysis_run'] if row['id'] in old_ids])
        self.assertEqual(facts['foreign_key_check'], [])
        self.stages[name] = {'student': student, 'teacher': teacher, 'facts': facts}
        if self.observer:
            self.observer(name, self.stages[name])
        return student

    def test_current_projection_retains_history_and_old_snapshots_through_005_lifecycle(self):
        self.edit(1, title='程序计数器原名', content='<p>PC 保存下一条指令地址。</p>', is_foundational=True)
        self.edit(2, title='寄存器原名', is_foundational=True)
        self.call(self.student, 'PUT', '/knowledge-points/1/progress', {'completed': True})
        v1 = self.call(self.teacher, 'POST', self.url,
                       question(practice_available=True, knowledge_ids=[1, 2]), 201).json['data']
        self.practice(v1, 'B')
        v2 = self.call(self.teacher, 'PATCH', f"/questions/{v1['id']}",
                       {'answer': 'B', 'knowledge_ids': [2]}).json['data']
        self.practice(v2, 'B')
        self.app.config['TEST_NOW'] += timedelta(milliseconds=1)
        self.old_student, self.old_teacher = self.analysis(), self.analysis(teacher=True)
        self.old_csv = self.export(self.old_teacher)
        self.original = self.facts()
        self.checkpoint('original', [1, 2], (1, 2, .5))
        self.edit(1, title='程序计数器新名', content='<p>PC 改文后仍保存下一条指令地址。</p>', is_foundational=False)
        renamed = self.checkpoint('renamed', [1, 2], (1, 2, .5))
        self.assertEqual(renamed['metrics']['items'][0]['title'], '程序计数器新名')
        self.assertEqual(self.old_student['metrics']['items'][0]['title'], '程序计数器原名')
        self.edit(1, published=False)
        self.checkpoint('one-hidden', [2], (0, 1, 0))
        self.edit(2, published=False)
        self.checkpoint('all-hidden', [], (0, 0, None))
        self.edit(1, title='程序计数器恢复名', content='<p>隐藏期间修改的正文。</p>')
        self.checkpoint('hidden-edit', [], (0, 0, None))
        self.edit(1, published=True)
        restored = self.checkpoint('one-restored', [1], (1, 1, 1))
        self.assertEqual(restored['metrics']['items'][0]['title'], '程序计数器恢复名')
        self.edit(2, published=True)
        self.checkpoint('both-restored', [1, 2], (1, 2, .5))
        dated = self.analysis(suffix='&from=2026-10-01T00:00:00Z&to=2026-10-02T00:00:00Z')
        self.assertEqual((dated['sample_size'], dated['metrics']['published_knowledge_count'],
                          dated['metrics']['completed_knowledge_count'], dated['metrics']['progress']), (0, 2, 1, .5))
        self.stages['excluded-dates'] = {'student': dated, 'facts': self.facts()}
