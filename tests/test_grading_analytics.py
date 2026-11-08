"""T010D 真实 API 集成：SPEC-010D 电路评测统计（教学分布 + 运行可靠性）。

只使用真实 HTTP 处理与真实 grading_run 事实表；worker 结果经引擎自身的
claim/submit 租约路径注入（不是 API mock）。真实 Logisim JAR 的 TV-01 由
SPEC-018 人工执行，本文件只证明统计读取真实事实而不硬编码样例数字。

覆盖来源（PRD 第 13 节 SPEC-010D 有效验收表）：
- SPEC-010/AC-01 → test_teaching_distribution_matches_prd_sample_and_recomputes
- SPEC-010/AC-02 → test_scope_permissions_and_invisible_objects
- SPEC-010/AC-03 → test_empty_sample_keeps_null_metrics_and_saves_snapshot
- SPEC-010/AC-04 → test_snapshot_and_csv_frozen_across_regrade
- R05 → test_timeout_and_resource_limit_zero_but_system_error_excluded
- R16 → test_member_exit_keeps_historical_denominator
- R19 → test_queued_and_system_error_do_not_replace_effective_score
- R29 → test_expired_lease_worker_lost_leaves_teaching_denominator
- R30 → test_statistics_project_real_facts_not_hardcoded
"""

import csv
import io
import json
from contextlib import closing

from backend.engines import grading as engine
from backend.models import grading_analysis as model
from backend.shared.db import connect
from tests import test_grading


