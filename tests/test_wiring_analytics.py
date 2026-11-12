"""SPEC-010C 连线统计：完成率与错误去重。"""

import csv
import io
import json
from datetime import UTC, datetime
from unittest import TestCase

from backend.apis.analytics import wiring_interval_metrics
from tests.test_wiring import WiringApiBase

START = "2026-10-01T00:00:00.000Z"
END = "2026-11-01T00:00:00.000Z"


def snapshot(assigned=10, completed=6, attempts=8, error_codes=None, dup_attempt=None):
    """构造连线统计快照。

    assigned: 分配人数(experiment_participant 去重)
    completed: 功能全过人数
    attempts: 提交次数
    error_codes: 错误码列表，每个对应一次 validation 记录
    dup_attempt: (attempt_id, revision, code) 重复项，验证去重
    """
    versions = [{"id": 1, "submission_modes_json": '["wiring"]', "end_at": "2026-10-15T00:00:00.000Z"}]
    participants = [{"experiment_version_id": 1, "student_id": i} for i in range(1, assigned + 1)]
    attempt_rows = []
    for i in range(1, attempts + 1):
        sid = ((i - 1) % assigned) + 1 if assigned else i
        attempt_rows.append({
            "id": i, "experiment_version_id": 1, "student_id": sid,
            "status": "submitted", "completed": 1 if i <= completed else 0,
        })
    validations = []
    for idx, code in enumerate(error_codes or [], 1):
        validations.append({"attempt_id": idx, "revision": idx,
                            "errors_json": f'[{{"code":"{code}","message":"x"}}]'})
    if dup_attempt:
        aid, rev, code = dup_attempt
        validations.append({"attempt_id": aid, "revision": rev,
                            "errors_json": f'[{{"code":"{code}","message":"dup"}}]'})
    return {"versions": versions, "participants": participants,
            "attempts": attempt_rows, "validations": validations}


