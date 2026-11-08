"""Persist R37 handler responses, DB facts and explicit known contract failures."""

import argparse
import json
import subprocess
import unittest
from datetime import UTC, datetime
from pathlib import Path

from tests.test_preparation_quiz_integration import PreparationQuizIntegrationTest

ROOT = Path(__file__).resolve().parents[1]


class EvidenceResult(unittest.TextTestResult):
    records = None

    def stopTest(self, test):
        self.records.append({'test': test.id(), 'http': test.trace, 'database': test.snapshots})
        super().stopTest(test)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines()
    EvidenceResult.records = []
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PreparationQuizIntegrationTest)
    with (args.output/'handlers.txt').open('w', encoding='utf-8') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=EvidenceResult).run(suite)
    report = {
        'at_utc': datetime.now(UTC).isoformat(), 'tested_head': head, 'dirty_paths': dirty,
        'layer': 'real Flask handlers / temporary SQLite; not socket or UI',
        'fixtures': ['initial admin/teacher bootstrap only', 'TEST_NOW',
                     'rollback-only link UPDATE', 'preparation notification abort trigger'],
        'business_setup': 'actual 001/005/006/008/004 HTTP; no successful-response mocks',
        'tests_run': result.testsRun,
        'passed': result.testsRun-len(result.expectedFailures)-len(result.errors)-len(result.failures),
        'expected_contract_failures': [{'test': test.id(), 'traceback': error} for test, error in result.expectedFailures],
        'failures': [{'test': test.id(), 'traceback': error} for test, error in result.failures+result.errors],
        'unexpected_successes': [test.id() for test in result.unexpectedSuccesses],
        'acceptance': 'blocked while R37-004-01/02 or preparation UI gaps remain',
        'records': EvidenceResult.records,
    }
    (args.output/'handlers.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('tests_run', 'passed', 'expected_contract_failures', 'failures')}, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
