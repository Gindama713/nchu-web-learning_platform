"""并发高压探测：找竞态、重复记录、DB_BUSY、座位抢占。"""
from __future__ import annotations

import concurrent.futures
import http.cookiejar
import json
import sqlite3
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

BASE = "http://127.0.0.1:5000"
DB = Path(r"D:\Desktop\WebBigHomework\wt-demo\instance\app.db")
OUT = Path(r"D:\Desktop\WebBigHomework\.workbuddy\tmp\deep-concurrency.json")

FINDINGS = []


def note(kind, detail):
    FINDINGS.append({"kind": kind, "detail": detail})
    print(f"[{kind}] {detail[:220]}")


def S():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar), urllib.request.ProxyHandler({}))


def call(op, method, path, body=None, csrf=None, origin=BASE):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("Origin", origin)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if csrf and method != "GET":
        req.add_header("X-CSRF-Token", csrf)
    try:
        with op.open(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as failure:
        return failure.code, failure.read().decode("utf-8", "replace")
    except Exception as failure:  # noqa: BLE001
        return 0, json.dumps({"transport": str(failure)}, ensure_ascii=False)


def login(op, number, password):
    status, raw = call(op, "POST", "/api/v1/auth/login",
                       {"student_no": number, "password": password})
    return status, (json.loads(raw).get("data") or {}).get("csrf_token", "")


def ro(sql, params=()):
    conn = sqlite3.connect("file:" + str(DB) + "?mode=ro", uri=True)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def main():
    teacher = S()
    student = S()
    other = S()
    t_status, t_csrf = login(teacher, "teacher", "teacher")
    s_status, s_csrf = login(student, "24201718", "24201718")
    o_status, o_csrf = login(other, "24201502", "24201502")
    print("login", t_status, s_status, o_status)

    now = datetime.now(UTC)
    z = lambda m: (now + timedelta(minutes=m)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    title = "压测-g24201710-%s" % uuid.uuid4().hex[:5]

    # ---------- 1. 并发创建点到任务 ----------
    create_body = {"title": title + "-race", "start_at": z(-1), "late_at": z(8), "end_at": z(20)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(call, teacher, "POST", "/api/v1/courses/16/attendance-tasks",
                               dict(create_body, title=title + "-race-%d" % i), t_csrf)
                   for i in range(6)]
        created = [f.result() for f in futures]
    statuses = [s for s, _ in created]
    failures = [(s, r[:160]) for s, r in created if s >= 500]
    note("并发建任务", f"6 并发，状态={statuses}，5xx={len(failures)} {failures[:2]}")
    race_titles = [title + "-race-%d" % i for i in range(6)]
    placeholders = ",".join("?" for _ in race_titles)
    rows = ro("SELECT id,title FROM attendance_task WHERE title IN (" + placeholders + ")",
              race_titles)
    note("并发建任务_落库", f"期望 6 条，库内 {len(rows)} 条，ids={[r[0] for r in rows]}")

    # 收尾：关闭刚建的并发任务，避免残留 open 任务
    for tid, _ in rows:
        call(teacher, "POST", "/api/v1/attendance-tasks/%d/close" % tid, {}, t_csrf)

    # ---------- 2. 并发签到幂等 ----------
    status, raw = call(teacher, "POST", "/api/v1/courses/16/attendance-tasks",
                       {"title": title + "-checkin", "start_at": z(-1),
                        "late_at": z(8), "end_at": z(20)}, t_csrf)
    task = (json.loads(raw).get("data") or {})
    tid, code = task.get("id"), task.get("code")
    note("并发签到_准备", f"task_id={tid}, code={'有' if code else '无'}, status={status}")
    if tid and code:
        def one_check(_):
            # 复用同一已登录会话：每线程重新登录会撞 20 次/分钟限流，
            # 得到 401 只是测试方的问题，压不到服务端幂等。
            return call(student, "POST", "/api/v1/attendance-tasks/%d/check-ins" % tid,
                        {"code": code}, s_csrf)

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(one_check, range(6)))
        sts = [s for s, _ in results]
        ids = []
        for _, r in results:
            try:
                ids.append((json.loads(r).get("data") or {}).get("id"))
            except Exception:  # noqa: BLE001
                ids.append(None)
        rows = ro("SELECT id,status,source FROM attendance_record "
                  "WHERE task_id=? AND student_id=151", (tid,))
        note("并发签到_结果", f"6 并发状态={sts}，返回记录 id={ids}，"
             f"库内该生记录数={len(rows)}（应为 1），明细={rows[:3]}")
        if len(rows) != 1:
            note("并发签到_竞态缺陷", f"同一学生产生 {len(rows)} 条记录，幂等被并发击穿")
        call(teacher, "POST", "/api/v1/attendance-tasks/%d/close" % tid, {}, t_csrf)

    # ---------- 3. 并发抢同一空位 ----------
    status, raw = call(teacher, "GET", "/api/v1/courses/16/seats", None, t_csrf)
    seats = (json.loads(raw).get("data") or {}).get("seats") or []
    occupied = {(x["group_no"], x["seat_no"]) for x in seats}
    status, raw = call(teacher, "GET", "/api/v1/courses/16/classroom", None, t_csrf)
    room = json.loads(raw).get("data") or {}
    free = [(r, c) for r in range(1, (room.get("rows") or 18) + 1)
            for c in range(1, (room.get("cols") or 10) + 1)
            if (r, c) not in occupied]
    note("并发占座_空位", f"教室 {room.get('rows')}×{room.get('cols')}，已占 {len(occupied)}，"
         f"空位 {len(free)}，取 {free[:1]}")
    if free:
        row, col = free[0]

        sessions = {"24201718": (student, s_csrf), "24201502": (other, o_csrf)}

        def grab(number):
            op, csrf = sessions[number]
            return number, call(op, "PUT", "/api/v1/courses/16/me/seat",
                                {"group_no": row, "seat_no": col}, csrf)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            grabbed = list(pool.map(grab, ["24201718", "24201502"]))
        for number, (s, r) in grabbed:
            note("并发占座_响应", f"{number} -> {s} {r[:160]}")
        holders = ro("SELECT student_id,group_no,seat_no FROM class_seat "
                     "WHERE course_id=16 AND group_no=? AND seat_no=?", (row, col))
        note("并发占座_落库", f"目标 ({row},{col}) 的占用行数={len(holders)}（应 ≤1），{holders}")

    # ---------- 4. 并发读压测 ----------
    read_paths = [
        "/api/v1/courses/16/members?page_size=100",
        "/api/v1/courses/16/attendance-tasks",
        "/api/v1/courses/16/attendance-records?page_size=100",
        "/api/v1/logs/summary",
        "/api/v1/alu74181/compute?a=9&b=5&op=add",
        "/who", "/help",
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        jobs = [pool.submit(call, teacher, "GET", read_paths[i % len(read_paths)], None, t_csrf)
                for i in range(120)]
        reads = [j.result() for j in jobs]
    bad = [(s, r[:120]) for s, r in reads if s >= 500 or s == 0]
    note("并发读压测", f"120 个并发 GET，5xx/连接失败={len(bad)} {bad[:2]}")

    # ---------- 5. 并发写同一任务（close 重复调用） ----------
    status, raw = call(teacher, "POST", "/api/v1/courses/16/attendance-tasks",
                       {"title": title + "-close", "start_at": z(-1),
                        "late_at": z(5), "end_at": z(12)}, t_csrf)
    ctid = (json.loads(raw).get("data") or {}).get("id")
    if ctid:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            closes = list(pool.map(
                lambda _: call(teacher, "POST", "/api/v1/attendance-tasks/%d/close" % ctid,
                               {}, t_csrf), range(6)))
        sts = [s for s, _ in closes]
        state = ro("SELECT status FROM attendance_task WHERE id=?", (ctid,))
        note("并发关闭", f"6 并发状态={sts}，库内状态={state}，"
             f"5xx={sum(1 for s in sts if s >= 500)}")

    OUT.write_text(json.dumps({"findings": FINDINGS}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("\n输出", OUT, "共", len(FINDINGS), "条记录")


if __name__ == "__main__":
    main()
