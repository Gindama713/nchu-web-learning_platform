"""C07 real 001/005/006 facts; dedicated 008 publication remains a separate dependency."""

import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch

from backend.apis.statistics_csv import cell
from backend.models import score_analysis as model
from backend.shared.db import connect, migrate
from tests import test_attempts


class ScoreAnalyticsTest(test_attempts.AttemptApiBase):
    create_question = test_attempts.KnowledgeFixtureAttemptTest.create_question
    make_paper = test_attempts.KnowledgeFixtureAttemptTest.make_paper
    at = test_attempts.KnowledgeFixtureAttemptTest.at
    answer = test_attempts.KnowledgeFixtureAttemptTest.answer

    def setUp(self):
        super().setUp()
        self.knowledge_fixture()
        self.analytics_url = f'/courses/{self.course_id}/analytics'

    def query(self, suffix='', client=None, status=200):
        return self.call(client or self.teacher, 'GET', self.analytics_url + '?dimension=scores' + suffix, status=status)

    def restore(self, run, client=None, status=200):
        return self.call(client or self.teacher, 'GET', self.analytics_url + f'?analysis_run_id={run}', status=status)

    def export(self, run, client=None, status=200, suffix=''):
        return self.call(client or self.teacher, 'GET', self.analytics_url +
                         f'/export?analysis_run_id={run}&format=csv' + suffix, status=status)

    def grade(self, attempt, q, score, revision=0):
        self.call(self.teacher, 'PATCH', f"/attempts/{attempt['id']}/manual-scores", {
            'revision': revision, 'items': [{'question_version_id': q['version_id'], 'score': score, 'comment': ''}]})

    def test_real_frozen_assignments_missing_partial_final_zero_and_recompute(self):
        short = self.create_question(type='short', options=[], answer='参考')
        missing, pending, zero = [self.make_paper([short], kind='homework', points=[10]) for _ in range(3)]
        self.at(13)
        attempt = self.submit(pending, [self.answer(short, '回答')]).json['data']
        self.submit(zero, [])
        self.at(14)
        old = self.query('&kind=homework').json['data']
        m = old['metrics']
        self.assertEqual([m[k] for k in ('expected_count', 'submitted_count', 'missing_count', 'partial_count',
                                        'graded_count', 'mean_score', 'mean_percentage')], [3, 2, 1, 1, 1, None, 0])
        self.assertEqual([b['count'] for b in m['score_bins']], [1, 0, 0, 0, 0])
        self.assertEqual(m['selected_paper_ids'], [missing, pending, zero])
        before = self.export(old['analysis_run_id']).data
        self.grade(attempt, short, 8)
        self.assertEqual(self.restore(old['analysis_run_id']).json['data'], old)
        self.assertEqual(self.export(old['analysis_run_id']).data, before)
        new = self.query('&kind=homework').json['data']
        self.assertEqual((new['metrics']['mean_percentage'], new['metrics']['partial_count']), (40, 0))
        single = self.query(f'&kind=homework&paper_id={pending}').json['data']
        self.assertEqual((single['metrics']['mean_score'], single['metrics']['mean_percentage']), (8, 80))
        with closing(connect(self.path)) as db:
            row = db.execute('SELECT * FROM analysis_run WHERE id=?', (old['analysis_run_id'],)).fetchone()
            raw, params = json.loads(row['input_snapshot_json']), json.loads(row['parameters_json'])
            self.assertEqual(model.calculate(raw, params['from'], params['to'], row['source_until'])['metrics'], m)
            self.assertNotIn('value_json', row['input_snapshot_json'])

    def test_real_percentage_edges_different_totals_and_half_open_paper_start(self):
        questions = [self.create_question(type='short', options=[], answer='参考') for _ in range(7)]
        papers = [self.make_paper([q], points=[total]) for q, total in
                  zip(questions, (10, 20, 10, 20, 10, 20, 10), strict=True)]
        self.at(13)
        for paper, short, percentage, total in zip(papers, questions, (0, 59.9, 60, 70, 80, 90, 100),
                                                   (10, 20, 10, 20, 10, 20, 10), strict=True):
            attempt = self.submit(paper, [self.answer(short, '回答')]).json['data']
            self.grade(attempt, short, round(percentage * total / 100, 2))
        self.at(14)
        data = self.query('&kind=exam&from=2026-10-13T13:00:00Z&to=2026-10-13T14:00:00Z').json['data']
        self.assertEqual(data['sample_size'], 7)  # Task start, not submission/grade date.
        self.assertEqual([b['count'] for b in data['metrics']['score_bins']], [2, 1, 1, 1, 2])
        self.assertIsNone(data['metrics']['mean_score'])
        self.assertEqual(data['metrics']['mean_percentage'], 65.7)
        self.assertEqual(sum(p['metrics']['expected_count'] for p in data['series']), 7)
        empty = self.query('&kind=exam&from=2026-10-13T12:00:00Z&to=2026-10-13T13:00:00Z').json['data']
        self.assertEqual(empty['metrics']['expected_count'], 0)
        self.assertIsNone(empty['metrics']['mean_percentage'])

    def test_exit_and_join_keep_frozen_denominator_and_self_inputs(self):
        q = self.create_question()
        first = self.make_paper([q], kind='homework')
        other = self.outsider.get('/api/v1/auth/session').json['data']['user']['id']
        self.call(self.teacher, 'POST', f'/courses/{self.course_id}/members',
                  {'user_id': other, 'member_role': 'student'}, 201)
        second = self.make_paper([q], kind='homework')
        self.at(13)
        self.submit(first, [self.answer(q, 'A')])
        self.submit(second, [], client=self.outsider)
        self.at(14)
        own = self.query('&kind=homework', self.student).json['data']
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{other}', status=204)
        data = self.query('&kind=homework').json['data']
        self.assertEqual((data['metrics']['expected_count'], data['metrics']['graded_count']), (3, 2))
        with closing(connect(self.path)) as db:
            raw = json.loads(db.execute('SELECT input_snapshot_json FROM analysis_run WHERE id=?',
                                        (own['analysis_run_id'],)).fetchone()[0])
            self.assertEqual({r['student_id'] for r in raw['assignments']}, {self.student_id})

    def test_empty_quiz_and_strict_filters_and_paper_access(self):
        self.assertIsNone(self.query('&kind=quiz').json['data']['metrics']['mean_percentage'])
        for suffix in ('', '&kind=all', '&kind=exam&kind=quiz', '&kind=exam&dimension=knowledge',
                       '&kind=exam&paper_id=', '&kind=exam&paper_id=9223372036854775808',
                       '&kind=exam&performance_paper_ids=1', '&kind=exam&from=', '&kind=exam&x=1',
                       '&kind=exam&student_id=', '&kind=exam&to=2099-01-01T00:00:00Z'):
            self.query(suffix, status=400)
        paper = self.make_paper([self.create_question()], kind='homework')
        self.query(f'&kind=exam&paper_id={paper}', status=404)
        self.query('&kind=exam&paper_id=999', status=404)
        self.query('&kind=exam&student_id=999', status=404)
        self.query('&kind=exam&student_id=999', self.student, 403)
        self.query('&kind=exam', self.outsider, 404)
        self.query('&kind=exam', self.app.test_client(), 401)

    def test_snapshot_export_permissions_revocation_kind_and_duplicate_parameters(self):
        teacher = self.query('&kind=exam').json['data']['analysis_run_id']
        student = self.query('&kind=exam', self.student).json['data']['analysis_run_id']
        self.restore(teacher, self.student, 404)
        self.export(student, self.student, 403)
        self.restore(student, status=404)
        for suffix in ('&kind=exam', '&format=csv', f'&analysis_run_id={teacher}', '&from=2026-01-01'):
            self.export(teacher, status=400, suffix=suffix)
        self.export(2**63, status=400)
        other_course = self.call(self.admin, 'POST', '/courses',
                                 {'title': 'other', 'teacher_id': self.teacher_id}, 201).json['data']['id']
        self.call(self.teacher, 'GET', f'/courses/{other_course}/analytics/export?analysis_run_id={teacher}&format=csv', status=404)
        selected = self.query(f'&kind=exam&student_id={self.student_id}').json['data']['analysis_run_id']
        self.call(self.teacher, 'DELETE', f'/courses/{self.course_id}/members/{self.student_id}', status=204)
        self.restore(selected, status=404)
        self.export(selected, status=404)
        self.restore(student, self.student, 404)
        with closing(connect(self.path)) as db:
            db.execute("UPDATE analysis_run SET kind='warning' WHERE id=?", (teacher,))
        self.export(teacher, status=404)
        with closing(connect(self.path)) as db:
            db.execute('DELETE FROM analysis_run WHERE id=?', (teacher,))
        self.restore(teacher, status=404)

    def test_failed_calculation_save_and_missing_dependency_leave_no_snapshot(self):
        for operation in ('INSERT', 'UPDATE'):
            with closing(connect(self.path)) as db:
                db.execute(f'CREATE TRIGGER fail BEFORE {operation} ON analysis_run '
                           "BEGIN SELECT RAISE(ABORT,'injected'); END")
            self.query('&kind=exam', status=503)
            with closing(connect(self.path)) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM analysis_run WHERE kind='scores'").fetchone()[0], 0)
                db.execute('DROP TRIGGER fail')
        with patch.object(model, 'calculate', side_effect=RuntimeError('injected')):
            self.query('&kind=exam', status=503)
        with closing(connect(self.path)) as db:
            db.execute('ALTER TABLE attempt RENAME TO unavailable_attempt')
        self.query('&kind=exam', status=503)

    def test_revoked_during_calculation_rolls_back_and_wal_reads_freeze_grades(self):
        q = self.create_question(type='short', options=[], answer='参考')
        paper = self.make_paper([q], points=[10])
        self.at(13)
        attempt = self.submit(paper, [self.answer(q, '回答')]).json['data']
        self.at(14)
        with closing(connect(self.path)) as db:
            db.execute('PRAGMA journal_mode=WAL')
        extract = model.extract

        def concurrent_read(db, *args):
            triggered = False

            def trace(sql):
                nonlocal triggered
                if sql.startswith('SELECT p.id paper_id') and not triggered:
                    triggered = True
                    with ThreadPoolExecutor(1) as pool:
                        pool.submit(self.grade, attempt, q, 8).result()

            db.set_trace_callback(trace)
            try:
                value = extract(db, *args)
                self.assertTrue(triggered)
                return value
            finally:
                db.set_trace_callback(None)

        with patch.object(model, 'extract', concurrent_read):
            old = self.query('&kind=exam').json['data']
        self.assertEqual(old['metrics']['partial_count'], 1)
        self.assertEqual(self.query('&kind=exam').json['data']['metrics']['mean_percentage'], 80)
        calculate = model.calculate

        def revoke(*args):
            with ThreadPoolExecutor(1) as pool:
                pool.submit(self.call, self.teacher, 'DELETE',
                            f'/courses/{self.course_id}/members/{self.student_id}', None, 204).result()
            return calculate(*args)

        with patch.object(model, 'calculate', revoke):
            self.query('&kind=exam', self.student, 404)

    def test_knowledge_csv_formula_escaping_and_backup_restore_original_id(self):
        title = '=HYPERLINK("https://invalid.example","x"),\n正文'
        self.call(self.teacher, 'PATCH', '/knowledge-points/1', {'title': title})
        data = self.call(self.teacher, 'GET', self.analytics_url + '?dimension=knowledge').json['data']
        run = data['analysis_run_id']
        original = self.export(run)
        self.assertEqual(original.headers['Cache-Control'], 'no-store')
        rows = list(csv.reader(io.StringIO(original.data.decode('utf-8-sig'))))
        self.assertIn(['item', '1', "'" + title, '0', '0', '0', ''], rows)
        migrate(self.path)
        backup = self.path.with_name('backup.db')
        with closing(connect(self.path)) as source, closing(connect(backup)) as target:
            source.backup(target)
            self.assertEqual(target.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(target.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.app.config['DATABASE_PATH'] = str(backup)
        self.assertEqual(self.restore(run).json['data'], data)
        self.assertEqual(self.export(run).data, original.data)

    def test_quiz_shared_service_fixture_scores_and_scores_backup_original_id(self):
        # 008 is unmerged. This calls the existing shared publish service, NOT its dedicated HTTP API.
        q = self.create_question()
        paper = self.make_paper([q], kind='quiz', points=[20], quiz_publish=True)
        self.at(13)
        self.submit(paper, [self.answer(q, 'A')])
        self.at(14)
        data = self.query('&kind=quiz').json['data']
        self.assertEqual((data['metrics']['expected_count'], data['metrics']['mean_score']), (1, 20))
        self.assertEqual(data['metrics']['score_bins'][-1]['count'], 1)
        run = data['analysis_run_id']
        csv_bytes = self.export(run).data
        with closing(connect(self.path)) as source, closing(connect(self.path.with_name('scores-backup.db'))) as target:
            source.backup(target)
            self.assertEqual(target.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(target.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.app.config['DATABASE_PATH'] = str(self.path.with_name('scores-backup.db'))
        self.assertEqual(self.restore(run).json['data'], data)
        self.assertEqual(self.export(run).data, csv_bytes)

    def test_csv_prefixes_and_account_deactivation_during_compute_and_export(self):
        for value in ('=1', '+cmd', '-1', '@SUM(1)', '\ttext', '\rtext', '\ntext', '  =SUM(1)'):
            self.assertEqual(cell(value), "'" + value)
        self.assertEqual(cell('教学,正文\n第二行'), '教学,正文\n第二行')
        self.assertEqual(cell(None), '')
        self.assertEqual(cell(0), 0)
        run = self.query('&kind=exam', self.student).json['data']['analysis_run_id']
        calculate = model.calculate

        def deactivate(*args):
            with ThreadPoolExecutor(1) as pool:
                pool.submit(self.call, self.admin, 'PATCH', f'/users/{self.student_id}', {'active': False}).result()
            return calculate(*args)

        with patch.object(model, 'calculate', deactivate):
            self.query('&kind=exam', self.student, 401)
        self.export(run, self.student, 401)
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM analysis_run WHERE kind='scores'").fetchone()[0], 1)
