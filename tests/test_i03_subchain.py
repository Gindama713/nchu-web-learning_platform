"""Cross-interface I-03 subset, with every successful business object via real API."""

from unittest import TestCase

from scripts.i03_subchain import Subchain
from tests import test_i03_entry


class I03SubchainTest(TestCase):
    setUp = test_i03_entry.I03EntryTest.setUp
    call = test_i03_entry.I03EntryTest.call
    login = test_i03_entry.I03EntryTest.login
    evidence = test_i03_entry.I03EntryTest.evidence

    def test_fixed_wrong_version_four_students_mastery_snapshot_and_qa_revocation(self):
        scenario = Subchain(self.call, self.app, self.teacher,
                            [self.student] + [self.app.test_client() for _ in range(3)],
                            self.course_id, self.app.config['TEST_NOW'], self.password)
        self.observations['stages'] = scenario.stages
        scenario.seed()
        scenario.submit()
        scenario.verify_before_review()
        scenario.review()
        scenario.qa()
        scenario.unpublish()
        scenario.revoke()