class WiringMetricsTest(TestCase):
    def test_completion_rate(self):
        # 10 人布置，6 人提交功能全过 → 完成率 0.6
        value = wiring_interval_metrics(snapshot(assigned=10, completed=6), START, END)
        self.assertEqual(value["assigned_count"], 10)
        self.assertEqual(value["completed_student_count"], 6)
        self.assertEqual(value["completion_rate"], 0.6)
        self.assertEqual(value["attempt_count"], 8)

    def test_draft_not_counted(self):
        # 草稿不计入完成；仅 submitted 计 attempt
        snap = snapshot(assigned=10, completed=0, attempts=0)
        snap["attempts"] = [{"id": 1, "experiment_version_id": 1, "student_id": 1,
                             "status": "draft", "completed": 0}]
        value = wiring_interval_metrics(snap, START, END)
        self.assertEqual(value["completed_student_count"], 0)
        self.assertEqual(value["attempt_count"], 0)

    def test_error_dedup_by_attempt_revision_code(self):
        # 同一 attempt/revision/code 重复出现只计一次
        value = wiring_interval_metrics(
            snapshot(error_codes=["OUTPUT_CONFLICT", "WIDTH_MISMATCH"],
                     dup_attempt=(1, 1, "OUTPUT_CONFLICT")),
            START, END)
        self.assertEqual(value["error_counts"]["OUTPUT_CONFLICT"], 1)
        self.assertEqual(value["error_counts"]["WIDTH_MISMATCH"], 1)

    def test_different_revision_counts_separately(self):
        # 同一 attempt 不同 revision 的同 code 计两次
        snap = snapshot(error_codes=[])
        snap["validations"] = [
            {"attempt_id": 1, "revision": 1, "errors_json": '[{"code":"SELF_CONNECTION"}]'},
            {"attempt_id": 1, "revision": 2, "errors_json": '[{"code":"SELF_CONNECTION"}]'},
        ]
        value = wiring_interval_metrics(snap, START, END)
        self.assertEqual(value["error_counts"]["SELF_CONNECTION"], 2)

    def test_no_assigned_returns_null_rate(self):
        value = wiring_interval_metrics(snapshot(assigned=0, completed=0), START, END)
        self.assertEqual(value["assigned_count"], 0)
        self.assertIsNone(value["completion_rate"])

    def test_errors_attributed_to_version_interval(self):
        # v1 截止 10-15（在 10 月区间），v2 截止 11-15（在 11 月区间）；
        # 错误必须随版本 end_at 落入对应区间，不能每周重复计数
        snap = snapshot(assigned=0, completed=0, attempts=0, error_codes=[])
        snap["versions"] = [
            {"id": 1, "submission_modes_json": '["wiring"]', "end_at": "2026-10-15T00:00:00.000Z"},
            {"id": 2, "submission_modes_json": '["wiring"]', "end_at": "2026-11-15T00:00:00.000Z"},
        ]
        snap["participants"] = [
            {"experiment_version_id": 1, "student_id": 1},
            {"experiment_version_id": 2, "student_id": 1},
        ]
        snap["attempts"] = [
            {"id": 1, "experiment_version_id": 1, "student_id": 1, "status": "draft", "completed": 0},
            {"id": 2, "experiment_version_id": 2, "student_id": 1, "status": "draft", "completed": 0},
        ]
        snap["validations"] = [
            {"attempt_id": 1, "revision": 1, "errors_json": '[{"code":"REQUIRED_OPEN"}]'},
            {"attempt_id": 2, "revision": 1, "errors_json": '[{"code":"WIDTH_MISMATCH"}]'},
        ]
        october = wiring_interval_metrics(snap, START, END)
        self.assertEqual(october["error_counts"], {"REQUIRED_OPEN": 1})
        november = wiring_interval_metrics(snap, "2026-11-01T00:00:00.000Z", "2026-12-01T00:00:00.000Z")
        self.assertEqual(november["error_counts"], {"WIDTH_MISMATCH": 1})

    def test_retry_does_not_increase_completed_students(self):
        # 同一学生多次提交，completed_student_count 去重
        snap = snapshot(assigned=10, completed=0, attempts=0)
        snap["attempts"] = [
            {"id": 1, "experiment_version_id": 1, "student_id": 1, "status": "submitted", "completed": 1},
            {"id": 2, "experiment_version_id": 1, "student_id": 1, "status": "submitted", "completed": 1},
            {"id": 3, "experiment_version_id": 1, "student_id": 2, "status": "submitted", "completed": 1},
        ]
        value = wiring_interval_metrics(snap, START, END)
        self.assertEqual(value["completed_student_count"], 2)
        self.assertEqual(value["attempt_count"], 3)

    def test_end_at_compared_as_instant_not_lexical_string(self):
        # 同一时刻写成 +08:00 / +00:00 / 无毫秒，都必须归入同一区间（父 AC-01 可复算）。
        # 裸字符串比较会把 "2026-11-01T07:00:00+08:00"（=10-31 23:00Z）误判到 11 月。
        inside = [
            "2026-10-15T00:00:00.000Z",
            "2026-10-15T00:00:00+00:00",
            "2026-10-15T08:00:00+08:00",
            "2026-10-31T23:00:00Z",
            "2026-11-01T07:00:00+08:00",
        ]
        for value in inside:
            snap = snapshot(assigned=10, completed=6)
            snap["versions"][0]["end_at"] = value
            self.assertEqual(wiring_interval_metrics(snap, START, END)["assigned_count"], 10, value)

    def test_end_at_outside_range_or_invalid_is_skipped(self):
        outside = [
            "2026-10-01T07:00:00+08:00",  # = 09-30 23:00Z，字典序却像 10 月
            "2026-11-01T00:00:00.000Z",   # 区间右端开区间
            "not-a-time",
            None,
        ]
        for value in outside:
            snap = snapshot(assigned=10, completed=6)
            snap["versions"][0]["end_at"] = value
            metrics = wiring_interval_metrics(snap, START, END)
            self.assertEqual(metrics["assigned_count"], 0, value)
            self.assertIsNone(metrics["completion_rate"], value)


