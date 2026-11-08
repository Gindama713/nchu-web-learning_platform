"""SPEC-010C 连线统计：完成率与错误去重。"""

from unittest import TestCase

from backend.apis.analytics import wiring_interval_metrics

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