class GradingAnalyticsTest(test_grading.GradingFixture):
    def setUp(self):
        super().setUp()
        self.analytics_url = f'{self.course}/analytics'
        self.students = [self.student, self.student2]
        for number in ('T010DST4', 'T010DST5', 'T010DST6'):
            client = self.app.test_client()
            self.call(client, 'POST', '/auth/register',
                      {'student_no': number, 'name': number, 'password': self.password}, 201)
            self.login(client, number)
            self.call(self.teacher, 'POST', f'{self.course}/members',
                      {'user_id': self._uid(client), 'member_role': 'student'}, 201)
            self.students.append(client)

    # ---------- 辅助 ----------

    def query(self, suffix='', client=None, status=200):
        return self.call(client or self.teacher, 'GET',
                         self.analytics_url + '?dimension=grading' + suffix, status=status)

    def restore(self, run, client=None, status=200):
        return self.call(client or self.teacher, 'GET',
                         self.analytics_url + f'?analysis_run_id={run}', status=status)

    def export(self, run, client=None, status=200, suffix=''):
        return self.call(client or self.teacher, 'GET',
                         self.analytics_url + f'/export?analysis_run_id={run}&format=csv' + suffix,
                         status=status)

    def submit_and_finish(self, client, passed=8, error=None):
        """提交后立刻经真实 worker 路径完成，保证 claim 顺序与提交顺序一致。"""
        data = self.submit(client)
        self.finish_run(data['run_id'], passed, error)
        return data

    def snapshot_of(self, run_id):
        with closing(connect(self.path)) as db:
            row = db.execute('SELECT * FROM analysis_run WHERE id=?', (run_id,)).fetchone()
            return json.loads(row['input_snapshot_json']), json.loads(row['parameters_json'])

    def csv_rows(self, run_id):
        return list(csv.reader(io.StringIO(self.export(run_id).data.decode('utf-8-sig'))))

    # ---------- AC-01 可复算 / PRD §4.1 样例 ----------

    def test_teaching_distribution_matches_prd_sample_and_recomputes(self):
        # 覆盖 SPEC-010/AC-01 与 PRD §4.1 样例：5 名学生各自有效成绩中 2 名 accepted，
        # 教学通过率 40%；同一筛选条件用保存快照可复算出同一结果。
        _version, _suite, _published = self.publish_circuit()
        for index, client in enumerate(self.students):
            self.submit_and_finish(client, passed=8 if index < 2 else 3)
        data = self.query().json['data']
        metrics = data['metrics']
        self.assertEqual((metrics['student_count'], metrics['effective_count'],
                          metrics['accepted_count'], metrics['pass_rate']), (5, 5, 2, 0.4))
        self.assertEqual(metrics['submission_count'], 5)
        self.assertEqual(metrics['run_count'], 5)
        self.assertEqual((metrics['system_error_count'], metrics['timeout_count'],
                          metrics['resource_limit_count']), (0, 0, 0))
        self.assertEqual(data['sample_size'], 5)
        self.assertEqual(data['dimension'], 'grading')
        self.assertEqual(len(metrics['selected_version_ids']), 1)
        self.assertEqual(len(metrics['suites']), 1)
        self.assertEqual(metrics['suites'][0]['effective_count'], 5)

        raw, parameters = self.snapshot_of(data['analysis_run_id'])
        again = model.calculate(raw, parameters['from'], parameters['to'],
                                self.restore(data['analysis_run_id']).json['data']['source_until'])
        self.assertEqual(again['metrics'], metrics)
        self.assertEqual(again['series'], data['series'])

    # ---------- AC-02 权限与不可见对象 ----------

    def test_scope_permissions_and_invisible_objects(self):
        # 覆盖 SPEC-010/AC-02：学生仅看自己，教师仅看本班；非成员/他课教师/非创建者统一 404，
        # 学生调用教师导出 403。
        self.publish_circuit()
        for client in self.students:
            self.submit_and_finish(client, passed=8)
        class_scope = self.query().json['data']
        own = self.query(client=self.student).json['data']
        self.assertEqual((class_scope['metrics']['student_count'],
                          own['metrics']['student_count']), (5, 1))
        self.assertEqual(own['filters']['student_id'], self._uid(self.student))
        self.query(f'&student_id={self._uid(self.student2)}', self.student, 403)
        selected = self.query(f'&student_id={self._uid(self.student2)}').json['data']
        self.assertEqual(selected['metrics']['student_count'], 1)
        self.query('', self.student3, 404)
        self.query('', self.teacher2, 404)
        self.query('', self.app.test_client(), 401)
        self.restore(class_scope['analysis_run_id'], self.student, 404)
        self.export(own['analysis_run_id'], self.student, 403)
        self.export(class_scope['analysis_run_id'], self.student, 403)
        other_course = self.call(self.admin, 'POST', '/courses',
                                 {'title': '010D other', 'teacher_id': self._uid(self.teacher2)},
                                 201).json['data']['id']
        self.call(self.teacher, 'GET',
                  f'/courses/{other_course}/analytics/export?analysis_run_id='
                  f'{class_scope["analysis_run_id"]}&format=csv', status=404)

    # ---------- AC-03 空样本 ----------

    def test_empty_sample_keeps_null_metrics_and_saves_snapshot(self):
        # 覆盖 SPEC-010/AC-03：空样本计数为 0、比率与均分为 null，仍保存合法快照。
        data = self.query().json['data']
        metrics = data['metrics']
        self.assertEqual((metrics['student_count'], metrics['submission_count'],
                          metrics['effective_count'], metrics['run_count']), (0, 0, 0, 0))
        self.assertIsNone(metrics['pass_rate'])
        self.assertIsNone(metrics['mean_score'])
        self.assertEqual([item['count'] for item in metrics['score_bins']], [0, 0, 0, 0, 0])
        self.assertEqual(metrics['suites'], [])
        self.assertEqual(data['sample_size'], 0)
        self.assertEqual(self.restore(data['analysis_run_id']).json['data'], data)
        # 日期区间外/空区间也保存合法快照。
        outside = self.query('&from=2026-08-01T00:00:00Z&to=2026-08-02T00:00:00Z').json['data']
        self.assertEqual(outside['metrics']['effective_count'], 0)

    # ---------- AC-04 快照与导出一致 ----------

    def test_snapshot_and_csv_frozen_across_regrade(self):
        # 覆盖 SPEC-010/AC-04：导出与页面使用同一 analysis_run_id 快照；重评后旧快照
        # 与旧 CSV 不变，只有新查询才反映更正。
        _version, _suite, _published = self.publish_circuit()
        submission = self.submit_and_finish(self.student, passed=3)
        first = self.query().json['data']
        csv_before = self.export(first['analysis_run_id']).data
        self.assertEqual(first['metrics']['accepted_count'], 0)
        self.assertEqual(first['metrics']['pass_rate'], 0)
        regrade = self.call(self.teacher, 'POST',
                            f'/submissions/{submission["submission_id"]}/regrades',
                            {'reason': '复核接线后重评'}, 202,
                            headers_extra={'Idempotency-Key': '9f1c4a2e-010d-4b6d-8a51-2c7e6f0a1b23'}
                            ).json['data']
        self.finish_run(regrade['run_id'], 8)
        self.assertEqual(self.restore(first['analysis_run_id']).json['data'], first)
        self.assertEqual(self.export(first['analysis_run_id']).data, csv_before)
        refreshed = self.query().json['data']
        self.assertEqual((refreshed['metrics']['accepted_count'],
                          refreshed['metrics']['pass_rate']), (1, 1))
        rows = self.csv_rows(refreshed['analysis_run_id'])
        self.assertIn(['dimension', 'grading'], rows)
        self.assertIn(['analysis_run_id', str(refreshed['analysis_run_id'])], rows)
        self.assertEqual(rows[0][0], 'analysis_run_id')
        header = next(row for row in rows if row[0] == 'suites')
        self.assertEqual(header[1], 'suite_id')
        self.assertEqual(len([row for row in rows if row[0] == 'suite']), 1)
        self.assertEqual(len([row for row in rows if row[0] == 'overall_bin']), 5)
        self.assertEqual(self.export(first['analysis_run_id']).headers['Cache-Control'], 'no-store')

    # ---------- R05 结果优先级 ----------

    def test_timeout_and_resource_limit_zero_but_system_error_excluded(self):
        # 覆盖 R05：超时与内存/输出限额计 0 分且进入教学分母；平台故障 score=null，
        # 只进可靠性计数、不扣学生分也不覆盖既有有效成绩。
        self.publish_circuit()
        self.submit_and_finish(self.student, passed=8)
        self.submit_and_finish(self.student2, passed=0, error='TIME_LIMIT')
        self.submit_and_finish(self.student2, passed=0, error='OUTPUT_LIMIT')
        self.submit_and_finish(self.students[2], passed=0, error='MEMORY_LIMIT')
        self.submit_and_finish(self.students[3], passed=0, error='ENGINE_CRASH')
        self.submit_and_finish(self.students[4], passed=8)
        self.submit_and_finish(self.students[4], passed=0, error='ENGINE_CRASH')
        metrics = self.query().json['data']['metrics']
        self.assertEqual((metrics['student_count'], metrics['effective_count'],
                          metrics['accepted_count']), (4, 4, 2))
        self.assertEqual(metrics['pass_rate'], 0.5)
        self.assertEqual((metrics['run_count'], metrics['system_error_count'],
                          metrics['timeout_count'], metrics['resource_limit_count']), (7, 2, 1, 2))
        # 100、0、0、100：故障的 0 分不覆盖 student4 既有的 accepted。
        self.assertEqual(metrics['mean_score'], 50.0)
        self.assertEqual([item['count'] for item in metrics['score_bins']], [2, 0, 0, 0, 2])

    # ---------- R16 冻结名单 ----------

    def test_member_exit_keeps_historical_denominator(self):
        # 覆盖 R16：退出成员的成绩仍是历史事实，分母不漂移；教师新查询不重算掉已退出学生。
        self.publish_circuit()
        for client in self.students:
            self.submit_and_finish(client, passed=8)
        before = self.query().json['data']['metrics']
        self.call(self.teacher, 'DELETE', f'{self.course}/members/{self._uid(self.students[-1])}',
                  status=204)
        after = self.query().json['data']['metrics']
        self.assertEqual((after['student_count'], after['effective_count'],
                          after['accepted_count'], after['pass_rate']), (5, 5, 5, 1))
        self.assertEqual((before['student_count'], before['effective_count']), (5, 5))
        self.query('', self.students[-1], 404)

    # ---------- R19 有效成绩 ----------

    def test_queued_and_system_error_do_not_replace_effective_score(self):
        # 覆盖 R19：新 run 排队/故障不覆盖旧有效分；同 submission 仅一个活动 run；
        # latest 待评不等于教学成绩。
        self.publish_circuit()
        self.submit_and_finish(self.student, passed=8)
        queued = self.submit(self.student)
        metrics = self.query().json['data']['metrics']
        self.assertEqual((metrics['effective_count'], metrics['accepted_count']), (1, 1))
        self.assertEqual(metrics['run_count'], 2)
        detail = self.call(self.student, 'GET', f'/submissions/{queued["submission_id"]}').json['data']
        self.assertEqual(detail['latest_run']['status'], 'queued')
        self.assertIsNone(detail['latest_run']['score'])
        self.assertIsNone(detail['effective_run'])
        # 同 submission 只有一条活动 run。
        with closing(connect(self.path)) as db:
            active = db.execute('SELECT count(*) FROM grading_run WHERE submission_id=? '
                                "AND status IN ('queued','running')",
                                (queued['submission_id'],)).fetchone()[0]
        self.assertEqual(active, 1)

    # ---------- R29 租约过期 ----------

    def test_expired_lease_worker_lost_leaves_teaching_denominator(self):
        # 覆盖 R29：达到 lease_until 后旧 worker 续租/提交均失败，回收为 system_error，
        # 不进入教学分母；另一学生的有效成绩不受影响。
        self.publish_circuit()
        self.submit_and_finish(self.student, passed=8)
        pending = self.submit(self.student2)
        with closing(connect(self.path)) as db:
            db.execute('BEGIN IMMEDIATE')
            claimed = engine.claim_run(db, test_grading.TEST_NOW)
            db.commit()
        self.assertEqual(claimed['id'], pending['run_id'])
        token = claimed['worker_token']
        with closing(connect(self.path)) as db:
            db.execute('BEGIN IMMEDIATE')
            expired = db.execute("UPDATE grading_run SET lease_until='2000-01-01T00:00:00Z' "
                                 'WHERE id=?', (pending['run_id'],)).rowcount
            db.commit()
        self.assertEqual(expired, 1)
        with closing(connect(self.path)) as db:
            db.execute('BEGIN IMMEDIATE')
            self.assertFalse(engine.renew_lease(db, pending['run_id'], token, test_grading.TEST_NOW))
            engine.reclaim_expired(db, test_grading.TEST_NOW)
            db.commit()
        with closing(connect(self.path)) as db:
            db.execute('BEGIN IMMEDIATE')
            self.assertFalse(engine.submit_run_result(db, pending['run_id'], token,
                                                      test_grading.TEST_NOW, None, []))
            db.commit()
        metrics = self.query().json['data']['metrics']
        self.assertEqual((metrics['effective_count'], metrics['accepted_count']), (1, 1))
        self.assertEqual(metrics['system_error_count'], 1)
        self.assertEqual(metrics['run_count'], 2)

    # ---------- R30 真实事实 ----------

    def test_statistics_project_real_facts_not_hardcoded(self):
        # 覆盖 R30：统计只投影真实 grading_run 事实；直接改事实表后新查询随之变化，
        # 证明数字不来自样例常量（真实 JAR 的 TV-01 仍由 018 人工执行）。
        self.publish_circuit()
        submission = self.submit_and_finish(self.student, passed=8)
        self.assertEqual(self.query().json['data']['metrics']['mean_score'], 100.0)
        with closing(connect(self.path)) as db:
            db.execute("UPDATE grading_run SET status='wrong_answer', score_hundredths=5000 "
                       'WHERE id=?', (submission['run_id'],))
        metrics = self.query().json['data']['metrics']
        self.assertEqual((metrics['accepted_count'], metrics['mean_score'],
                          metrics['pass_rate']), (0, 50.0, 0))

    # ---------- 参数与依赖 ----------

    def test_strict_filters_duplicates_and_missing_dependency(self):
        for suffix in ('&student_id=', '&x=1', '&from=', '&to=2099-01-01T00:00:00Z',
                       '&dimension=knowledge', '&student_id=9223372036854775808'):
            self.query(suffix, status=400)
        self.query('', self.student3, 404)
        self.restore('0', status=400)
        self.restore('999', status=404)
        self.export(999, status=404)
        for suffix in ('&dimension=grading', '&format=csv', '&from=2026-01-01'):
            self.export(1, status=400, suffix=suffix)
        with closing(connect(self.path)) as db:
            db.execute('ALTER TABLE grading_run RENAME TO unavailable_run')
        self.query('', status=503)
