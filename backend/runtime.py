"""Engine self-test and worker heartbeat contract, persisted beside the database."""

import json
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from backend.operations import sha256

JAR_SHA256 = "6b368e894742c04cc83aa9830f869bcab0190ede4df43ad6fecdb89b3a23a41c"
HEARTBEAT_SECONDS = 45
ENGINE_CHECK_SECONDS = 300


def state_path(database, kind):
    database = Path(database).resolve()
    return database.with_name(database.name + f".{kind}.json")


def save_state(database, kind, data):
    path = state_path(database, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(data), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_state(database, kind):
    try:
        data = json.loads(state_path(database, kind).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def jar_identity():
    path = Path(os.environ.get("LOGISIM_JAR_PATH", ""))
    try:
        stat = path.stat()
        if not path.is_file():
            return None
        return str(path.resolve()), stat.st_size, stat.st_mtime_ns
    except OSError:
        return None


@lru_cache(maxsize=4)
def verified_jar(identity):
    try:
        return bool(identity) and sha256(identity[0]) == JAR_SHA256
    except OSError:
        return False


def publish_worker_status(database, worker_id, state):
    """Call from the REAL worker loop every <=5s, including while executing.

    Publish 'stopped' on exit, 'error' if execution/renewal cannot proceed.
    A supervisor must not publish fake worker liveness on its behalf.
    """
    if state not in {"idle", "running", "paused", "error", "stopped"} or not worker_id:
        raise ValueError("Invalid worker state")
    save_state(database, "worker", {"worker_id": str(worker_id), "state": state, "at": time.time()})


def check_engine(database):
    """Explicit bounded real execution, never launched by a health HTTP request."""
    from backend.engines import grading
    identity = jar_identity()
    state = {"ready": False, "identity": identity, "at": time.time(), "error": "JAR_IDENTITY"}
    try:
        if not verified_jar(identity):
            return state
        # Tiny trusted wire circuit; validate both correct and deliberately wrong expectations.
        circuit = '''<?xml version="1.0"?><project source="5.0.0" version="1.0">
<lib desc="#Wiring" name="0"/><main name="pipeline"/><circuit name="pipeline">
<comp lib="0" loc="(120,100)" name="Pin"><a name="label" val="A"/></comp>
<comp lib="0" loc="(240,100)" name="Pin"><a name="label" val="Y"/>
<a name="output" val="true"/></comp><wire from="(120,100)" to="(240,100)"/>
</circuit></project>'''
        with tempfile.TemporaryDirectory(prefix="engine-check-") as directory:
            root = Path(directory)
            (root / "check.circ").write_text(circuit, encoding="utf-8")
            for expected, vector_text in ((True, "A\tY\n0\t0\n1\t1\n"),
                                          (False, "A\tY\n0\t1\n1\t0\n")):
                vector = root / "vector.txt"
                vector.write_text(vector_text, encoding="utf-8")
                command = grading.engine_command(identity[0], "pipeline", vector, root / "check.circ",
                                                 {"memory_mib": 256})
                raw, code = grading.real_executor(command, root, 30, 65536)
                parsed = grading.parse_engine_output(raw or "", [{"id": 1}])
                if code != 0 or parsed is None or parsed[1]["passed"] != expected:
                    state["error"] = "ENGINE_SELFTEST"
                    return state
        state.update(ready=True, error=None)
    except (OSError, ValueError, grading.SandboxTimeout, grading.SandboxOutputLimit):
        state["error"] = "ENGINE_UNAVAILABLE"
    finally:
        state["at"] = time.time()
        save_state(database, "engine", state)
    return state


def health_details(database):
    identity = jar_identity()
    engine, worker = load_state(database, "engine"), load_state(database, "worker")
    current = time.time()

    def fresh(record, seconds):
        at = record.get("at")
        return isinstance(at, (int, float)) and 0 <= current - at <= seconds

    engine_ready = (bool(identity) and verified_jar(identity) and engine.get("ready") is True
                    and engine.get("identity") == list(identity) and fresh(engine, ENGINE_CHECK_SECONDS))
    worker_ready = (bool(worker.get("worker_id")) and worker.get("state") in {"idle", "running"}
                    and fresh(worker, HEARTBEAT_SECONDS))
    queued = running = None
    try:
        with closing(sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True, timeout=0.2)) as db:
            counts = dict(db.execute("SELECT status,COUNT(*) FROM grading_run GROUP BY status"))
            queued, running = counts.get("queued", 0), counts.get("running", 0)
    except sqlite3.Error:
        pass
    return {"engine_ready": engine_ready, "worker_ready": worker_ready,
            "grader_ready": engine_ready and worker_ready, "queued": queued, "running": running,
            "worker_state": worker.get("state", "missing"),
            "engine_check_at": datetime.fromtimestamp(engine["at"], UTC).isoformat()
            if fresh(engine, ENGINE_CHECK_SECONDS) else None}
