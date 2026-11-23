"""Isolated real-HTTP Waitress smoke/load probe; never accepts a live database.

Seeds synthetic sessions to measure business requests, not login throttling.
Does NOT claim full exam/grader workload or target-Linux acceptance.
"""

import argparse
import hashlib
import hmac
import json
import os
import platform
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.shared.db import connect, migrate
from scripts.poll_burst_20261112 import call, mint_sessions, stamp


def main():
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--students", type=int, default=50)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if not 1 <= args.students <= 200:
        parser.error("students must be 1..200")
    report = {"platform": platform.platform(), "python": platform.python_version(), "sessions": args.students,
              "scope": "Synthetic sessions: attendance writes + session/course polling + read-only assistant; no exam/worker load"}
    with TemporaryDirectory(prefix="cpu-runtime-probe-") as directory:
        root = Path(directory)
        database = root / "app.db"
        migrate(database)
        secret = secrets.token_hex(32)
        at = datetime.now(UTC)
        teacher_token = secrets.token_hex(24)
        teacher_csrf = hmac.new(secret.encode(), teacher_token.encode(), "sha256").hexdigest()
        with closing(connect(database)) as db:
            for index in range(args.students + 1):
                role = "teacher" if index == 0 else "student"
                db.execute("INSERT INTO user(id,student_no,name,password_hash,role,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                           (index + 1, f"PROBE{index:05d}", f"Synthetic {index}", "unused", role, stamp(at), stamp(at)))
            db.execute("INSERT INTO course(id,title,teacher_id,created_at,updated_at) VALUES(1,'Runtime probe',1,?,?)",
                       (stamp(at), stamp(at)))
            for index in range(args.students + 1):
                db.execute("INSERT INTO course_member(course_id,user_id,member_role,created_at,updated_at) VALUES(1,?,?,?,?)",
                           (index + 1, "teacher" if index == 0 else "student", stamp(at), stamp(at)))
            db.execute("INSERT INTO session(token_hash,user_id,csrf_hash,session_version,expires_at,last_seen_at,created_at) "
                       "VALUES(?,1,?,0,?,?,?)", (hashlib.sha256(teacher_token.encode()).hexdigest(),
                                               hashlib.sha256(teacher_csrf.encode()).hexdigest(),
                                               stamp(at + timedelta(hours=2)), stamp(at), stamp(at)))
        students = mint_sessions(database, secret, 1, args.students)
        with closing(socket.socket()) as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = dict(os.environ, PYTHONUTF8="1", APP_ENV="development", SECRET_KEY=secret, APP_ORIGIN=base,
                   DATABASE_PATH=str(database), UPLOAD_ROOT=str(root / "uploads"), HOST="127.0.0.1", PORT=str(port))
        with (root / "web.log").open("w", encoding="utf-8") as log:
            web = subprocess.Popen([sys.executable, "-m", "backend.serve"], cwd=ROOT, env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 30
                while call(base, "GET", "/api/v1/health", timeout=1)[0] not in (200, 503):
                    if web.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("Waitress failed to start")
                    time.sleep(0.1)
                status, body, _ = call(base, "POST", "/api/v1/courses/1/attendance-tasks",
                                       {"title": "Synthetic attendance", "start_at": stamp(at - timedelta(minutes=1)),
                                        "late_at": stamp(at + timedelta(minutes=20)), "end_at": stamp(at + timedelta(minutes=30))},
                                       teacher_token, teacher_csrf)
                if status != 201:
                    raise RuntimeError(f"Attendance setup failed: {status} {body}")
                task = body["data"]

                def requests(student):
                    token, csrf = student["token"], student["csrf"]
                    return [call(base, "POST", f"/api/v1/attendance-tasks/{task['id']}/check-ins", {"code": task["code"]}, token, csrf),
                            call(base, "GET", "/api/v1/auth/session", cookie=token),
                            call(base, "GET", "/api/v1/courses", cookie=token),
                            call(base, "POST", "/api/v1/courses/1/assistant/ask", {"question": "最近7天考勤"}, token, csrf)]

                with ThreadPoolExecutor(max_workers=args.students) as pool:
                    results = [row for group in pool.map(requests, students) for row in group]
                latencies = sorted(row[2] for row in results)
                failed = [row for row in results if row[0] not in (200, 201)]
                with closing(connect(database)) as db:
                    records = db.execute("SELECT COUNT(*) FROM attendance_record").fetchone()[0]
                report.update(requests=len(results), failures=len(failed), attendance_records=records,
                              p95_ms=round(latencies[min(len(latencies) - 1, int(len(latencies) * .95))], 1),
                              max_ms=round(latencies[-1], 1), errors=[{"status": row[0], "body": row[1]} for row in failed[:3]])
                paused = subprocess.run([sys.executable, "-m", "flask", "--app", "backend.app", "maintenance", "on"],
                                        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30, check=True)
                report["maintenance_cli"] = paused.returncode == 0
                blocked = call(base, "GET", "/api/v1/courses", cookie=teacher_token)
                report["maintenance_blocks_existing_session"] = blocked[0] == 503 and blocked[1]["error"]["code"] == "MAINTENANCE"
                report["passed"] = not failed and records == args.students and report["maintenance_blocks_existing_session"]
            finally:
                if os.name == "nt":
                    # venv's Windows launcher owns a second Python process; terminate the test tree.
                    subprocess.run(["taskkill", "/PID", str(web.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=10)
                else:
                    web.terminate()
                try:
                    web.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    web.kill()
                    web.wait(timeout=5)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
