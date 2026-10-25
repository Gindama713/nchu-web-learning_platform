"""Run only the authorized 005 I-01/resource seams; preserve known failures."""

import argparse
import io
import json
import os
import subprocess
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path

from tests.test_knowledge_i01_seams import KnowledgeI01SeamsTest

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "logs/i01/handlers")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"started_at": datetime.now(UTC).isoformat(),
              "tested_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "dirty_paths": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines(),
              "scope": "005 to existing 009/017/010C consumption, 005 markup/003 upload policy; not full I-01"}
    stream = io.StringIO()
    started = time.monotonic()
    previous = os.environ.get("I01_EVIDENCE_DIR")
    os.environ["I01_EVIDENCE_DIR"] = str(args.output)
    try:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(KnowledgeI01SeamsTest)
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    finally:
        if previous is None:
            os.environ.pop("I01_EVIDENCE_DIR", None)
        else:
            os.environ["I01_EVIDENCE_DIR"] = previous
    report.update(tests=result.testsRun, passed=result.testsRun - len(result.expectedFailures) - len(result.failures)
                  - len(result.errors) - len(result.unexpectedSuccesses),
                  expected_failures=[{"test": test.id(), "trace": trace} for test, trace in result.expectedFailures],
                  failures=[test.id() for test, _ in result.failures], errors=[test.id() for test, _ in result.errors],
                  unexpected_successes=[test.id() for test in result.unexpectedSuccesses],
                  elapsed_seconds=round(time.monotonic() - started, 3),
                  status=("passed_with_known_contract_failures" if result.expectedFailures else "passed")
                  if result.wasSuccessful() else "failed")
    (args.output / "handlers.txt").write_text(stream.getvalue(), encoding="utf-8")
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(stream.getvalue())
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
