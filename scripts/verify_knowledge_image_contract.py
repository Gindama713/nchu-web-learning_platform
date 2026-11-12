"""Run only SPEC-005 image readiness checks; keep gaps separate from passes."""

import argparse
import hashlib
import io
import json
import os
import subprocess
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path

from tests.test_knowledge_image_contract import KnowledgeImageContractTest

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Use a new output directory; prior evidence must be preserved")
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"started_at": datetime.now(UTC).isoformat(),
              "tested_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "dirty_paths": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines(),
              "scope": "005 existing safety/persistence; 003 current policy and PDF controls; no image acceptance",
              "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
                  "backend/apis/resources.py", "backend/models/knowledge.py",
                  "tests/test_knowledge_image_contract.py", "scripts/verify_knowledge_image_contract.py")}}
    stream = io.StringIO()
    started = time.monotonic()
    previous = os.environ.get("KNOWLEDGE_IMAGE_EVIDENCE_DIR")
    os.environ["KNOWLEDGE_IMAGE_EVIDENCE_DIR"] = str(args.output)
    try:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(KnowledgeImageContractTest)
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    finally:
        if previous is None:
            os.environ.pop("KNOWLEDGE_IMAGE_EVIDENCE_DIR", None)
        else:
            os.environ["KNOWLEDGE_IMAGE_EVIDENCE_DIR"] = previous
    observations = []
    for case in sorted(args.output.glob("test_*.json")):
        observations.extend(json.loads(case.read_text(encoding="utf-8"))["contract_observations"])
    report.update(tests=result.testsRun, failures=[test.id() for test, _ in result.failures],
                  errors=[test.id() for test, _ in result.errors],
                  elapsed_seconds=round(time.monotonic() - started, 3), observations=observations,
                  boundary_checks="passed" if result.wasSuccessful() else "failed",
                  image_readiness="blocked",
                  status="checks_passed_with_open_gaps" if result.wasSuccessful() else "failed")
    (args.output / "checks.txt").write_text(stream.getvalue(), encoding="utf-8")
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(stream.getvalue())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
