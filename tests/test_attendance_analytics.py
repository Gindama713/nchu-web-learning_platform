"""Fixed C01-C04 examples from PRD §4.4."""

from unittest import TestCase

from backend.apis.analytics import interval_metrics

START = "2026-10-01T00:00:00.000Z"
END = "2026-11-01T00:00:00.000Z"


def sample(present_counts=(1, 2, 3), include_fourth=False):
    attend = []
    for student_id, count in enumerate(present_counts, 1):
        for task_id in range(1, 5):
            attend.append({"student_id": student_id, "task_id": task_id, "start_at": START,
                           "status": "present" if task_id <= count else "absent"})
    if include_fourth:
        for task_id in range(1, 5):
            attend.append({"student_id": 4, "task_id": task_id, "start_at": START, "status": "present"})
    attempts = []
    for student_id in range(1, len(present_counts) + 1):
        for paper_id, score in ((1, student_id * 10), (2, student_id * 30)):
            attempts.append({"id": len(attempts) + 1, "student_id": student_id, "paper_id": paper_id,
                             "status": "graded", "score_hundredths": score * 100})
    if include_fourth:
        attempts.append({"id": 99, "student_id": 4, "paper_id": 1, "status": "partial",
                         "score_hundredths": None})
    return {"attendance": attend, "papers": [{"id": 1, "start_at": START, "total_points": 5000},
                                               {"id": 2, "start_at": START, "total_points": 10000}],
            "attempts": attempts}


class AnalyticsTest(TestCase):
    def test_c01_perfect_correlation(self):
        value = interval_metrics(sample(), START, END)
        self.assertEqual(value["attendance_rate"], 0.5)
        self.assertEqual(value["performance_correlation"], 1)
        self.assertEqual(value["paired_count"], 3)

    def test_c02_insufficient_pairs(self):
        value = interval_metrics(sample((1, 2)), START, END)
        self.assertIsNone(value["performance_correlation"])
        self.assertEqual(value["correlation_reason"], "insufficient_pairs")

    def test_c03_zero_variance(self):
        value = interval_metrics(sample((2, 2, 2)), START, END)
        self.assertIsNone(value["performance_correlation"])
        self.assertEqual(value["correlation_reason"], "zero_variance")

    def test_c04_missing_performance(self):
        value = interval_metrics(sample(include_fourth=True), START, END)
        self.assertEqual(value["candidate_count"], 4)
        self.assertEqual(value["paired_count"], 3)
        self.assertEqual(value["missing_performance_count"], 1)
        self.assertEqual(value["attendance_rate"], 0.625)
        self.assertEqual(value["performance_correlation"], 1)

    def test_personal_scope_has_no_class_metrics(self):
        value = interval_metrics(sample(), START, END, subject=1)
        self.assertIsNone(value["candidate_count"])
        self.assertIsNone(value["performance_correlation"])
        self.assertEqual(value["correlation_reason"], "personal_scope")
