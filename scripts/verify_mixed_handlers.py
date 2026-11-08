"""Run only the two new finite seams and preserve sanitized handler evidence."""

import argparse
import json
import subprocess
import unittest
from datetime import UTC, datetime
from pathlib import Path

from tests.test_mixed_consumption import MixedConsumptionTest

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'logs/mixed-consumption/handlers')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    MixedConsumptionTest.output = args.output
    report = {'at': datetime.now(UTC).isoformat(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines()}
    with (args.output / 'handlers.txt').open('w', encoding='utf-8') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(MixedConsumptionTest))
    report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  expected_failures=len(result.expectedFailures), result='passed' if result.wasSuccessful() else 'failed')
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
