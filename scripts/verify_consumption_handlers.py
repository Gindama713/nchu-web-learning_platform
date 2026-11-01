"""Run only the two consumption seams, retaining sanitized requests and raw facts."""

import argparse
import json
import os
import subprocess
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path

from tests.test_consumption_seams import ConsumptionSeamsTest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('logs/consumption/handlers'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ['CONSUMPTION_SEAMS_OUTPUT'] = str(args.output.resolve())
    report = {'started_at': datetime.now(UTC).isoformat(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], text=True).splitlines()}
    start = time.monotonic()
    with (args.output / 'handlers.txt').open('w', encoding='utf-8') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(ConsumptionSeamsTest))
    report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  expected_failures=len(result.expectedFailures), elapsed_seconds=round(time.monotonic() - start, 3),
                  status='passed' if result.wasSuccessful() else 'failed')
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
