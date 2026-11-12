"""课堂投票的并发压测：全班同时投票，会不会出现重复计票、丢票或 503。

设计要点（和 scripts/db_busy_probe_20261112.py 同一个思路）：
* 用 SECRET_KEY 直接在库里签发会话，绕开登录限流，只量投票这一段。
* 用 threading.Barrier 让 N 个人尽量同一瞬间发请求，否则排队效应会把问题藏起来。
* 不要跑在演示库上：脚本要求 --db 指向一份副本，投完直接丢，不污染课堂数据。

用法（后端要用同一个 SECRET_KEY 启动，并且 --db 指向它正在用的那个库）：
    SECRET_KEY=<64hex> python scripts/poll_burst_20261112.py \
        --base http://127.0.0.1:5003 --db test-tmp/burst/poll.db --course 16 \
        --task 57 --students 160
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta


def stamp(value=None):
    return (value or datetime.now(UTC)).astimezone(UTC).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


def call(base, method, path, payload=None, cookie=None, csrf=None, timeout=30):
    """返回 (status, body, 耗时毫秒)；4xx/5xx 当结果收，连接层失败 status=0。"""
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(base + path, data=data, method=method)
    request.add_header("Origin", base)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if cookie:
        request.add_header("Cookie", f"cpu_session={cookie}")
    if csrf:
        request.add_header("X-CSRF-Token", csrf)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw, status = response.read(), response.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(), exc.code
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {str(exc)[:60]}", (time.perf_counter() - started) * 1000
    elapsed = (time.perf_counter() - started) * 1000
    try:
        body = json.loads(raw.decode() or "{}")
    except ValueError:
        body = {"raw": raw[:120].decode(errors="replace")}
    return status, body, elapsed


def login(base, student_no, password):
    data = json.dumps({"student_no": student_no, "password": password}).encode()
    request = urllib.request.Request(base + "/api/v1/auth/login", data=data, method="POST")
    request.add_header("Origin", base)
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            cookie = response.headers.get("Set-Cookie", "")
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return None, None, f"HTTP {exc.code} {exc.read()[:120].decode(errors='replace')}"
    token = cookie.split("cpu_session=")[1].split(";")[0] if "cpu_session=" in cookie else None
    return token, body.get("data", {}).get("csrf_token"), None


def mint_sessions(db_path, secret, course_id, limit):
    """直接在库里签发会话：登录限流是每 IP 每分钟 20 次，压测绕不开它。"""
    sql = ("SELECT m.user_id, u.student_no, u.name, u.session_version "
           "FROM course_member m JOIN user u ON u.id=m.user_id "
           "WHERE m.course_id=? AND m.member_role='student' AND m.active=1 "
           "AND u.role='student' AND u.active=1 ORDER BY m.user_id LIMIT ?")
    db = sqlite3.connect(db_path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        now = datetime.now(UTC)
        made = []
        for row in db.execute(sql, (course_id, limit)).fetchall():
            token = secrets.token_hex(24)
            csrf = hmac.new(secret.encode(), token.encode(), "sha256").hexdigest()
            db.execute(
                "INSERT INTO session(token_hash,user_id,csrf_hash,session_version,expires_at,"
                "last_seen_at,created_at) VALUES(?,?,?,?,?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), row["user_id"],
                 # 库里存 sha256(csrf_token)，不是 csrf_token 本身（见 identity.login）
                 hashlib.sha256(csrf.encode()).hexdigest(),
                 row["session_version"], stamp(now + timedelta(hours=3)), stamp(now), stamp(now)))
            made.append({"token": token, "csrf": csrf, "no": row["student_no"],
                         "name": row["name"], "id": row["user_id"]})
        db.commit()
        return made
    finally:
        db.close()


def summarise(label, results):
    codes, latencies = {}, []
    for status, _body, elapsed in results:
        codes[status] = codes.get(status, 0) + 1
        if status:
            latencies.append(elapsed)
    latencies.sort()

    def pct(share):
        return latencies[min(len(latencies) - 1, int(len(latencies) * share))] if latencies else 0

    ok = sum(codes.get(code, 0) for code in (200, 201, 204))
    print(f"\n--- {label} ---")
    print("  状态码：" + "，".join(f"{k}×{v}" for k, v in sorted(codes.items())))
    print(f"  成功 {ok}/{len(results)} = {ok / len(results) * 100:.1f}%")
    if latencies:
        print(f"  延迟 p50 {pct(0.5):.0f}ms  p95 {pct(0.95):.0f}ms  max {latencies[-1]:.0f}ms"
              f"  mean {statistics.mean(latencies):.0f}ms")
    for status, body, _ in [item for item in results if item[0] >= 400 or item[0] == 0][:3]:
        text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)[:170]
        print(f"  失败样例 {status}: {text}")
    return ok, len(results)


def check_rows(db_path, poll_id, expected_ballots, expected_choices):
    db = sqlite3.connect(db_path, timeout=10)
    try:
        ballots = db.execute("SELECT COUNT(*) FROM poll_ballot WHERE poll_id=?",
                             (poll_id,)).fetchone()[0]
        choices = db.execute(
            "SELECT COUNT(*) FROM poll_choice c JOIN poll_ballot b ON b.id=c.ballot_id "
            "WHERE b.poll_id=?", (poll_id,)).fetchone()[0]
        duplicates = db.execute(
            "SELECT COUNT(*) FROM (SELECT student_id FROM poll_ballot WHERE poll_id=? "
            "GROUP BY student_id HAVING COUNT(*)>1)", (poll_id,)).fetchone()[0]
    finally:
        db.close()
    print(f"  库内：ballot {ballots} 行（应 {expected_ballots}），choice {choices} 行"
          f"（应 {expected_choices}），同一人重复投票 {duplicates} 人")
    return ballots == expected_ballots and choices == expected_choices and duplicates == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5003")
    parser.add_argument("--db", default="test-tmp/burst/poll.db")
    parser.add_argument("--course", type=int, default=16)
    parser.add_argument("--task", type=int, default=0, help="挂在哪个进行中的考勤任务上；0 = 自动挑一个")
    parser.add_argument("--students", type=int, default=160)
    args = parser.parse_args()

    secret = os.environ.get("SECRET_KEY", "")
    if len(secret) < 32:
        sys.exit("需要与后端相同的 SECRET_KEY（>=32 字符）才能签发会话")
    if not os.path.exists(args.db):
        sys.exit(f"找不到库 {args.db}：先复制一份演示库再跑，别直接压课堂数据")

    cookie, csrf, error = login(args.base, "teacher", "teacher")
    if not cookie:
        sys.exit(f"教师登录失败：{error}")

    # 1) 找一条进行中的任务，并确认它真的有签到过的人（不然投票资格 403）
    status, body, _ = call(args.base, "GET",
                           f"/api/v1/courses/{args.course}/attendance-tasks?page_size=50", cookie=cookie)
    if status != 200:
        sys.exit(f"读任务失败 {status}")
    tasks = [task for task in body["data"] if task["status"] == "open"]
    if args.task:
        tasks = [task for task in tasks if task["id"] == args.task]
    if not tasks:
        sys.exit("没有进行中的考勤任务，先开一条并让学生签到")
    task = tasks[0]
    print(f"挂在任务 #{task['id']}「{task['title']}」上")

    # 2) 发起一场实名单选投票
    status, body, _ = call(args.base, "POST", f"/api/v1/courses/{args.course}/polls", {
        "task_id": task["id"], "title": f"并发压测 {datetime.now():%H:%M:%S}",
        "type": "single", "options": ["1 处", "2 处", "3 处"],
        "correct_ordinals": [2], "anonymous": False,
    }, cookie=cookie, csrf=csrf)
    if status not in (200, 201):
        sys.exit(f"发起投票失败 {status}: {json.dumps(body, ensure_ascii=False)[:200]}")
    poll = body["data"]
    poll_id = poll["id"]
    option_ids = [option["id"] for option in poll["options"]]
    print(f"投票 #{poll_id} 已开，应投 {poll['eligible']} 人")

    # 3) 签发 N 个学生会话
    people = mint_sessions(args.db, secret, args.course, args.students)
    print(f"已签发 {len(people)} 个学生会话")
    if not people:
        sys.exit("该课程没有可用学生")

    # 4) 栅栏同步：全班同一瞬间点「提交」
    barrier = threading.Barrier(len(people))
    results = [None] * len(people)
    picks = [None] * len(people)

    def voter(index, person):
        barrier.wait()
        call(args.base, "GET", f"/api/v1/polls/{poll_id}", cookie=person["token"])
        # 一半人选正确答案（第 2 项），一半人选错，方便核对对错统计
        pick = option_ids[1] if index % 2 == 0 else option_ids[0]
        picks[index] = pick
        results[index] = call(args.base, "POST", f"/api/v1/polls/{poll_id}/ballots",
                             {"option_ids": [pick]}, cookie=person["token"], csrf=person["csrf"])

    threads = [threading.Thread(target=voter, args=(index, person))
               for index, person in enumerate(people)]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.perf_counter() - started

    voters = len(people)
    ok, total = summarise(f"{voters} 人同时投票（总耗时 {wall:.2f}s）", results)
    right = (voters + 1) // 2
    stored = check_rows(args.db, poll_id, total, total)

    # 5) 同一人并发点两次：应当一成一败，不能变成两票
    racer = people[0]
    same = [None, None]
    barrier2 = threading.Barrier(2)

    def twice(slot):
        barrier2.wait()
        same[slot] = call(args.base, "POST", f"/api/v1/polls/{poll_id}/ballots",
                          {"option_ids": [option_ids[0]]},
                          cookie=racer["token"], csrf=racer["csrf"])

    pair = [threading.Thread(target=twice, args=(slot,)) for slot in (0, 1)]
    for thread in pair:
        thread.start()
    for thread in pair:
        thread.join()
    codes = sorted(item[0] for item in same)
    print(f"\n--- 同一人同时点两次 ---\n  状态码 {codes}（期望 [201, 409] 或 [409, 409]）")

    # 6) 老师看结果：票数、对错、未投名单都要对得上
    status, body, _ = call(args.base, "GET", f"/api/v1/polls/{poll_id}/results", cookie=cookie)
    report = body.get("data", {})
    print(f"\n--- 老师端结果 ---")
    print(f"  voted {report.get('voted')} / eligible {report.get('eligible')}")
    correct = report.get("correct") or {}
    print(f"  对 {correct.get('right')} 错 {correct.get('wrong')} 正确率 {correct.get('accuracy')}")
    print(f"  明细 {len(report.get('details') or [])} 行，未投 {len(report.get('unvoted') or [])} 人")

    problems = []
    if ok != total:
        problems.append(f"{total - ok} 人投票失败")
    if not stored:
        problems.append("库内行数或唯一性不对")
    if report.get("voted") != total:
        problems.append(f"计票 {report.get('voted')} ≠ {total}")
    if correct.get("right") != right or correct.get("wrong") != total - right:
        problems.append(f"对错统计 {correct.get('right')}/{correct.get('wrong')} 与预期 {right}/{total - right} 不符")
    if codes.count(201) > 1:
        problems.append("同一人被计了两票")

    print("\n== 结论 ==")
    print("  全部通过" if not problems else "  存在问题：" + "；".join(problems))
    sys.exit(0 if not problems else 2)


if __name__ == "__main__":
    main()
