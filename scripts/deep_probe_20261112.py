"""高强度探测：不预设结论，只收集真实响应。不修代码、不删数据。"""
from __future__ import annotations

import json
import http.cookiejar
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

BASE = "http://127.0.0.1:5000"
OUT = Path(r"D:\Desktop\WebBigHomework\.workbuddy\tmp\deep-probe.json")


def S(label):
    jar = http.cookiejar.CookieJar()
    return label, urllib.request.build_opener(
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
        with op.open(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as failure:
        return failure.code, failure.read().decode("utf-8", "replace")
    except Exception as failure:  # noqa: BLE001
        return 0, json.dumps({"transport": str(failure)}, ensure_ascii=False)


def login(op, number, password):
    status, raw = call(op, "POST", "/api/v1/auth/login",
                       {"student_no": number, "password": password})
    return status, (json.loads(raw).get("data") or {}).get("csrf_token", "")


FINDINGS = []
SUMMARY = defaultdict(int)


def note(kind, detail):
    FINDINGS.append({"kind": kind, "detail": detail})
    SUMMARY[kind] += 1
    print(f"[{kind}] {detail[:200]}")


def main():
    _, anon = S("anon")
    _, top = S("teacher")
    _, stu = S("student")
    t_status, t_csrf = login(top, "teacher", "teacher")
    s_status, s_csrf = login(stu, "24201718", "24201718")
    print("login", t_status, s_status)

    # ---------- A. 74181 全 512 组独立对照 ----------
    status, raw = call(anon, "GET", "/api/v1/alu74181/table")
    rows = (json.loads(raw).get("data") or {}).get("rows") or []
    mismatches = []
    for row in rows:
        op = row["op"]
        a, b = row["a"], row["b"]
        if op == "add":
            operand_b, carry_in, dec = b, 0, a + b
        else:
            operand_b, carry_in, dec = (~b) & 15, 1, a - b
        total = a + operand_b + carry_in
        f, carry = total & 15, 1 if total > 15 else 0
        expect = {
            "f": f, "f_hex": f"0x{f:X}", "f_bits": format(f, "04b"),
            "internal_sum": total, "operand_b": operand_b,
            "operand_b_bits": format(operand_b, "04b"),
            "carry_in": carry_in, "carry": carry, "cn4": 0 if carry else 1,
            "zero": 1 if f == 0 else 0, "equal": 1 if a == b else 0,
            "decimal_result": dec,
            "borrow": (1 - carry) if op == "sub" else None,
        }
        diffs = {k: (row.get(k), v) for k, v in expect.items() if row.get(k) != v}
        if diffs:
            mismatches.append({"op": op, "a": a, "b": b, "diffs": diffs})
    note("74181_全量对照", f"{len(rows)} 组，独立实现不一致 {len(mismatches)} 组"
         + (f"，样例 {json.dumps(mismatches[:2], ensure_ascii=False)}" if mismatches else ""))

    # ---------- B. 27 个 blueprint 代表端点抽查 ----------
    status, raw = call(anon, "GET", "/help")
    modules = (json.loads(raw).get("data") or {}).get("modules") or []
    cid = 16
    path_sub = {
        "{course_id}": str(cid), "{id}": "1", "{task_id}": "55",
        "{record_id}": "1", "{user_id}": "1", "{student_id}": "151",
        "{leave_id}": "1", "{notification_id}": "1", "{version_id}": "1",
        "{experiment_id}": "1", "{submission_id}": "1", "{run_id}": "1",
        "{suite_id}": "1", "{validation_id}": "1", "{class_id}": "1",
        "{paper_id}": "1", "{assessment_id}": "1", "{attempt_id}": "1",
        "{question_id}": "1", "{practice_id}": "1", "{quiz_id}": "1",
        "{session_id}": "1", "{demo_id}": "1", "{preparation_id}": "1",
        "{resource_id}": "1", "{knowledge_id}": "1", "{swap_id}": "1",
    }
    import re
    server_errors = []
    ok_count = 0
    for m in modules:
        blueprint = m.get("blueprint")
        gets = [e["path"] for e in m.get("endpoints", []) if e.get("method", "").startswith("GET")]
        if not gets:
            continue
        path = sorted(gets, key=len)[0]
        for key, value in path_sub.items():
            path = path.replace(key, value)
        path = re.sub(r"\{[^}]+\}", "1", path)
        status, raw = call(top, "GET", path, None, t_csrf)
        if status >= 500:
            server_errors.append({"blueprint": blueprint, "path": path, "status": status,
                                  "body": raw[:300]})
            note("模块抽查_5xx", f"{blueprint} GET {path} -> {status} {raw[:120]}")
        else:
            ok_count += 1
    note("模块抽查_汇总", f"抽查 {ok_count + len(server_errors)} 个 blueprint，"
         f"5xx {len(server_errors)} 个，其余 {ok_count} 个非 5xx")

    # ---------- C. 参数边界轰炸（只找 5xx 与信息泄露） ----------
    evil_bodies = [
        {}, {"title": None}, {"title": "x" * 10000},
        {"title": ["a", "b"]}, {"title": {"nested": 1}}, {"title": 12345},
        {"title": "'; DROP TABLE user; --"}, {"title": "<script>alert(1)</script>"},
        {"page_size": -1}, {"page_size": 1e9}, {"page_size": "abc"},
        {"start_at": "not-a-date"}, {"a": -1, "b": 16},
    ]
    write_targets = [
        "/api/v1/courses/16/attendance-tasks",
        "/api/v1/courses/16/classroom",
        "/api/v1/courses/16/members",
    ]
    for path in write_targets:
        for body in evil_bodies:
            status, raw = call(top, "POST" if "attendance-tasks" in path or "members" in path else "PUT",
                               path, body, t_csrf)
            if status >= 500:
                note("边界_5xx", f"{path} body={str(body)[:60]} -> {status} {raw[:150]}")
            if "Traceback" in raw or "sqlite3." in raw or "File \"" in raw:
                note("边界_栈泄露", f"{path} body={str(body)[:60]} -> {raw[:150]}")
    get_targets = [
        "/api/v1/courses/16/members?page_size=-5",
        "/api/v1/courses/16/members?page_size=999999",
        "/api/v1/courses/16/members?page=abc",
        "/api/v1/courses/16/attendance-records?page_size=100000",
        "/api/v1/alu74181/compute?a=-1&b=1&op=add",
        "/api/v1/alu74181/compute?a=1&b=1&op=__import__",
        "/api/v1/logs/access?page_size=999999",
        "/api/v1/users/lookup?q=%27%20OR%201%3D1--",
    ]
    for path in get_targets:
        status, raw = call(top, "GET", path, None, t_csrf)
        if status >= 500:
            note("边界_GET_5xx", f"{path} -> {status} {raw[:150]}")
        if "Traceback" in raw or "sqlite3." in raw:
            note("边界_GET_栈泄露", f"{path} -> {raw[:150]}")
    note("边界_汇总", f"写请求 {len(write_targets) * len(evil_bodies)} 组、读请求 {len(get_targets)} 组")

    # ---------- D. 权限矩阵：学生访问教师/管理员端点 ----------
    protected = [
        ("GET", "/api/v1/users"),
        ("GET", "/api/v1/admin/audit-events"),
        ("GET", "/api/v1/logs/access"),
        ("GET", "/api/v1/logs/access.csv"),
        ("GET", "/api/v1/logs/audit.csv"),
        ("GET", "/api/v1/logs/summary"),
        ("GET", "/api/v1/courses/16/members"),
        ("POST", "/api/v1/courses/16/attendance-tasks"),
        ("PUT", "/api/v1/courses/16/classroom"),
        ("POST", "/api/v1/courses/16/classroom/auto-seat"),
        ("PATCH", "/api/v1/attendance-records/1"),
        ("PATCH", "/api/v1/users/1"),
        ("POST", "/api/v1/courses"),
    ]
    for method, path in protected:
        body = {} if method != "GET" else None
        status, raw = call(stu, method, path, body, s_csrf)
        if status == 200:
            note("权限_学生越权成功", f"{method} {path} -> 200（学生不应有此权限）{raw[:100]}")
        elif status >= 500:
            note("权限_5xx", f"{method} {path} -> {status} {raw[:120]}")
    note("权限_汇总", f"学生会话探测 {len(protected)} 个受保护端点")

    # ---------- E. 匿名访问受保护端点 ----------
    for method, path in protected[:8]:
        status, raw = call(anon, method, path, {} if method != "GET" else None)
        if status not in (401, 403):
            note("权限_匿名未拒", f"{method} {path} -> {status} {raw[:100]}")

    # ---------- F. 会话失效 ----------
    _, tmp = S("logout")
    _, tok = login(tmp, "24201502", "24201502")
    call(tmp, "POST", "/api/v1/auth/logout", {}, tok)
    status, raw = call(tmp, "GET", "/api/v1/auth/session")
    note("会话_注销后", f"logout 后 GET /auth/session -> {status} {raw[:120]}")

    # ---------- G. 404 / 方法 / 超长路径 ----------
    for path in ["/api/v1/nope", "/api/v1/" + "a" * 3000, "/who/../etc/passwd"]:
        status, raw = call(anon, "GET", path)
        if status >= 500:
            note("路由_5xx", f"GET {path[:60]} -> {status} {raw[:120]}")
    status, raw = call(anon, "DELETE", "/who")
    note("路由_方法", f"DELETE /who -> {status}")

    OUT.write_text(json.dumps({"findings": FINDINGS, "summary": dict(SUMMARY),
                               "modules": len(modules), "table_rows": len(rows)},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== 汇总 ===")
    for k, v in sorted(SUMMARY.items()):
        print(f"  {k}: {v}")
    print("输出", OUT)


if __name__ == "__main__":
    main()
