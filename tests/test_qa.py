"""T011 algorithm components and real 001/005 handler integration, not socket/UI evidence."""

import json
import math
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

import numpy as np

from backend.app import create_app
from backend.models import qa
from backend.shared.db import connect, migrate
from tests import test_knowledge_integration


class QAAlgorithmTest(TestCase):
    def test_nfkc_html_case_entities_and_whitespace(self):
        self.assertEqual(qa.preprocess('<p>ＰＣ\t\n ALU &amp; &#xFF21;CC</p>'),
                         '程序计数器 算术逻辑单元 & 累加器')
        self.assertEqual(qa.preprocess('  ＡＢＣ\u3000Def\r\nghi  '), 'abc def ghi')

    def test_all_fixed_aliases_english_boundaries_and_chinese_adjacency(self):
        self.assertEqual(qa.preprocess('PC/ALU/ACC/IR'), '程序计数器/算术逻辑单元/累加器/指令寄存器')
        self.assertEqual(qa.preprocess('PC有什么作用'), '程序计数器有什么作用')
        self.assertEqual(qa.preprocess('space alu2 xACC ir_ _pc'), 'space alu2 xacc ir_ _pc')
        self.assertEqual(qa.preprocess('xPC pcx xALU ACCx IRa'), 'xpc pcx xalu accx ira')
        self.assertEqual(qa.preprocess('(IR) ＡＬＵ'), '(指令寄存器) 算术逻辑单元')

    def test_real_character_grams_smoothed_idf_counts_and_l2(self):
        rows = [{'id': 1, 'title': '', 'content': '甲甲', 'example': ''},
                {'id': 2, 'title': '', 'content': '甲乙', 'example': ''}]
        index = qa.build_index('fixed', rows)
        vocabulary = index.vectorizer.vocabulary_
        self.assertEqual(set(vocabulary), {'甲', '乙', '甲甲', '甲乙'})
        idf = math.log(3 / 2) + 1
        self.assertAlmostEqual(index.vectorizer.idf_[vocabulary['甲']], 1)
        self.assertAlmostEqual(index.vectorizer.idf_[vocabulary['甲甲']], idf)
        self.assertAlmostEqual(index.matrix.toarray()[0, vocabulary['甲']], 2 / math.sqrt(4 + idf**2))
        np.testing.assert_allclose(np.asarray(index.matrix.multiply(index.matrix).sum(axis=1)), [[1], [1]])
        vector = qa.build_index('grams', [{'id': 3, 'title': '', 'content': '甲乙丙', 'example': ''}])
        self.assertIn('甲乙丙', vector.vectorizer.vocabulary_)
        self.assertNotIn('甲乙丙丁', vector.vectorizer.vocabulary_)

    def test_raw_threshold_sort_before_rounding_top_k_excerpt_200(self):
        rows = [{'id': i, 'content': '<p>' + '甲' * 201 + '</p>'} for i in [1, 8, 3, 5, 2]]
        matches, raw = qa.rank_matches(rows, [0.09999999, 0.10000001, 0.10, 0.10000002, 0.10], 5)
        self.assertEqual([m['knowledge_id'] for m in matches], [5, 8, 2, 3])
        self.assertEqual([m['similarity'] for m in matches], [0.1] * 4)
        self.assertEqual(raw[0], 0.10000002)
        self.assertEqual(len(matches[0]['excerpt']), 200)
        self.assertEqual(qa.rank_matches(rows, [0.2] * 5, 1)[0][0]['knowledge_id'], 1)

    def test_zero_vector_empty_corpus_and_empty_vocabulary(self):
        for rows in ([], [{'id': 1, 'title': '<b></b>', 'content': '<p> </p>', 'example': ''}]):
            self.assertEqual(qa.build_index('empty', rows).search('PC', 3), ([], []))
        index = qa.build_index('nonempty', [{'id': 1, 'title': '甲', 'content': '乙', 'example': '丙'}])
        self.assertEqual(index.search('🦄', 3), ([], []))
        self.assertEqual(index.search('<b></b>', 3), ([], []))
        self.assertEqual(index.search('丙', 3)[0][0]['knowledge_id'], 1)


