"""One bounded real-API scenario shared by handler and socket/UI evidence."""

from datetime import timedelta
from uuid import uuid4

from scripts.i03_support import facts


class Subchain:
    def __init__(self, call, app, teacher, students, course_id, at, password):
        self.call, self.app, self.teacher, self.students = call, app, teacher, students
        self.course, self.at, self.password = course_id, at, password
        self.base = f'/courses/{course_id}'
        self.stages = {}

    def data(self, actor, method, path, payload=None, status=200, **kw):
        return self.call(actor, method, path, payload, status, **kw).json['data']

    def capture(self, name):
        snapshot = facts(self.app.config['DATABASE_PATH'])
        assert snapshot['foreign_key_check'] == [] and snapshot['integrity_check'] == 'ok'
        self.stages[name] = snapshot
        return snapshot

    def seed(self):
        self.ids = []
        for position, client in enumerate(self.students):
            if position:
                number = f'I03STUDENT{position + 1}'
                self.call(client, 'POST', '/auth/register', {
                    'student_no': number, 'name': number, 'password': self.password}, 201)
                session = self.data(client, 'POST', '/auth/login', {'student_no': number, 'password': self.password})
                client.csrf = session['csrf_token']
            uid = self.data(client, 'GET', '/auth/session')['user']['id']
            self.ids.append(uid)
            if position:
                self.call(self.teacher, 'POST', self.base + '/members', {'user_id': uid, 'member_role': 'student'}, 201)
        chapter = self.data(self.teacher, 'POST', self.base + '/chapters', {'title': 'I03固定版本知识'}, 201)['id']
        self.points = []
        for title, text, published in (
            ('程序计数器', '程序计数器保存下一条指令的地址。I03原始知识出处。', True),
            ('算术逻辑单元', '算术逻辑单元执行加减和逻辑运算。I03第二知识出处。', True),
            ('草稿禁止语料', '草稿秘密不可作为出处', False),
        ):
            self.points.append(self.data(self.teacher, 'POST', f'/chapters/{chapter}/knowledge-points', {
                'title': title, 'content': '<p>' + text + '</p>', 'published': published}, 201)['id'])
        k1, k2, _ = self.points
        self.questions = []
        for index, tags in enumerate(([k1, k2], [k1], [k2], [k1])):
            short = index == 3
            self.questions.append(self.data(self.teacher, 'POST', self.base + '/questions', {
                'type': 'short' if short else 'single', 'stem': f'I03原版本第{index + 1}题',
                'options': [] if short else [{'key': 'A', 'text': '甲'}, {'key': 'B', 'text': '乙'}],
                'answer': '原版本参考简答' if short else 'A', 'explanation': f'I03原版本解析{index + 1}',
                'difficulty': 'easy', 'knowledge_ids': tags}, 201))
        self.quiz = self.data(self.teacher, 'POST', self.base + '/papers', {
            'title': 'I03四人固定版本测验', 'kind': 'quiz', 'confidential': True,
            'items': [{'question_version_id': q['version_id'], 'points': 10} for q in self.questions]}, 201)['id']
        self.data(self.teacher, 'POST', self.base + '/quizzes', {
            'paper_id': self.quiz, 'start_at': (self.at + timedelta(minutes=1)).isoformat(),
            'end_at': (self.at + timedelta(minutes=2)).isoformat(), 'confidentiality_note': '确认未公开且非复制公开题'}, 201)
        # Later current version changes both answer and tags. Every consumer must keep the frozen version.
        self.new_version = self.data(self.teacher, 'PATCH', f"/questions/{self.questions[0]['id']}", {
            'stem': 'I03后续版本不应改写原答卷', 'answer': 'B', 'knowledge_ids': [k1]})
        self.call(self.students[0], 'PUT', f'/knowledge-points/{k1}/progress', {'completed': True})
        self.capture('published_frozen_four')

    def submit(self):
        self.app.config['TEST_NOW'] = self.at + timedelta(minutes=1)
        values = ((0, 'B'), (1, 'A'), (3, '学生待批简答'))
        self.attempts = []
        for client, pairs in zip(self.students[:3], (values, ((0, 'A'), (1, 'B'), (2, 'A')), ()), strict=True):
            submitted = self.data(client, 'POST', f'/quizzes/{self.quiz}/attempts', {'answers': [
                {'question_version_id': self.questions[i]['version_id'], 'value': value} for i, value in pairs]},
                201, headers={'Idempotency-Key': str(uuid4())})
            self.attempts.append(submitted['id'])
        self.app.config['TEST_NOW'] = self.at + timedelta(minutes=3)

    def analytics(self, dimension, client=None):
        suffix = '&kind=quiz' if dimension == 'scores' else ''
        return self.data(client or self.teacher, 'GET', self.base + '/analytics?dimension=' + dimension + suffix)

    def wrong(self, client=None):
        return self.data(client or self.students[0], 'GET', '/users/me/wrong-questions')

    def verify_before_review(self):
        k1, k2, _ = self.points
        own = self.students[0]
        statistics = self.data(self.teacher, 'GET', f'/quizzes/{self.quiz}/statistics')
        assert [statistics[k] for k in ('expected_count', 'submitted_count', 'missing_count')] == [4, 3, 1]
        assert statistics['objective_correct_rate'] == 1 / 3
        assert statistics['questions'][3]['pending_count'] == 1
        self.call(own, 'GET', f'/quizzes/{self.quiz}/statistics', status=403)
        first, second = self.wrong(), self.wrong(self.students[1])
        assert len(first) == len(second) == 1
        wrong = first[0]
        assert (wrong['question_id'], wrong['question_version_id'], wrong['knowledge_ids']) == (
            self.questions[0]['id'], self.questions[0]['version_id'], [k1, k2])
        assert (wrong['last_attempt_type'], wrong['last_attempt_id'], wrong['wrong_count']) == ('paper', self.attempts[0], 1)
        assert wrong['answer_visible'] is False and 'answer' not in wrong and 'explanation' not in wrong
        assert self.wrong(self.students[2]) == self.wrong(self.students[3]) == []
        assert self.data(own, 'GET', f'/users/me/wrong-questions?knowledge_id={k2}') == first
        for client, attempt in zip(self.students[:3], self.attempts, strict=True):
            paper = self.data(client, 'GET', f'/papers/{self.quiz}')
            answer = self.data(client, 'GET', f'/attempts/{attempt}')
            for item in paper['items'] + answer['answers']:
                assert 'answer' not in item and 'explanation' not in item
        self.call(self.students[1], 'GET', f'/attempts/{self.attempts[0]}', status=404)
        self.old = {kind: self.analytics(kind) for kind in ('knowledge', 'scores')}
        knowledge, scores = self.old['knowledge'], self.old['scores']
        assert (knowledge['sample_size'], knowledge['metrics']['correct_count'], knowledge['metrics']['mastery']) == (5, 3, 0.6)
        assert [(i['answered_count'], i['correct_count']) for i in knowledge['metrics']['items']] == [(4, 2), (3, 2)]
        m = scores['metrics']
        assert [m[k] for k in ('expected_count', 'submitted_count', 'missing_count', 'graded_count', 'partial_count',
                              'mean_percentage')] == [4, 3, 1, 2, 1, 25]
        self.own = self.analytics('knowledge', own)
        assert (self.own['sample_size'], self.own['metrics']['correct_count'], self.own['metrics']['progress']) == (2, 1, 0.5)
        for client in self.students[2:]:
            empty = self.analytics('knowledge', client)
            assert empty['sample_size'] == 0 and empty['metrics']['mastery'] is None
        self.csv = {kind: self.call(self.teacher, 'GET', self.base +
                    f"/analytics/export?analysis_run_id={item['analysis_run_id']}&format=csv").data for kind, item in self.old.items()}
        raw = self.capture('closed_unreviewed')
        assert len(raw['paper_participant']) == 4 and len(raw['attempt']) == 3 and len(raw['answer']) == 12
        assert sum(a['answered'] for a in raw['answer']) == 6  # Five objective + one pending short.
        assert len(raw['wrong_question']) == 2
        assert sum(a['score_hundredths'] is None for a in raw['answer']) == 1
        versions = {v['id']: v for v in raw['question_version']}
        objective = [a for a in raw['answer'] if a['answered'] and versions[a['question_version_id']]['type'] != 'short']
        assert len(objective) == 5 and sum(a['score_hundredths'] > 0 for a in objective) == 3
        assert all(a['question_version_id'] != self.new_version['version_id'] for a in raw['answer'])
        for row in raw['wrong_question']:
            source = next(a for a in raw['attempt'] if a['id'] == row['last_attempt_id'])
            assert source['student_id'] == row['student_id'] and source['paper_id'] == self.quiz
        saved = next(r for r in raw['analysis_run'] if r['id'] == knowledge['analysis_run_id'])
        self.stages['knowledge_input'] = saved['input_snapshot_json']

    def review(self):
        self.data(self.teacher, 'PATCH', f'/attempts/{self.attempts[0]}/manual-scores', {
            'revision': 0, 'items': [{'question_version_id': self.questions[3]['version_id'], 'score': 8, 'comment': '真实批分'}]})
        self.call(self.students[0], 'POST', f'/quizzes/{self.quiz}/review', {}, 403)
        self.data(self.teacher, 'POST', f'/quizzes/{self.quiz}/review', {})
        wrong = self.wrong()[0]
        assert wrong['answer_visible'] is True and wrong['answer'] == 'A'
        assert wrong['knowledge_ids'] == self.points[:2] and wrong['explanation'] == 'I03原版本解析1'
        answer = self.data(self.students[0], 'GET', f'/attempts/{self.attempts[0]}')
        assert answer['score'] == 18 and answer['status'] == 'graded'
        assert answer['answers'][0]['answer'] == 'A' and answer['answers'][0]['value'] == 'B'
        assert self.analytics('scores')['metrics']['mean_percentage'] == 31.67
        assert self.analytics('knowledge')['metrics']['mastery'] == 0.6
        self.assert_old_snapshots()
        self.capture('reviewed_graded')

    def assert_old_snapshots(self):
        for kind, original in self.old.items():
            run = original['analysis_run_id']
            assert self.data(self.teacher, 'GET', self.base + f'/analytics?analysis_run_id={run}') == original
            assert self.call(self.teacher, 'GET', self.base +
                             f'/analytics/export?analysis_run_id={run}&format=csv').data == self.csv[kind]

    def qa(self):
        own = self.students[0]
        # Use actual old-version labels to obtain a title, then ask within its course.
        self.sources = []
        for kid in self.wrong()[0]['knowledge_ids']:
            point = self.data(own, 'GET', f'/knowledge-points/{kid}')
            matches = self.data(own, 'POST', self.base + '/qa', {'question': point['title'], 'top_k': 3})
            assert matches['found'] and kid in [i['knowledge_id'] for i in matches['matches']]
            assert self.points[2] not in [i['knowledge_id'] for i in matches['matches']]
            source = next(i for i in matches['matches'] if i['knowledge_id'] == kid)
            assert source['excerpt'] in point['content']
            self.sources.append(matches)
        self.call(own, 'GET', f'/knowledge-points/{self.points[2]}', status=404)
        self.capture('same_course_qa_sources')

    def unpublish(self):
        k2 = self.points[1]
        self.data(self.teacher, 'PATCH', f'/knowledge-points/{k2}', {'published': False})
        self.call(self.students[0], 'GET', f'/knowledge-points/{k2}', status=404)
        answer = self.data(self.students[0], 'POST', self.base + '/qa', {'question': '算术逻辑单元', 'top_k': 5})
        assert k2 not in [i['knowledge_id'] for i in answer['matches']]
        assert answer['index_version'] != self.sources[-1]['index_version']
        newer = self.analytics('knowledge')
        assert newer['sample_size'] == 5 and [i['knowledge_id'] for i in newer['metrics']['items']] == [self.points[0]]
        assert self.wrong()[0]['knowledge_ids'] == self.points[:2]  # Historical tags stay traceable.
        self.assert_old_snapshots()
        self.capture('unpublished_historical_tags_old_snapshot')

    def revoke(self):
        own = self.students[0]
        self.call(self.teacher, 'DELETE', self.base + f'/members/{self.ids[0]}', status=204)
        for path in (f'/papers/{self.quiz}', f'/attempts/{self.attempts[0]}',
                     f'/knowledge-points/{self.points[0]}', self.base + f"/analytics?analysis_run_id={self.own['analysis_run_id']}"):
            self.call(own, 'GET', path, status=404)
        assert self.wrong() == []
        self.call(own, 'POST', self.base + '/qa', {'question': '程序计数器'}, 404)
        assert self.analytics('scores')['metrics']['expected_count'] == 4
        self.assert_old_snapshots()
        raw = self.capture('revoked')
        actions = [r['action'] for r in raw['audit_event']]
        assert actions.count('quiz.review') == 1 and actions.count('attempt.manual_scores') == 1
        assert len(raw['attempt']) == 3 and len(raw['wrong_question']) == 2
