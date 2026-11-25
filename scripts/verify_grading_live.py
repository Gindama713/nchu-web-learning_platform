"""Real HTTP + persistent worker + pinned Java, using disposable synthetic accounts.

No direct claim/submit injection. Optional installed Chrome/Edge verification.
"""

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.shared.db import connect
from scripts.poll_burst_20261112 import call, mint_sessions, stamp
from tests import test_grading as fixture_source


class HttpClient:
    def __init__(self, base, source):
        self.base = base
        self.cookie = source.get_cookie("cpu_session").value
        self.csrf = source.csrf
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def open(self, path, method="GET", json=None, headers=None, data=None):
        import json as codec
        headers = {**(headers or {}), "Origin": self.base, "Cookie": "cpu_session=" + self.cookie}
        body = None
        if data is not None:
            boundary = "cpu-" + uuid4().hex
            parts = []
            for key, value in data.items():
                parts.append(f"--{boundary}\r\n".encode())
                if isinstance(value, tuple):
                    content, filename = value[:2]
                    parts.append(f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
                    parts.append(content.getvalue())
                else:
                    parts.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n{value}'.encode())
                parts.append(b"\r\n")
            body = b"".join(parts) + f"--{boundary}--\r\n".encode()
            headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
        elif json is not None:
            body = codec.dumps(json).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, body, headers, method=method)
        try:
            response = self.http.open(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            result = codec.loads(raw) if "json" in response.headers.get("Content-Type", "") else None
            return SimpleNamespace(status_code=response.code, json=result, data=raw)

    def get(self, path, **kwargs):
        return self.open(path, **kwargs)

    def post(self, path, **kwargs):
        return self.open(path, method="POST", **kwargs)

    def put(self, path, **kwargs):
        return self.open(path, method="PUT", **kwargs)

    def patch(self, path, **kwargs):
        return self.open(path, method="PATCH", **kwargs)

    def delete(self, path, **kwargs):
        return self.open(path, method="DELETE", **kwargs)


def terminate(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    else:
        process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def wait_data(client, path, success, timeout=150):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get("/api/v1" + path)
        if response.status_code != 200:
            raise AssertionError((path, response.status_code, response.json))
        value = response.json["data"]
        if success(value):
            return value
        if value.get("status") in {"failed", "passed", "accepted", "wrong_answer", "system_error", "timeout", "invalid_circuit", "resource_limit"}:
            raise AssertionError((path, value))
        time.sleep(0.2)
    raise AssertionError("Timed out: " + path)


def main():
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jar", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--sandbox", choices=("native", "bubblewrap"), default="bubblewrap" if os.name == "posix" else "native")
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--browser-only", action="store_true", help="UI-only pass, separate from the real grading report")
    parser.add_argument("--load", action="store_true", help="Run 50 synthetic sessions while the worker grades CPU")
    args = parser.parse_args()
    if args.browser_only:
        args.browser = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    fixture_source.TEST_NOW = datetime.now(UTC)
    fixture = fixture_source.GradingFixture("runTest")
    fixture.setUp()
    processes = []
    logs = []
    report = {"platform": platform.platform(), "python": platform.python_version(), "sandbox": args.sandbox,
              "scope": "Disposable synthetic accounts; real loopback HTTP, persistent worker and fixed Java/JAR",
              "browser_only": args.browser_only, "experiments": []}
    try:
        if args.load:
            at = stamp()
            with closing(connect(fixture.path)) as db:
                db.execute("BEGIN IMMEDIATE")
                for index in range(50):
                    user_id = db.execute("INSERT INTO user(student_no,name,password_hash,role,created_at,updated_at) "
                                         "VALUES(?,?,?,'student',?,?)", (f"LIVELOAD{index:04d}", f"Load {index}", "fixture-only", at, at)).lastrowid
                    db.execute("INSERT INTO course_member(course_id,user_id,member_role,created_at,updated_at) "
                               "VALUES(?,?,'student',?,?)", (fixture.course_id, user_id, at, at))
                db.commit()
            sessions = mint_sessions(fixture.path, fixture.app.config["SECRET_KEY"], fixture.course_id, 50)
        with closing(socket.socket()) as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = dict(os.environ, PYTHONUTF8="1", APP_ENV="development", APP_ORIGIN=base,
                   SECRET_KEY=fixture.app.config["SECRET_KEY"], DATABASE_PATH=str(fixture.path),
                   UPLOAD_ROOT=fixture.app.config["UPLOAD_ROOT"], LOGISIM_JAR_PATH=str(args.jar.resolve()),
                   HOST="127.0.0.1", PORT=str(port))
        for name, command in (("web", ["-m", "backend.serve"]), ("worker", ["-m", "backend.worker", "--sandbox", args.sandbox])):
            log = (args.report.parent / (args.report.stem + "-" + name + ".log")).open("w", encoding="utf-8")
            logs.append(log)
            processes.append(subprocess.Popen([sys.executable, *command], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT))
        clients = {}
        for name in ("teacher", "student", "student2", "student3"):
            clients[name] = HttpClient(base, getattr(fixture, name))
            setattr(fixture, name, clients[name])
        teacher = fixture.teacher
        deadline = time.monotonic() + 30
        while True:
            try:
                health = teacher.get("/api/v1/health")
                if health.json and health.json["data"]["grader_ready"]:
                    break
            except OSError:
                pass
            if any(p.poll() is not None for p in processes) or time.monotonic() >= deadline:
                raise AssertionError("Web/worker failed to become ready; inspect local logs")
            time.sleep(0.2)
        experiments = [] if args.browser_only else [("EXP-01", "alu8.circ"), ("EXP-02", "reg8.circ"), ("EXP-04", "cpu8.circ")]
        for code, filename in experiments:
            if code == "EXP-01":
                version_id = fixture.version_id
            else:
                experiment = fixture.call(teacher, "POST", fixture.course + "/experiments",
                                          {"code": code, "title": code, "description": "Live grading"}, 201).json["data"]
                version_id = fixture.create_version(("circuit",), code_experiment=experiment["id"])
            template = fixture.call(teacher, "GET", f"/experiment-versions/{version_id}/grading-template").json["data"]
            fixture.call(teacher, "PUT", f"/experiment-versions/{version_id}/judge-profile", template["profile"])
            suite = fixture.create_suite(version_id, cases=template["cases"])
            content = (ROOT / "tests" / "fixtures" / "logisim" / filename).read_bytes()
            broken = ET.fromstring(content)
            for circuit in broken.findall("circuit"):
                for wire in list(circuit.findall("wire")):
                    circuit.remove(wire)
            wrong = ET.tostring(broken, encoding="utf-8")
            reference = fixture.upload_reference(version_id, "correct", content)
            negative = fixture.upload_reference(version_id, "known_wrong", wrong)
            validation = fixture.call(teacher, "POST", f"/test-suites/{suite['id']}/validations",
                                       {"reference_file_id": reference["reference_file_id"],
                                        "negative_file_id": negative["reference_file_id"]}, 202).json["data"]
            wait_data(teacher, f"/test-suite-validations/{validation['validation_id']}", lambda r: r["status"] == "passed")
            fixture.publish_suite(version_id, suite, validation["validation_id"])
            at = datetime.now(UTC)
            fixture.call(teacher, "POST", f"/experiment-versions/{version_id}/publish",
                         {"start_at": (at - timedelta(minutes=1)).isoformat(), "end_at": (at + timedelta(days=1)).isoformat(),
                          "initial_test_suite_id": suite["id"]})
            good = fixture.submit(fixture.student, version_id, content=content)
            bad = fixture.submit(fixture.student2, version_id, content=wrong)
            if args.load and code == "EXP-04":
                def exercise(session):
                    result = []
                    for path in ("/api/v1/auth/session", "/api/v1/courses",
                                 f"/api/v1/courses/{fixture.course_id}/experiment-versions"):
                        result.append(call(base, "GET", path, cookie=session["token"]))
                    result.append(call(base, "POST", f"/api/v1/courses/{fixture.course_id}/assistant/ask",
                                       {"question": "最近7天考勤"}, session["token"], session["csrf"]))
                    return result
                with ThreadPoolExecutor(max_workers=50) as pool:
                    load = [row for group in pool.map(exercise, sessions) for row in group]
                latency = sorted(row[2] for row in load)
                failures = [row for row in load if row[0] != 200]
                health = teacher.get("/api/v1/health").json["data"]
                report["concurrent_load"] = {"sessions": 50, "requests": len(load), "failures": len(failures),
                                             "p95_ms": round(latency[int(len(latency) * .95)], 1),
                                             "worker_state_after_load": health["worker_state"],
                                             "scope": "Session/course/experiment polling + read-only assistant during CPU grading"}
                assert not failures, [(r[0], r[1]) for r in failures[:2]]
            good_result = wait_data(fixture.student, f"/grading-runs/{good['run_id']}", lambda r: r["status"] == "accepted")
            bad_result = wait_data(fixture.student2, f"/grading-runs/{bad['run_id']}", lambda r: r["status"] == "wrong_answer")
            regrade = fixture.call(teacher, "POST", f"/submissions/{good['submission_id']}/regrades", {"reason": "Live regression"},
                                   202, headers_extra={"Idempotency-Key": str(uuid4())}).json["data"]
            wait_data(fixture.student, f"/grading-runs/{regrade['run_id']}", lambda r: r["status"] == "accepted")
            fixture.call(fixture.student3, "GET", f"/grading-runs/{good['run_id']}", status=404)
            report["experiments"].append({"code": code, "cases": len(template["cases"]), "version_id": version_id,
                                          "standard": good_result["status"], "negative": bad_result["status"],
                                          "regrade": "accepted", "student_isolation": True})
            print(code + " real HTTP validation/submission/regrade passed", flush=True)
        if args.browser:
            from scripts.verify_completion_browsers import verify
            report["browsers"] = verify(base, fixture, args.report.parent)
        report["passed"] = True
    finally:
        for process in reversed(processes):
            terminate(process)
        for log in logs:
            log.close()
        fixture.tearDown()
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
