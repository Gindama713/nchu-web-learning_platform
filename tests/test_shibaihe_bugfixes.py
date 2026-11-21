"""石佰合负责模块遗留缺陷回归测试（SPEC-003 / SPEC-009 / SPEC-018 / SPEC-010D）。

对应 docs/bug-review-2026-10-26.md 与 docs/cross-module-bug-review-2026-10-28.md 中
归属 SPEC-003 / SPEC-010D / SPEC-018 的 7 项缺陷。他人模块（SPEC-004/006/008/017/010A）
不在本文件覆盖范围，也不在本轮改动范围内。
"""

import ast
import csv
import io
import sqlite3
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from flask import Flask

from backend.apis import resources, statistics_csv
from backend.models import question as question_model
from backend.shared.db import connect
from tests.test_resources import (
    ResourceImportTest,
    ResourcesTest,
    bank_question,
    make_pdf,
)


class _RacingWrite:
    """模拟并发写入：另一个连接抢先插入同键事件后，本连接命中 UNIQUE 冲突。"""

    def __init__(self, insert):
        self.insert = insert

    def __enter__(self):
        self.insert()
        raise sqlite3.IntegrityError(
            "UNIQUE constraint failed: resource_event.user_id, resource_event.event_id")

    def __exit__(self, *_exc):
        return False


class ResourceBugfixTest(ResourcesTest):
    """SPEC-003：错误码、备课表缺失降级、访问事件竞态。"""

    def test_p2_question_bank_preview_uses_resource_error_code(self):
        """题库预览被拒时应返回资源语义错误码，而非电路模块的 INVALID_CIRCUIT。"""
        uploaded = self._upload(self.teacher, self.course_id,
                                self._bank_json(), "题库", "question_bank")
        vid = uploaded.json["data"]["id"]
        resp = self._content(self.teacher, vid, "view", "evt-bank-view")
        self.assertEqual(resp.status_code, 422, resp.json)
        self.assertEqual(resp.json["error"]["code"], "UNSUPPORTED_OPERATION", resp.json)

    def _bank_json(self):
        bio = io.BytesIO(b'[{"stem":"q"}]')
        bio.name = "bank.json"
        return bio

    def test_p1_missing_preparation_tables_degrades_gracefully(self):
        """SPEC-004 尚未安装时，修改可见性不应因缺表抛 sqlite3.OperationalError。"""
        uploaded = self._upload(self.teacher, self.course_id,
                                make_pdf("p.pdf"), "课件", "slides")
        rid = uploaded.json["data"]["resource_id"]
        db = connect(self.path)
        try:
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute("DROP TABLE preparation_resource")
            db.execute("DROP TABLE preparation")
            db.commit()
        finally:
            db.close()
        resp = self._call(self.teacher, "PATCH", f"/api/v1/resources/{rid}",
                          {"visibility": "teacher_only"})
        self.assertEqual(resp.status_code, 200, resp.json)
        self.assertEqual(resp.json["data"]["visibility"], "teacher_only")

    def _insert_event(self, event_id, intent, version_id):
        def insert():
            db = connect(self.path)
            try:
                uid = db.execute(
                    "SELECT id FROM user WHERE student_no='STUD0001'").fetchone()[0]
                db.execute(
                    "INSERT INTO resource_event(user_id,resource_version_id,event_type,event_id,"
                    "request_id,created_at) VALUES(?,?,?,?,?,?)",
                    (uid, version_id, intent, event_id, "race-request",
                     "2026-11-09T00:00:00Z"))
                db.commit()
            finally:
                db.close()
        return insert

    def test_p2_event_race_same_intent_is_idempotent(self):
        """并发抢先插入同 intent/version 时，UNIQUE 冲突降级为幂等成功而非 500。"""
        uploaded = self._upload(self.teacher, self.course_id,
                                make_pdf("r.pdf"), "竞态课件", "slides")
        vid = uploaded.json["data"]["id"]
        eid = "evt-race-same"
        insert = self._insert_event(eid, "view", vid)
        with patch.object(resources, "write", return_value=_RacingWrite(insert)):
            resp = self._content(self.student, vid, "view", eid)
        self.assertIn(resp.status_code, (200, 206), resp.data[:200])

    def test_p2_event_race_different_intent_is_409(self):
        """并发抢先插入不同 intent 时，UNIQUE 冲突应明确返回 409 EVENT_CONFLICT。"""
        uploaded = self._upload(self.teacher, self.course_id,
                                make_pdf("r2.pdf"), "竞态课件2", "slides")
        vid = uploaded.json["data"]["id"]
        eid = "evt-race-diff"
        insert = self._insert_event(eid, "view", vid)
        with patch.object(resources, "write", return_value=_RacingWrite(insert)):
            resp = self._content(self.student, vid, "download", eid)
        self.assertEqual(resp.status_code, 409, resp.json)
        self.assertEqual(resp.json["error"]["code"], "EVENT_CONFLICT", resp.json)


