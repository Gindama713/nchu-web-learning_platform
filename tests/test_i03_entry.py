"""Bounded 007 entry/authorization observations; no 007 implementation takeover."""

import os
from pathlib import Path
from unittest import TestCase

from scripts.i03_support import facts, record, save
from tests.test_demo import ORIGIN, DemoApiBase


class I03EntryTest(TestCase):
    login = DemoApiBase.login

    def setUp(self):
        self.requests = []
        self.observations = {}
        DemoApiBase.setUp(self)
        self.addCleanup(self.evidence)

    def call(self, client, method, path, data=None, status=200):
        response = client.open('/api/v1' + path, method=method, json=data,
                               headers={'Origin': ORIGIN, 'X-CSRF-Token': getattr(client, 'csrf', '')})
        actor = next((name for name in ('admin', 'teacher', 'student', 'outsider')
                      if getattr(self, name, None) is client), 'controlled-student')
        record(self.requests, actor, method, path, data, response.status_code, response.get_json(silent=True))
        self.assertEqual(response.status_code, status, response.get_json(silent=True))
        return response

    def evidence(self):
        output = os.environ.get('I03_EVIDENCE_DIR')
        if output:
            save(Path(output) / (self._testMethodName + '.json'), {
                'requests': self.requests, 'observations': self.observations, 'facts': facts(self.path),
                'fixtures': ['bootstrap admin/teacher only', 'TEST_NOW; all business objects via API'],
            })

    def test_demo_actual_entry_permissions_and_current_revision_observation(self):
        course = self.course_id
        demo = self.call(self.teacher, 'POST', self.base, {'preset': 'cpu'}, 201).json['data']
        other = self.call(self.admin, 'POST', '/courses', {
            'title': 'I03 other course', 'teacher_id': self.teacher_id}, 201).json['data']['id']
        foreign = self.call(self.teacher, 'POST', f'/courses/{other}/demo-sessions',
                            {'preset': 'cpu'}, 201).json['data']
        listing = self.call(self.student, 'GET', self.base).json
        self.assertEqual([r['id'] for r in listing['data']], [demo['id']])
        self.assertEqual(listing['total'], 1)
        self.call(self.student, 'GET', f"/demo-sessions/{foreign['id']}", status=404)
        self.call(self.student, 'GET', f'/courses/{other}/demo-sessions', status=404)
        self.call(self.outsider, 'GET', f"/demo-sessions/{demo['id']}", status=404)
        self.call(self.student, 'POST', self.base, {'preset': 'cpu'}, 403)
        self.call(self.student, 'PUT', f"/demo-sessions/{demo['id']}/state",
                  {'revision': 0, 'action': 'step'}, 403)
        self.call(self.student, 'POST', f"/demo-sessions/{demo['id']}/close", {'revision': 0}, 403)
        advanced = self.call(self.teacher, 'PUT', f"/demo-sessions/{demo['id']}/state",
                             {'revision': 0, 'action': 'step'}).json['data']
        for _ in range(2):
            current = self.call(self.student, 'GET', f"/demo-sessions/{demo['id']}?after_revision=0").json['data']
            self.assertEqual(current, advanced)
        self.call(self.teacher, 'PUT', f"/demo-sessions/{demo['id']}/state",
                  {'revision': 0, 'action': 'step'}, 409)
        # Record a real contract defect separately; this is not a passing AC-03 assertion.
        future = self.call(self.student, 'GET', f"/demo-sessions/{demo['id']}?after_revision=99").json['data']
        self.observations['future_revision'] = {
            'acceptance': 'SPEC-007/AC-03; APIC 4 GET current revision', 'owner': '罗浩铭',
            'expected_revision': advanced['revision'], 'actual_revision': future['revision'],
            'result': 'failed' if future['revision'] != advanced['revision'] else 'passed',
        }
        self.observations['cpu_initial'] = {'ram_prefix': demo['state']['ram'][:12],
                                           'state_fields': list(demo['state']), 'not_full_R07': True}
        self.call(self.teacher, 'DELETE', f'/courses/{course}/members/{self.student_id}', status=204)
        self.call(self.student, 'GET', self.base, status=404)
        self.call(self.student, 'GET', f"/demo-sessions/{demo['id']}", status=404)
        self.assertEqual(facts(self.path)['foreign_key_check'], [])
