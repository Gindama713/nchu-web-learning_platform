"""Only the new 007 entry and personal I-03 subchain checks, with actual transcripts."""

import argparse
import io
import os
import subprocess
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts.i03_support import ROOT, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'logs/i03/handlers')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ['I03_EVIDENCE_DIR'] = str(args.output)
    report = {'date': datetime.now(UTC).isoformat(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
              'scope': '007 API authorization observations; 008/006 -> 010B -> 011 bounded subchain; not full I-03',
              '007_UI': 'blocked, missing registered classroom page', 'fault_injections': []}
    suite = unittest.defaultTestLoader.loadTestsFromNames(['tests.test_i03_entry.I03EntryTest',
                                                         'tests.test_i03_subchain.I03SubchainTest'])
    stream = io.StringIO()
    started = time.monotonic()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    report.update(tests=result.testsRun, expected_failures=len(result.expectedFailures),
                  passed=result.testsRun-len(result.expectedFailures)-len(result.failures)-len(result.errors)
                  -len(result.unexpectedSuccesses)-len(result.skipped),
                  failures=[test.id() for test, _ in result.failures],
                  errors=[test.id() for test, _ in result.errors],
                  unexpected_successes=[test.id() for test in result.unexpectedSuccesses],
                  seconds=round(time.monotonic() - started, 3),
                  result=('passed_with_007_expected_failure' if result.expectedFailures else 'passed')
                  if result.wasSuccessful() else 'failed')
    (args.output / 'handlers.txt').write_text(stream.getvalue(), encoding='utf-8')
    save(args.output / 'report.json', report)
    print(stream.getvalue())
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