class ResourceImportBugfixTest(ResourceImportTest):
    """SPEC-003 题库导入：前置依赖检查与重复知识校验。"""

    def _bank_resource(self, questions):
        uploaded = self._upload(self.teacher, self.course_id, self._bank(questions),
                                "前置检查题库", "question_bank")
        self.assertEqual(uploaded.status_code, 201, uploaded.json)
        return uploaded.json["data"]["resource_id"], uploaded.json["data"]["id"]

    def _drop_table(self, name):
        statements = {'chapter': 'DROP TABLE chapter',
                      'paper_item': 'DROP TABLE paper_item'}
        db = connect(self.path)
        try:
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute(statements[name])
            db.commit()
        finally:
            db.close()

    def test_p1_import_requires_knowledge_tables_up_front(self):
        """知识模块缺表时应在前置检查返回 503，而不是创建题目时才失败。"""
        rid, vid = self._bank_resource([bank_question()])
        self._drop_table("chapter")
        resp = self._import(self.teacher, rid, vid)
        self.assertEqual(resp.status_code, 503, resp.json)
        self.assertEqual(resp.json["error"]["code"], "DEPENDENCY_UNAVAILABLE", resp.json)
        self.assertIn("题库或知识模块", resp.json["error"]["message"])

    def test_p1_import_requires_paper_tables_for_practice(self):
        """含公开练习题时，试卷模块缺表应由导入前置检查明确拒绝。"""
        rid, vid = self._bank_resource([bank_question(practice_available=True)])
        self._drop_table("paper_item")
        resp = self._import(self.teacher, rid, vid)
        self.assertEqual(resp.status_code, 503, resp.json)
        self.assertEqual(resp.json["error"]["code"], "DEPENDENCY_UNAVAILABLE", resp.json)
        self.assertIn("随堂测模块", resp.json["error"]["message"])

    def test_p2_check_knowledge_called_once_per_question(self):
        """知识归属校验只由 save_version 执行一次，不再每题重复两次。"""
        rid, vid = self._bank_resource([bank_question(),
                                        bank_question(stem="第二题题干？")])
        with patch.object(question_model, "check_knowledge",
                          wraps=question_model.check_knowledge) as spy:
            resp = self._import(self.teacher, rid, vid)
        self.assertEqual(resp.status_code, 201, resp.json)
        self.assertEqual(spy.call_count, 2)


def _csv_payload(dimension, series_selector=True):
    series_metrics = {'pass_rate': 0.5, 'items': [], 'score_bins': [], 'suites': []}
    if series_selector:
        series_metrics['selected_version_ids'] = [7]
    return {
        'analysis_run_id': 1,
        'dimension': dimension,
        'source_until': '2026-11-09T00:00:00Z',
        'generated_at': '2026-11-09T00:00:01Z',
        'algorithm_version': 'v1',
        'sample_size': 1,
        'population_basis': 'all',
        'unit': 'student',
        'warnings': [],
        'filters': {},
        'metrics': {'pass_rate': 0.5, 'selected_version_ids': [7],
                    'items': [], 'score_bins': [], 'suites': []},
        'series': [{'period_start': '2026-01-01', 'period_end': '2026-01-08',
                    'metrics': series_metrics}],
    }


def _csv_header(dimension, series_selector=True):
    app = Flask(__name__)
    with app.test_request_context():
        response = statistics_csv.response(_csv_payload(dimension, series_selector))
    rows = list(csv.reader(io.StringIO(response.data.decode('utf-8-sig'))))
    return next(row for row in rows if row[0] == 'section')


class CsvBugfixTest(TestCase):
    """SPEC-010D：grading 维度 CSV 不应把筛选条件快照当成指标列。"""

    def test_p2_grading_csv_excludes_selected_version_ids(self):
        """真实快照里 series 通常不带筛选字段，原实现会 KeyError；修复后正常导出。"""
        header = _csv_header('grading', series_selector=False)
        self.assertNotIn('selected_version_ids', header)
        self.assertIn('pass_rate', header)

    def test_p2_other_dimensions_csv_unchanged(self):
        """只修 grading 维度，其他维度列集合保持不变（不触碰他人模块行为）。"""
        header = _csv_header('scores')
        self.assertIn('selected_version_ids', header)
        self.assertIn('pass_rate', header)


class GradingCleanupTest(TestCase):
    """SPEC-018：模块顶部已导入 now，函数内不应再有重复局部导入。"""

    def test_p2_no_redundant_local_import(self):
        source = Path(__file__).resolve().parents[1] / 'backend' / 'apis' / 'grading.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        nested = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    if (isinstance(child, ast.ImportFrom)
                            and child.module == 'backend.shared.api'
                            and any(alias.name == 'now' for alias in child.names)):
                        nested.append(child.lineno)
        self.assertEqual(nested, [])
