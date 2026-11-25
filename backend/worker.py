"""Single persistent SPEC-018 consumer. Run: python -m backend.worker."""

import argparse
import json
import logging
import os
import signal
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from uuid import uuid4

from backend import runtime
from backend.engines import grading as engine
from backend.models.grading import (
    canonical_profile_sha256,
    preflight_circ,
    suite_content_sha256,
)
from backend.operations import file_path, in_maintenance, sha256
from backend.shared.db import connect, database_ready

logger = logging.getLogger(__name__)


def utcnow():
    return datetime.now(UTC)


@contextmanager
def singleton(database):
    """OS releases the lock after crashes; a stale filename is harmless."""
    path = Path(database).resolve().with_name(Path(database).name + ".worker.lock")
    with path.open("a+b") as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def claim(database, validation_first=False):
    with closing(connect(database)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            order = ("validation", "run") if validation_first else ("run", "validation")
            job = None
            for kind in order:
                row = (engine.claim_run if kind == "run" else engine.claim_validation)(db, utcnow())
                if row is not None:
                    job = kind, dict(row)
                    break
            db.commit()
            return job
        except BaseException:
            db.rollback()
            raise


def load_inputs(database, uploads, kind, job):
    """Freeze checked inputs in memory; reject changed identities before executing."""
    with closing(connect(database)) as db:
        cases = [dict(row) for row in db.execute("SELECT * FROM test_case WHERE suite_id=? ORDER BY id", (job["suite_id"],))]
        suite = db.execute("SELECT * FROM test_suite WHERE id=?", (job["suite_id"],)).fetchone()
        expected_suite = job["suite_sha256"]
        serialized = [{"label": case["label"], "visibility": case["visibility"], "group_code": case["group_code"],
                       "steps": json.loads(case["steps_json"])} for case in cases]
        if not suite or suite["content_sha256"] != expected_suite or suite_content_sha256(serialized) != expected_suite:
            raise ValueError("Test suite identity changed")
        if kind == "run":
            profile = json.loads(job["profile_snapshot_json"])
            row = db.execute("SELECT s.file_sha256,f.storage_key FROM submission s JOIN file_object f ON f.id=s.file_id "
                             "WHERE s.id=?", (job["submission_id"],)).fetchone()
            references = [(row["storage_key"], row["file_sha256"])] if row else []
        else:
            row = db.execute("SELECT * FROM judge_profile WHERE experiment_version_id=?", (suite["experiment_version_id"],)).fetchone()
            if not row:
                raise ValueError("Missing judge profile")
            profile = {"top_circuit": row["top_circuit"], "port_schema": json.loads(row["port_schema_json"]),
                       "allowed_components": json.loads(row["allowed_components_json"]), "engine_version": row["engine_version"],
                       "limits": json.loads(row["limits_json"]), "jar_sha256": row["jar_sha256"]}
            references = []
            for prefix in ("reference", "negative"):
                file = db.execute("SELECT f.storage_key FROM reference_file r JOIN file_object f ON f.id=r.file_id WHERE r.id=?",
                                  (job[prefix + "_file_id"],)).fetchone()
                if not file:
                    raise ValueError("Reference file missing")
                references.append((file["storage_key"], job[prefix + "_sha256"]))
    canonical = canonical_profile_sha256(profile["top_circuit"], profile["port_schema"], profile["allowed_components"],
                                        profile["engine_version"], profile["limits"])
    if canonical != job["profile_sha256"] or job["jar_sha256"] != runtime.JAR_SHA256:
        raise ValueError("Judge profile or JAR identity changed")
    if len(references) != (1 if kind == "run" else 2):
        raise ValueError("Circuit file missing")
    paths = []
    for key, expected in references:
        path = file_path(uploads, key)
        if sha256(path) != expected:
            raise ValueError("Circuit checksum mismatch")
        preflight_circ(path.read_text(encoding="utf-8"), {
            "top_circuit": profile["top_circuit"], "port_schema_json": json.dumps(profile["port_schema"]),
            "allowed_components_json": json.dumps(profile["allowed_components"])})
        paths.append(path)
    return {"profile_snapshot_json": json.dumps(profile)}, cases, paths


def execute_job(database, uploads, kind, job, executor):
    profile, cases, paths = load_inputs(database, uploads, kind, job)
    outcomes = [engine.run_in_sandbox(profile, path, cases, executor) for path in paths]
    if kind == "run":
        outcome = outcomes[0]
        results = [{"case_id": case["id"], "passed": result["passed"], "actual": result.get("actual", [])}
                   for case in cases if (result := outcome["results"].get(case["id"])) is not None]
        return outcome["error_code"], results
    good, bad = outcomes
    error = good["error_code"] or bad["error_code"]
    return error, (len(good["results"]) == len(cases) and all(r["passed"] for r in good["results"].values()),
                   any(not r["passed"] for r in bad["results"].values()))


def finish(database, kind, job, outcome):
    error, results = outcome
    with closing(connect(database)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            if kind == "run":
                accepted = engine.submit_run_result(db, job["id"], job["worker_token"], utcnow(), error, results)
            else:
                accepted = engine.submit_validation_result(db, job["id"], job["worker_token"], utcnow(),
                                                           results[0], results[1], error=error)
            db.commit()
            return accepted
        except BaseException:
            db.rollback()
            raise


def consume(database, uploads, stop, executor=engine.real_executor, once=False, heartbeat=5):
    worker_id = f"{os.getpid()}-{uuid4().hex}"
    validation_first = False
    checked_at = None
    with singleton(database), ThreadPoolExecutor(max_workers=1) as pool:
        try:
            while not stop.is_set():
                if in_maintenance(database):
                    runtime.publish_worker_status(database, worker_id, "paused")
                    if once:
                        return
                    stop.wait(1)
                    continue
                if checked_at is None or time.monotonic() - checked_at >= runtime.ENGINE_CHECK_SECONDS - 30:
                    runtime.publish_worker_status(database, worker_id, "error")
                    if not runtime.check_engine(database, executor=executor)["ready"]:
                        logger.error("Engine/sandbox self-test failed; not claiming jobs")
                        if once:
                            raise RuntimeError("Engine self-test failed")
                        stop.wait(5)
                        continue
                    checked_at = time.monotonic()
                runtime.publish_worker_status(database, worker_id, "idle")
                job = claim(database, validation_first)
                validation_first = not validation_first
                if job is None:
                    if once:
                        return
                    stop.wait(1)
                    continue
                kind, row = job
                logger.info("Claimed %s=%s", kind, row["id"])
                cancelled = threading.Event()
                execute = partial(executor, cancel_event=cancelled)
                future = pool.submit(execute_job, database, uploads, kind, row, execute)
                leased = True
                while not future.done():
                    runtime.publish_worker_status(database, worker_id, "running" if leased else "error")
                    wait([future], timeout=heartbeat)
                    try:
                        with closing(connect(database)) as db:
                            renew = engine.renew_lease if kind == "run" else engine.renew_validation_lease
                            leased = leased and renew(db, row["id"], row["worker_token"], utcnow())
                    except sqlite3.Error:
                        logger.exception("Lease renewal failed")
                        leased = False
                    if not leased:
                        cancelled.set()
                try:
                    outcome = future.result()
                except Exception:
                    logger.exception("Job %s=%s failed", kind, row["id"])
                    outcome = ("ENGINE_CRASH", [] if kind == "run" else (False, False))
                if leased and not finish(database, kind, row, outcome):
                    logger.warning("Discarded result after losing lease: %s=%s", kind, row["id"])
                if once:
                    return
        finally:
            runtime.publish_worker_status(database, worker_id, "stopped")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Consume at most one job for diagnosis")
    parser.add_argument("--sandbox", choices=("native", "bubblewrap"), default="bubblewrap" if os.name == "posix" else "native")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    database = os.environ.get("DATABASE_PATH", "instance/app.db")
    uploads = os.environ.get("UPLOAD_ROOT", "instance/uploads")
    if not database_ready(database):
        parser.error("Run db-upgrade before starting the worker")
    if args.sandbox == "native" and os.environ.get("APP_ENV") == "production":
        parser.error("Production grading requires Linux bubblewrap isolation")
    executor = engine.real_executor
    if args.sandbox == "bubblewrap":
        from backend.sandbox import bubblewrap_executor
        executor = bubblewrap_executor
    stop = threading.Event()
    for name in ("SIGINT", "SIGTERM"):
        signal.signal(getattr(signal, name), lambda *_: stop.set())
    try:
        consume(database, uploads, stop, executor=executor, once=args.once)
    except (OSError, RuntimeError, sqlite3.Error) as error:
        logger.error("Worker stopped: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