EXP01_FULL_WIRES = [
    {"id": "w_a", "from_terminal": "sw_a_out", "to_terminal": "alu_a"},
    {"id": "w_b", "from_terminal": "sw_b_out", "to_terminal": "alu_b"},
    {"id": "w_op", "from_terminal": "sw_op_out", "to_terminal": "alu_op"},
    {"id": "w_y", "from_terminal": "alu_y", "to_terminal": "led_y_in"},
    {"id": "w_z", "from_terminal": "alu_z", "to_terminal": "led_z_in"},
    {"id": "w_c", "from_terminal": "alu_c", "to_terminal": "led_c_in"},
]


class WiringAnalyticsApiTest(WiringApiBase):
    """010C 接口层验收：父 AC-01 可复算、AC-02 权限边界、AC-04 导出与页面同一快照。"""

    def setUp(self):
        super().setUp()
        # 默认 TEST_NOW=10-13 12:00 在发布窗口（10-13T11 → 10-20）内，
        # 用于创建真实尝试；统计前再推到窗口结束之后（见 _close_window）。
        self.exp, self.ver = self.setup_experiment("EXP-01")
        self.url = (f"/courses/{self.course_id}/analytics"
                    "?dimension=wiring&from=2026-10-01T00:00:00Z&to=2026-10-21T00:00:00Z")

    def _close_window(self):
        # 统计口径要求 end_at 落入 [from, to) 且 to <= now：只有窗口结束后才成立。
        # 时间前进会让旧会话过期，所有客户端需重新登录。
        self.app.config["TEST_NOW"] = datetime(2026, 10, 21, 12, tzinfo=UTC)
        for client, number in ((self.admin, "T017ADMIN"), (self.teacher, "T017TEACH"),
                               (self.student, "T017STUD1"), (self.outsider, "T017STUD2")):
            self.login(client, number)

    def _submit_completed(self):
        attempt = self.create_attempt(self.ver["id"])
        state = attempt["state"]
        state["wires"] = EXP01_FULL_WIRES
        actions = [{"type": "connect", "payload": w} for w in EXP01_FULL_WIRES]
        self.call(self.student, "PUT", f"/wiring-attempts/{attempt['id']}",
                  {"revision": 0, "state": state, "actions": actions})
        return self.call(self.student, "POST", f"/wiring-attempts/{attempt['id']}/submit",
                         {"revision": 1}).json["data"]

    def test_permission_boundary_wiring_is_teacher_only(self):
        # 父 AC-02：学生（含未选课学生）无权查看班级连线统计
        self._close_window()
        self.call(self.student, "GET", self.url, status=403)
        self.call(self.outsider, "GET", self.url, status=404)
        data = self.call(self.teacher, "GET", self.url).json["data"]
        self.assertEqual(data["dimension"], "wiring")
        self.assertIn("analysis_run_id", data)

    def test_metrics_reflect_real_attempts(self):
        self._submit_completed()
        # 草稿不计提交次数，也不影响完成人数
        self.create_attempt(self.ver["id"])
        self._close_window()
        data = self.call(self.teacher, "GET", self.url).json["data"]
        self.assertEqual(data["metrics"]["assigned_count"], 1)
        self.assertEqual(data["metrics"]["completed_student_count"], 1)
        self.assertEqual(data["metrics"]["completion_rate"], 1.0)
        self.assertEqual(data["metrics"]["attempt_count"], 1)

    def test_validation_errors_surface_in_metrics(self):
        self._submit_completed()
        attempt = self.create_attempt(self.ver["id"])
        state = attempt["state"]
        state["wires"] = [{"id": "w_bad", "from_terminal": "sw_a_out", "to_terminal": "no_such"}]
        actions = [{"type": "connect",
                    "payload": {"id": "w_bad", "from_terminal": "sw_a_out", "to_terminal": "no_such"}}]
        saved = self.call(self.student, "PUT", f"/wiring-attempts/{attempt['id']}",
                          {"revision": 0, "state": state, "actions": actions}).json["data"]
        checked = self.call(self.student, "POST", f"/wiring-attempts/{attempt['id']}/validate",
                            {"revision": saved["revision"]}).json["data"]
        self.assertFalse(checked["valid"])
        self._close_window()
        data = self.call(self.teacher, "GET", self.url).json["data"]
        # 接到不存在端子的尝试计入错误趋势，但不计完成
        self.assertTrue(data["metrics"]["error_counts"])
        self.assertEqual(data["metrics"]["completed_student_count"], 1)

    def test_recompute_and_snapshot_restore_are_consistent(self):
        # 父 AC-01：同一筛选条件可复算；快照读回与首次结果完全一致
        self._close_window()
        first = self.call(self.teacher, "GET", self.url).json["data"]
        second = self.call(self.teacher, "GET", self.url).json["data"]
        self.assertEqual(first["metrics"], second["metrics"])
        self.assertNotEqual(first["analysis_run_id"], second["analysis_run_id"])
        restored = self.call(self.teacher, "GET",
                             f"/courses/{self.course_id}/analytics"
                             f"?analysis_run_id={first['analysis_run_id']}").json["data"]
        self.assertEqual(restored, first)

    def test_export_csv_uses_same_analysis_run_snapshot(self):
        # 父 AC-04：导出与页面使用同一 analysis_run_id 快照且口径一致
        self._submit_completed()
        self._close_window()
        data = self.call(self.teacher, "GET", self.url).json["data"]
        run_id = data["analysis_run_id"]
        response = self.call(self.teacher, "GET",
                             f"/courses/{self.course_id}/analytics"
                             f"/export?analysis_run_id={run_id}&format=csv")
        rows = list(csv.reader(io.StringIO(response.data.decode("utf-8-sig"))))
        # 前 4 行是 run 元数据，第 5 行是表头，其后每周一行
        self.assertEqual(rows[0][0], "analysis_run_id")
        self.assertEqual(rows[0][1], str(run_id))
        header = rows[4]
        self.assertEqual(header[0:2], ["period_start", "period_end"])
        self.assertEqual(header[2:],
                         ["assigned_count", "completed_student_count", "completion_rate",
                          "attempt_count", "error_counts"])
        series = data["series"]
        self.assertEqual(len(rows) - 5, len(series))
        for row, item in zip(rows[5:], series):
            self.assertEqual(row[0], item["period_start"])
            self.assertEqual(row[1], item["period_end"])
            for key, raw in zip(header[2:], row[2:]):
                expected = item["metrics"][key]
                if isinstance(expected, (list, dict)):
                    self.assertEqual(json.loads(raw), expected, key)
                elif expected is None:
                    self.assertEqual(raw, "", key)
                elif isinstance(expected, (int, float)):
                    self.assertEqual(float(raw), float(expected), key)
                else:
                    self.assertEqual(raw, expected, key)
        # 学生既不能读快照，也不能导出
        self.call(self.student, "GET",
                  f"/courses/{self.course_id}/analytics?analysis_run_id={run_id}", status=404)
        self.call(self.student, "GET",
                  f"/courses/{self.course_id}/analytics"
                  f"/export?analysis_run_id={run_id}&format=csv", status=403)

    def test_empty_course_reports_null_rate_not_zero(self):
        # 父 AC-03：没有连线实验的课程显示无数据（rate=null），不冒充 0%
        self._close_window()
        other = self.call(self.admin, "POST", "/courses",
                          {"title": "empty", "teacher_id": self.teacher_id}, 201).json["data"]["id"]
        data = self.call(self.teacher, "GET",
                         f"/courses/{other}/analytics"
                         "?dimension=wiring&from=2026-10-01T00:00:00Z&to=2026-10-21T00:00:00Z"
                         ).json["data"]
        self.assertEqual(data["metrics"]["assigned_count"], 0)
        self.assertIsNone(data["metrics"]["completion_rate"])
