"""SPEC-014 rules, missing denominators and clustering gates."""

from unittest import TestCase

from backend.apis.warnings import analyze


def student(student_id, correct=5, answers=5, completed=1, due=1,
            attended=1, expected=1, last_two=None):
    return {"student_id": student_id, "correct": correct, "answers": answers,
            "completed": completed, "due": due, "attended": attended,
            "expected": expected, "last_two": last_two or []}


class WarningTest(TestCase):
    def test_rules_work_without_cluster_or_attendance_denominator(self):
        value = analyze([student(1, correct=2, attended=0, expected=0),
                         student(2, answers=0, correct=0, attended=0, expected=2,
                                 last_two=["late", "absent"])])
        self.assertEqual(value["model_status"], "insufficient_data")
        self.assertEqual([item["reasons"][0]["code"] for item in value["warnings"]],
                         ["LOW_OBJECTIVE_RATE", "RECENT_ATTENDANCE"])

    def test_all_good_students_do_not_force_warning(self):
        rows = [student(i, correct=5 + i % 2, answers=6, completed=1, due=1,
                        attended=4 + i % 2, expected=5) for i in range(1, 11)]
        value = analyze(rows)
        self.assertEqual(value["model_status"], "clustered")
        self.assertEqual(value["warnings"], [])

    def test_cluster_is_deterministic_with_real_weak_group(self):
        rows = [student(i, correct=2 if i <= 5 else 5, completed=0 if i <= 5 else 1,
                        attended=1 if i <= 5 else 5, expected=5)
                for i in range(1, 11)]
        first, second = analyze(rows), analyze(list(reversed(rows)))
        self.assertEqual(first["labels"], second["labels"])
        self.assertEqual({item["student_id"] for item in first["warnings"]}, set(range(1, 6)))
