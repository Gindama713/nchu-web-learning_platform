"""C06 real sessions / knowledge / objective practice / published paper / saved analytics."""

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch
from uuid import uuid4

from backend.models import knowledge_analysis as model
from backend.shared.db import connect, migrate
from tests import test_attempts, test_practices


class KnowledgeAnalyticsTest(test_attempts.AttemptApiBase):
    create_question = test_attempts.KnowledgeFixtureAttemptTest.create_question
    make_paper = test_attempts.KnowledgeFixtureAttemptTest.make_paper
    at = test_attempts.KnowledgeFixtureAttemptTest.at
    answer = test_attempts.KnowledgeFixtureAttemptTest.answer
    practice = test_practices.KnowledgeFixturePracticeTest.practice

    def setUp(self):
        super().setUp()
        self.knowledge_fixture()  # This helper calls the actual merged 005 APIs.
        self.analytics_url = f'/courses/{self.course_id}/analytics'

    def query(self, client=None, suffix='', status=200):
        return self.call(client or self.student, 'GET', self.analytics_url + '?dimension=knowledge' + suffix,
                         status=status)

    def restore(self, run, client=None, status=200):
        return self.call(client or self.student, 'GET',
                         self.analytics_url + f'?analysis_run_id={run}', status=status)

    def point(self, number, **changes):
        return self.call(self.teacher, 'PATCH', f'/knowledge-points/{number}', changes)

    def progress(self, number):
        self.call(self.student, 'PUT', f'/knowledge-points/{number}/progress', {'completed': True})

    def count_runs(self):
        with closing(connect(self.path)) as db:
            return db.execute("SELECT count(*) FROM analysis_run WHERE kind='knowledge'").fetchone()[0]

    def test_four_answers_three_correct_multitag_fixed_versions_and_zero_sample(self):
        q = self.create_question(practice_available=True, knowledge_ids=[1, 2])
        key = str(uuid4())
        self.practice(q, 'A', key=key)
        self.practice(q, 'A', key=key)  # Successful retry is one original sample.
        self.practice(q, 'A')
        self.practice(q, 'A')
        self.practice(q, 'B')
        self.practice(q, None)  # Retained but excluded from mastery.
        self.call(self.teacher, 'PATCH', f"/questions/{q['id']}", {'knowledge_ids': [2], 'answer': 'B'})
        chapter = self.call(self.teacher, 'GET', f'/courses/{self.course_id}/chapters').json['data'][0]['id']
        self.call(self.teacher, 'POST', f'/chapters/{chapter}/knowledge-points',
                  {'title': '零样本', 'content': '正文', 'published': True}, 201)
        self.at(13)
        response = self.query()
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        data = response.json['data']
        self.assertEqual((data['sample_size'], data['metrics']['answered_count'], data['metrics']['mastery']),
                         (4, 4, 0.75))
        self.assertEqual([(p['answered_count'], p['correct_count'], p['wrong_count'], p['mastery'])
                          for p in data['metrics']['items']], [(4, 3, 1, 0.75), (4, 3, 1, 0.75), (0, 0, 0, None)])
        self.assertEqual(sum(row['metrics']['answered_count'] for row in data['series']), 4)
        with closing(connect(self.path)) as db:
            run = db.execute('SELECT * FROM analysis_run WHERE id=?', (data['analysis_run_id'],)).fetchone()
            snapshot, parameters = json.loads(run['input_snapshot_json']), json.loads(run['parameters_json'])
            self.assertEqual(parameters['knowledge_ids'], [1, 2, 3])
            self.assertEqual([row['knowledge_ids'] for row in snapshot['samples']], [[1, 2]] * 4)
            reproduced = model.calculate(snapshot, parameters['from'], parameters['to'], run['source_until'])
            self.assertEqual(reproduced['metrics'], data['metrics'])
            self.assertEqual(reproduced['series'], data['series'])
            self.assertNotIn('answer_json', run['input_snapshot_json'])

    def test_real_paper_answers_blank_short_manual_revision_and_replay_count_once(self):
        qs = [self.create_question(knowledge_ids=[1, 2]), self.create_question(),
              self.create_question(type='short', options=[], answer='参考')]
        paper = self.make_paper(qs)
        self.at(13)
        key = str(uuid4())
        answers = [self.answer(qs[0], 'A'), self.answer(qs[2], '学生文本')]
        attempt = self.submit(paper, answers, key=key).json['data']
        self.submit(paper, answers, key=key)
        self.at(14)
        old = self.query().json['data']
        self.assertEqual((old['sample_size'], old['metrics']['correct_count']), (1, 1))
        self.call(self.teacher, 'PATCH', f"/attempts/{attempt['id']}/manual-scores", {
            'revision': 0, 'items': [{'question_version_id': qs[2]['version_id'], 'score': 8, 'comment': ''}]})
        self.assertEqual(self.restore(old['analysis_run_id']).json['data'], old)
        self.assertEqual(self.query().json['data']['metrics'], old['metrics'])

    def test_r38_current_set_dates_unpublish_republish_and_empty(self):
        chapter = self.call(self.teacher, 'GET', f'/courses/{self.course_id}/chapters').json['data'][0]['id']
        self.call(self.teacher, 'POST', f'/chapters/{chapter}/knowledge-points',
                  {'title': '第三点', 'content': '正文', 'published': True}, 201)
        self.progress(1)
        self.progress(2)
        original = self.query().json['data']
        self.assertEqual(original['metrics']['progress'], 2 / 3)
        self.point(1, published=False)
        narrow = '&from=2026-10-01T00:00:00Z&to=2026-10-02T00:00:00Z'
        value = self.query(suffix=narrow).json['data']['metrics']
        self.assertEqual((value['completed_knowledge_count'], value['published_knowledge_count'], value['progress']),
                         (1, 2, 0.5))
        self.point(1, published=True)
        self.point(3, published=False)
        self.assertEqual(self.query().json['data']['metrics']['progress'], 1)
        self.point(1, published=False)
        self.point(2, published=False)
        empty = self.query().json['data']
        self.assertEqual(empty['metrics']['published_knowledge_count'], 0)
        self.assertEqual(empty['metrics']['completed_knowledge_count'], 0)
        self.assertIsNone(empty['metrics']['progress'])
        self.assertIsNone(empty['metrics']['mastery'])
        self.assertEqual(empty['metrics']['items'], [])
        self.assertEqual(self.restore(original['analysis_run_id']).json['data'], original)
        self.assertEqual(self.restore(empty['analysis_run_id']).json['data'], empty)

    def test_date_half_open_bounds_and_all_objective_types(self):
        qs = [self.create_question(practice_available=True),
              self.create_question(practice_available=True, type='multiple', answer=['A', 'B']),
              self.create_question(practice_available=True, type='boolean', options=[], answer=False),
              self.create_question(practice_available=True, type='numeric', options=[], answer=0.2, tolerance=0.1)]
        for q, value in zip(qs, ['A', ['A'], False, 0.3], strict=True):
            self.practice(q, value)
        self.at(13)
        self.practice(qs[0], 'B')
        self.at(14)
        value = self.query(suffix='&from=2026-10-13T12:00:00Z&to=2026-10-13T13:00:00Z').json['data']
        self.assertEqual((value['sample_size'], value['metrics']['correct_count'], value['metrics']['mastery']),
                         (4, 3, 0.75))
        self.assertEqual(self.query().json['data']['sample_size'], 5)

    def test_practice_and_answer_equal_numeric_ids_are_distinct_samples(self):
        practice = self.create_question(practice_available=True, knowledge_ids=[1, 2])
        self.practice(practice, 'B')
        private = self.create_question(knowledge_ids=[1, 2])
        paper = self.make_paper([private])
        self.at(13)
        self.submit(paper, [self.answer(private, 'A')])
        self.at(14)
        value = self.query().json['data']
        self.assertEqual((value['sample_size'], value['metrics']['correct_count'], value['metrics']['mastery']),
                         (2, 1, 0.5))
        self.assertEqual([item['answered_count'] for item in value['metrics']['items']], [2, 2])
        with closing(connect(self.path)) as db:
            snapshot = json.loads(db.execute('SELECT input_snapshot_json FROM analysis_run WHERE id=?',
                                             (value['analysis_run_id'],)).fetchone()[0])
            self.assertEqual({(row['source'], row['sample_id']) for row in snapshot['samples']},
                             {('practice', 1), ('answer', 1)})

    def test_student_teacher_scope_isolation_and_class_progress(self):
        q = self.create_question(practice_available=True)
        self.practice(q, 'A')
        self.progress(1)
        self.at(13)
        personal = self.query().json['data']
        class_data = self.query(self.teacher).json['data']
        self.assertIsNone(class_data['metrics']['progress'])
        self.assertIsNone(class_data['metrics']['completed_knowledge_count'])
        selected = self.query(self.teacher, f'&student_id={self.student_id}').json['data']
        self.assertEqual(selected['metrics'], personal['metrics'])
        self.call(self.teacher, 'GET', self.analytics_url +
                  f"/export?analysis_run_id={class_data['analysis_run_id']}&format=csv", status=503)
        self.call(self.student, 'GET', self.analytics_url +
                  f"/export?analysis_run_id={personal['analysis_run_id']}&format=csv", status=403)
        self.restore(personal['analysis_run_id'], self.teacher, 404)
        self.restore(class_data['analysis_run_id'], self.student, 404)
        self.query(self.student, '&student_id=999', 403)
        self.query(self.teacher, '&student_id=999', 404)
        self.query(self.outsider, status=404)
        self.query(self.admin, status=404)
        self.query(self.app.test_client(), status=401)
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{self.student_id}', status=204)
        self.restore(personal['analysis_run_id'], status=404)
        self.restore(selected['analysis_run_id'], self.teacher, 404)

    def test_invalid_filters_snapshot_kind_cross_course_and_deleted(self):
        for suffix in ('&kind=quiz', '&paper_id=1', '&performance_paper_ids=1', '&x=1', '&student_id=',
                       '&student_id=0', '&student_id=9223372036854775808', '&dimension=attendance',
                       '&from=', '&from=2026-10-13T00:00:00Z&from=2026-10-12T00:00:00Z',
                       '&from=2026-10-14T00:00:00Z', '&from=2026-10-13T12:00:00Z'):
            self.query(suffix=suffix, status=400)
        value = self.query().json['data']
        run_id = value['analysis_run_id']
        for suffix in ('&dimension=knowledge', '&from=2026-10-01T00:00:00Z', f'&analysis_run_id={run_id}'):
            self.call(self.student, 'GET', self.analytics_url + f'?analysis_run_id={run_id}' + suffix, status=400)
        self.restore('', status=400)
        self.restore(2**63, status=400)
        self.restore(999, status=404)
        other = self.call(self.admin, 'POST', '/courses',
                          {'title': 'other', 'teacher_id': self.teacher_id}, 201).json['data']['id']
        teacher_run = self.query(self.teacher).json['data']['analysis_run_id']
        self.call(self.teacher, 'GET', f'/courses/{other}/analytics?analysis_run_id={teacher_run}', status=404)
        with closing(connect(self.path)) as db:
            db.execute("UPDATE analysis_run SET kind='warning' WHERE id=?", (run_id,))
        self.restore(run_id, status=404)
        with closing(connect(self.path)) as db:
            db.execute('DELETE FROM analysis_run WHERE id=?', (teacher_run,))
        self.restore(teacher_run, self.teacher, 404)

    def test_failed_insert_or_result_save_rolls_back_no_id(self):
        for operation in ('INSERT', 'UPDATE'):
            with closing(connect(self.path)) as db:
                db.execute(f'CREATE TRIGGER fail BEFORE {operation} ON analysis_run '
                           "BEGIN SELECT RAISE(ABORT,'injected snapshot failure'); END")
            response = self.query(status=503)
            self.assertNotIn('analysis_run_id', response.json)
            self.assertEqual(self.count_runs(), 0)
            with closing(connect(self.path)) as db:
                db.execute('DROP TRIGGER fail')
        self.query()
        self.assertEqual(self.count_runs(), 1)

    def test_revocation_during_calculation_prevents_snapshot_save(self):
        calculate = model.calculate

        def revoke(*args):
            with ThreadPoolExecutor(1) as pool:
                pool.submit(self.call, self.teacher, 'DELETE',
                            f'/courses/{self.course_id}/members/{self.student_id}', None, 204).result()
            return calculate(*args)

        with patch.object(model, 'calculate', revoke):
            self.query(status=404)
        self.assertEqual(self.count_runs(), 0)

    def test_session_deactivation_during_calculation_prevents_save(self):
        calculate = model.calculate

        def deactivate(*args):
            with ThreadPoolExecutor(1) as pool:
                pool.submit(self.call, self.admin, 'PATCH', f'/users/{self.student_id}', {'active': False}).result()
            return calculate(*args)

        with patch.object(model, 'calculate', deactivate):
            self.query(status=401)
        self.assertEqual(self.count_runs(), 0)

    def test_snapshot_backup_restore_and_public_runner_replay(self):
        self.progress(1)
        original = self.query().json['data']
        migrate(self.path)
        backup = self.path.with_name('backup.db')
        with closing(connect(self.path)) as db, closing(connect(backup)) as target:
            db.backup(target)
            self.assertEqual(target.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(target.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.app.config['DATABASE_PATH'] = str(backup)
        self.assertEqual(self.restore(original['analysis_run_id']).json['data'], original)

    def test_compute_or_missing_fact_dependency_failure_does_not_create_run(self):
        with patch.object(model, 'calculate', side_effect=RuntimeError('injected calculation failure')):
            self.query(status=503)
        self.assertEqual(self.count_runs(), 0)
        with closing(connect(self.path)) as db:
            db.execute('ALTER TABLE practice_attempt RENAME TO unavailable_practice')
        self.query(status=503)
        self.assertEqual(self.count_runs(), 0)

    def test_read_transaction_freezes_knowledge_progress_and_objective_samples(self):
        q = self.create_question(practice_available=True)
        self.practice(q, 'A')
        self.progress(1)
        self.at(13)
        with closing(connect(self.path)) as db:
            db.execute('PRAGMA journal_mode=WAL')
        extract = model.extract

        def concurrent_read(db, *args):
            triggered = False

            def trace(sql):
                nonlocal triggered
                if sql.startswith('WITH samples') and not triggered:
                    triggered = True
                    with ThreadPoolExecutor(1) as pool:
                        pool.submit(self.point, 1, published=False).result()
                        pool.submit(self.practice, q, 'B').result()

            db.set_trace_callback(trace)
            try:
                value = extract(db, *args)
                self.assertTrue(triggered)
                return value
            finally:
                db.set_trace_callback(None)

        with patch.object(model, 'extract', concurrent_read):
            original = self.query().json['data']
        self.assertEqual(original['sample_size'], 1)
        self.assertEqual(original['metrics']['published_knowledge_count'], 2)
        self.assertEqual(original['metrics']['completed_knowledge_count'], 1)
        self.at(14)
        latest = self.query().json['data']
        self.assertEqual(latest['sample_size'], 2)
        self.assertEqual(latest['metrics']['published_knowledge_count'], 1)
        self.assertEqual(latest['metrics']['completed_knowledge_count'], 0)
        self.assertEqual(self.restore(original['analysis_run_id']).json['data'], original)

    def test_class_totals_include_historical_facts_but_self_snapshots_only_store_own_inputs(self):
        outsider_id = self.outsider.get('/api/v1/auth/session').json['data']['user']['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members',
                  {'user_id': outsider_id, 'member_role': 'student'}, 201)
        q = self.create_question(practice_available=True, knowledge_ids=[1, 2])
        self.practice(q, 'A')
        self.practice(q, 'B', client=self.outsider)
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{outsider_id}', status=204)
        self.at(13)
        value = self.query(self.teacher).json['data']
        self.assertEqual((value['sample_size'], value['metrics']['mastery']), (2, 0.5))
        own = self.query().json['data']
        self.assertEqual((own['sample_size'], own['metrics']['mastery']), (1, 1))
        with closing(connect(self.path)) as db:
            raw = json.loads(db.execute('SELECT input_snapshot_json FROM analysis_run WHERE id=?',
                                        (own['analysis_run_id'],)).fetchone()[0])
            self.assertEqual({row['student_id'] for row in raw['samples']}, {self.student_id})
