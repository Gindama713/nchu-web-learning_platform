"""Run only the R01 seam tests and retain real responses/DB checkpoints."""

import argparse
import json
import os
import subprocess
import unittest
from datetime import UTC, datetime
from pathlib import Path

from tests.test_resource_question_integration import ResourceQuestionSeamTest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('logs/r01/handlers'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ['R01_EVIDENCE_DIR'] = str(args.output.resolve())
    report = {'started_at': datetime.now(UTC).isoformat(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], text=True).splitlines(),
              'layer': 'real Flask handlers/SQLite; bootstrap admin/teacher and TEST_NOW; separate audit fault trigger'}
    with (args.output/'handlers.txt').open('w', encoding='utf-8') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(ResourceQuestionSeamTest))
    report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  expected_failures=len(result.expectedFailures), status='passed' if result.wasSuccessful() else 'failed')
    (args.output/'handlers.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(not result.wasSuccessful())


if __name__ == '__main__':
    main()