class QAIntegrationTest(TestCase):
    setUp = test_knowledge_integration.KnowledgeIntegrationTest.setUp
    tearDown = test_knowledge_integration.KnowledgeIntegrationTest.tearDown
    call = test_knowledge_integration.KnowledgeIntegrationTest.call
    login = test_knowledge_integration.KnowledgeIntegrationTest.login

    def ask(self, question='PC 有什么作用', client=None, status=200, **extra):
        return self.call(client or self.student, 'POST', self.course + '/qa',
                         {'question': question, **extra}, status)

    def update(self, **values):
        return self.call(self.teacher, 'PATCH', self.detail, values)

    def rows(self, table):
        with closing(connect(self.path)) as db:
            return [dict(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY id')]

    def test_real_published_corpus_response_records_raw_scores_and_reuse(self):
        self.call(self.teacher, 'POST', f'/chapters/{self.chapter_id}/knowledge-points',
                  {'title': '草稿PC', 'content': '绝密草稿内容', 'published': False}, 201)
        response = self.ask()
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        data = response.json['data']
        self.assertEqual(set(data), {'matches', 'found', 'reason', 'index_version', 'algorithm_version'})
        self.assertEqual((data['found'], data['reason'], data['algorithm_version']), (True, 'matched', qa.ALGORITHM))
        self.assertEqual([m['knowledge_id'] for m in data['matches']], [self.point])
        self.assertEqual(data['matches'][0]['excerpt'], 'PC 指向下一条指令')
        self.assertEqual(set(data['matches'][0]), {'knowledge_id', 'excerpt', 'similarity'})
        cache = self.app.extensions['qa_cache'].items[self.course_id]
        with patch.object(qa, 'build_index', side_effect=AssertionError('must reuse')):
            self.assertEqual(self.ask().json['data'], data)
        self.assertIs(self.app.extensions['qa_cache'].items[self.course_id], cache)
        records = self.rows('qa_query')
        self.assertEqual(len(records), 2)
        record = records[0]
        self.assertEqual((record['user_id'], record['course_id'], record['index_revision'], record['algorithm_version']),
                         (self.student_id, self.course_id, data['index_version'], qa.ALGORITHM))
        self.assertEqual(json.loads(record['matched_ids_json']), [self.point])
        expected = cache.search('PC 有什么作用', 3)[1]
        self.assertEqual(json.loads(record['similarities_json']), expected)
        self.assertEqual(round(expected[0], 6), data['matches'][0]['similarity'])
        self.ask(client=self.teacher)
        self.ask(client=self.admin)  # L per APIC; administrator sees published corpus only.
        self.call(self.student, 'GET', self.course + '/qa-query-records', status=404)

    def test_real_update_unpublish_empty_revision_zero_and_draft_isolation(self):
        original = self.ask().json['data']['index_version']
        for question in ('🦄', '<b></b>'):
            data = self.ask(question).json['data']
            self.assertEqual((data['found'], data['matches'], data['reason']), (False, [], 'no_match'))
        self.update(title='累加器', content='<p>累加器保存计算结果</p>')
        changed = self.ask('ACC').json['data']
        self.assertNotEqual(changed['index_version'], original)
        self.assertIn('计算结果', changed['matches'][0]['excerpt'])
        self.update(published=False)
        empty = self.ask().json['data']
        self.assertEqual((empty['found'], empty['matches'], empty['reason']), (False, [], 'empty_corpus'))
        self.assertNotEqual(empty['index_version'], changed['index_version'])
        self.update(content='下架文本再次变动')
        self.assertEqual(self.ask().json['data'], empty)
        self.update(published=True)
        self.assertNotEqual(self.ask().json['data']['index_version'], empty['index_version'])

    def test_http_top_k_same_score_order(self):
        ids = [self.point]
        for _ in range(5):
            ids.append(self.call(self.teacher, 'POST', f'/chapters/{self.chapter_id}/knowledge-points', {
                'title': '程序计数器', 'content': '<p>PC 指向下一条指令</p>', 'published': True}, 201).json['data']['id'])
        self.assertEqual([m['knowledge_id'] for m in self.ask(top_k=5).json['data']['matches']], ids[:5])
        self.assertEqual(len(self.ask().json['data']['matches']), 3)
        self.assertEqual(len(self.ask(top_k=1).json['data']['matches']), 1)

    def test_input_csrf_cross_course_and_session_denials_leave_no_queries(self):
        for question in ('', ' ', 'a' * 501, 1, None):
            self.ask(question, status=400)
        for value in (0, 6, True, 1.5, '3', None):
            self.ask(top_k=value, status=400)
        self.ask(user_id=self.student_id, status=400)
        self.call(self.student, 'POST', self.course + '/qa?top_k=3', {'question': 'PC'}, 400)
        self.call(self.student, 'POST', self.course + '/qa', {}, 400)
        self.ask(client=self.outsider, status=404)
        self.call(self.student, 'POST', '/courses/9999/qa', {'question': 'PC'}, 404)
        response = self.student.post('/api/v1' + self.course + '/qa', json={'question': 'PC'}, headers={'Origin': ORIGIN})
        self.assertEqual(response.status_code, 403)
        response = self.student.post('/api/v1' + self.course + '/qa', json={'question': 'PC'},
                                     headers={'Origin': 'https://foreign.example', 'X-CSRF-Token': self.student.csrf})
        self.assertEqual(response.status_code, 403)
        self.call(self.app.test_client(), 'POST', self.course + '/qa', {'question': 'PC'}, 401)
        self.assertEqual(self.rows('qa_query'), [])
        self.call(self.teacher, 'DELETE', self.course + f'/members/{self.student_id}', status=204)
        self.ask(status=404)
        self.call(self.admin, 'PATCH', f'/users/{self.student_id}', {'active': False})
        self.ask(status=401)

    def test_build_failure_after_real_update_never_serves_old_and_recovers(self):
        old = self.ask().json['data']
        self.update(content='全新知识正文')
        with patch.object(qa, 'build_index', side_effect=RuntimeError('injected sensitive internal path')):
            response = self.ask(status=503)
        self.assertEqual(response.json['error']['code'], 'INDEX_UNAVAILABLE')
        self.assertNotIn('指向', response.get_data(as_text=True))
        self.assertNotIn('sensitive', response.get_data(as_text=True))
        self.assertNotIn(self.course_id, self.app.extensions['qa_cache'].items)
        index = self.rows('qa_index')[0]
        self.assertEqual((index['status'], index['error_code']), ('failed', 'INDEX_UNAVAILABLE'))
        self.assertNotEqual(index['corpus_revision'], old['index_version'])
        self.assertEqual(len(self.rows('qa_query')), 1)
        self.call(self.student, 'PUT', self.detail + '/progress', {'completed': True})
        self.assertEqual(self.ask('全新知识').json['data']['index_version'], index['corpus_revision'])
        self.assertEqual(self.rows('qa_index')[0]['status'], 'ready')

    def test_unpublish_with_failed_rebuild_cannot_return_obsolete_excerpt(self):
        self.ask()
        self.update(published=False)
        with patch.object(qa, 'build_index', side_effect=RuntimeError('controlled fault')):
            self.ask(status=503)
        self.assertEqual(self.ask().json['data']['reason'], 'empty_corpus')

    def test_failed_qa_does_not_block_real_objective_practice_submission(self):
        question = self.call(self.teacher, 'POST', self.course + '/questions', {
            'type': 'boolean', 'stem': 'PC保存下一条指令地址？', 'answer': True, 'options': [],
            'difficulty': 'easy', 'knowledge_ids': [self.point], 'practice_available': True}, 201).json['data']
        with patch.object(qa, 'build_index', side_effect=RuntimeError('controlled index fault')):
            self.ask(status=503)
            response = self.student.post(f"/api/v1/questions/{question['id']}/practice-attempts", json={
                'question_version_id': question['version_id'], 'answer': True}, headers={
                'Origin': ORIGIN, 'X-CSRF-Token': self.student.csrf, 'Idempotency-Key': str(uuid4())})
        self.assertEqual(response.status_code, 201, response.json)
        self.assertTrue(response.json['data']['correct'])
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM practice_attempt').fetchone()[0], 1)
        self.assertEqual(self.rows('qa_query'), [])

    def test_continuous_real_updates_exhaust_bounded_retry_without_old_result(self):
        original = qa.build_index
        revisions = []

        def changing(revision, rows):
            revisions.append(revision)
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(self.update, content=f'语料变更{len(revisions)}').result()
            return original(revision, rows)

        with patch.object(qa, 'build_index', side_effect=changing):
            response = self.ask(status=503)
        self.assertEqual(response.json['error']['code'], 'INDEX_UNAVAILABLE')
        self.assertEqual(len(set(revisions)), 3)
        self.assertEqual(self.rows('qa_query'), [])
        self.assertNotIn(self.course_id, self.app.extensions['qa_cache'].items)
        self.assertEqual(self.ask('语料变更3').json['data']['matches'][0]['excerpt'], '语料变更3')

    def test_real_update_during_fit_retries_and_atomically_publishes_new_revision(self):
        self.ask()
        self.update(content='重建开始前内容')
        original = qa.build_index
        captured = []

        def building(revision, rows):
            captured.append(revision)
            self.assertNotIn(self.course_id, self.app.extensions['qa_cache'].items)
            if len(captured) == 1:
                # Actual second HTTP-handler/connection write while fitting: no write lock.
                with ThreadPoolExecutor(max_workers=1) as executor:
                    executor.submit(self.update, content='最终原子替换正文').result()
            return original(revision, rows)

        with patch.object(qa, 'build_index', side_effect=building):
            data = self.ask('最终原子替换').json['data']
        self.assertEqual(len(captured), 2)
        self.assertNotEqual(data['index_version'], captured[0])
        self.assertEqual(data['index_version'], captured[1])
        self.assertEqual(data['matches'][0]['excerpt'], '最终原子替换正文')
        self.assertEqual(len(self.rows('qa_query')), 2)

    def test_revocation_during_fit_is_rechecked_before_query_record(self):
        original = qa.build_index

        def revoked(revision, rows):
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(self.call, self.teacher, 'DELETE',
                                self.course + f'/members/{self.student_id}', status=204).result()
            return original(revision, rows)

        with patch.object(qa, 'build_index', side_effect=revoked):
            self.ask(status=404)
        self.assertEqual(self.rows('qa_query'), [])
        self.assertEqual(self.rows('qa_index'), [])

    def test_persistence_failure_rolls_back_both_and_does_not_replace_cache(self):
        self.ask()
        old = self.rows('qa_index')
        self.update(content='更新正文')
        for table in ('qa_query', 'qa_index'):
            with closing(connect(self.path)) as db:
                operation = 'INSERT' if table == 'qa_query' else 'UPDATE'
                db.execute(f"CREATE TRIGGER fail_qa BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'fault'); END")
            self.ask(status=503)
            self.assertEqual(self.rows('qa_index'), old)
            self.assertEqual(len(self.rows('qa_query')), 1)
            self.assertNotIn(self.course_id, self.app.extensions['qa_cache'].items)
            with closing(connect(self.path)) as db:
                db.execute('DROP TRIGGER fail_qa')
        self.ask()

    def test_parallel_queries_and_restart_backup_rebuild_from_facts(self):
        cookie = self.student.get_cookie('cpu_session')

        def query(_):
            client = self.app.test_client()
            client.set_cookie('cpu_session', cookie.value)
            client.csrf = self.student.csrf
            return self.ask(client=client).json['data']

        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(query, range(3)))
        self.assertEqual(results, [results[0]] * 3)
        self.assertEqual(len(self.rows('qa_index')), 1)
        self.assertEqual(len(self.rows('qa_query')), 3)
        migrate(self.path)
        backup = self.path.with_name('backup.db')
        with closing(connect(self.path)) as db, closing(connect(backup)) as target:
            db.backup(target)
            self.assertEqual(target.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(target.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        restored = create_app({**self.app.config, 'DATABASE_PATH': str(backup)})
        client = restored.test_client()
        client.set_cookie('cpu_session', cookie.value)
        client.csrf = self.student.csrf
        self.assertEqual(self.ask(client=client).json['data'], results[0])
        self.assertEqual(len(restored.extensions['qa_cache'].items), 1)


ORIGIN = 'http://127.0.0.1:5173'
