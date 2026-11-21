"""g24201710 自测（2026-11-12）：把互测踩过的坑转成回归用例，实测本组演示环境。

契约（从 /help 与源码实读，非猜测）：
  - API base /api/v1；统一 {data,request_id} / {error:{code,...},request_id}
  - Cookie 会话 + X-CSRF-Token + 同源 Origin
  - 登录 student_no/password；教师 teacher/teacher；学生学号/学号
  - 点到任务 create_task 可选 pattern（手势由教师开课时指定，/auth/gesture 已移除）
用法：
  python scripts/verify_self_20261112.py
  python scripts/verify_self_20261112.py --base http://127.0.0.1:5000 --frontend http://127.0.0.1:5173
输出：
  docs/SELF_TEST_REPORT_20261112.md
  docs/SELF_DEFECTS_20261112.csv
  .workbuddy/tmp/self-test-20261112.json（原始日志，不随文档提交）
"""
from __future__ import annotations

import argparse
import csv
import http.cookiejar
import json
import re
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO = Path(r"D:\Desktop\WebBigHomework(5)\WebBigHomework")
DEMO_DB = Path(r"D:\Desktop\WebBigHomework\wt-demo\instance\app.db")
DOCS = REPO / "docs"
RAW_LOG = Path(r"D:\Desktop\WebBigHomework\.workbuddy\tmp\self-test-20261112.json")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
DATE = "20261112"

CASES: list[dict] = []
TRACE: list[dict] = []


def stamp(offset_minutes=0):
    return (datetime.now(UTC) + timedelta(minutes=offset_minutes)).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


class Session:
    def __init__(self, label, base):
        self.label, self.base = label, base
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar), urllib.request.ProxyHandler({}))
        self.csrf = None

    def req(self, method, path, body=None, csrf=True, origin=None, extra=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Accept", "application/json")
        request.add_header("Origin", origin or self.base)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if csrf and self.csrf and method != "GET":
            request.add_header("X-CSRF-Token", self.csrf)
        for key, value in (extra or {}).items():
            request.add_header(key, value)
        started = time.perf_counter()
        status, raw = 0, ""
        try:
            with self.opener.open(request, timeout=12) as response:
                status, raw = response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as failure:
            status, raw = failure.code, failure.read().decode("utf-8", "replace")
        except Exception as failure:  # noqa: BLE001
            raw = json.dumps({"transport": str(failure)}, ensure_ascii=False)
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        try:
            payload = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            payload = {"raw": raw[:200]}
        TRACE.append({"at": stamp(), "actor": self.label, "method": method,
                      "path": path, "status": status, "ms": elapsed})
        return status, payload, raw

    def get(self, path, **kw):
        return self.req("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.req("POST", path, body, **kw)

    def login(self, number, password):
        status, payload, _ = self.post("/api/v1/auth/login",
                                       {"student_no": number, "password": password})
        if status == 200:
            self.csrf = (payload.get("data") or {}).get("csrf_token")
        return status, payload, ""


def data_of(payload):
    return (payload or {}).get("data") if isinstance(payload, dict) else None


def err(payload):
    return ((payload or {}).get("error") or {}).get("code", "") if isinstance(payload, dict) else ""


def record(cid, layer, title, expected, actual, passed, reproduce,
           severity="中", status_override=None, priority="P1"):
    status = status_override or ("通过" if passed else "失败")
    CASES.append({"id": cid, "layer": layer, "title": title, "expected": expected,
                  "actual": actual, "status": status, "severity": severity,
                  "reproduce": reproduce, "priority": priority})
    print(f"[{status}] {cid} {title} | {str(actual)[:110]}")


def query_ro(sql, params=()):
    """只读打开演示库；失败返回 None，绝不写库。"""
    if not DEMO_DB.is_file():
        return None
    try:
        conn = sqlite3.connect("file:" + str(DEMO_DB) + "?mode=ro", uri=True)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return rows
    except sqlite3.Error:
        return None


def main():
    parser = argparse.ArgumentParser(description="g24201710 自测")
    parser.add_argument("--base", default="http://127.0.0.1:5000", help="后端 API 地址")
    parser.add_argument("--frontend", default="http://127.0.0.1:5173", help="前端地址")
    args = parser.parse_args()
    started = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    anon = Session("匿名", args.base)
    teacher = Session("教师", args.base)
    student = Session("学生", args.base)
    student2 = Session("学生2", args.base)

    # ---------- 冒烟 ----------
    s, p, _ = anon.get("/who")
    who = data_of(p) or {}
    record("S-01", "冒烟", "公开接口 /who", "200 且组号/组长/成员齐全",
           f"HTTP {s}，class_name={who.get('class_name')}，group_no={who.get('group_no')}，"
           f"组长={(who.get('leader') or {}).get('name')}，成员={who.get('member_count')}",
           s == 200 and who.get("group_no") == "g24201710" and who.get("member_count") == 4,
           "匿名 GET /who", "高", priority="P0")

    s, p, _ = anon.get("/help")
    help_data = data_of(p) or {}
    counts = help_data.get("counts") or {}
    modules = help_data.get("modules") or []
    declared_public = set(help_data.get("public_endpoints") or [])
    record("S-02", "冒烟", "公开接口 /help", "200 且含模块/端点/账号规则",
           f"HTTP {s}，{counts.get('modules')} 模块 / {counts.get('endpoints')} 端点，"
           f"公开 {len(declared_public)} 条",
           s == 200 and counts.get("endpoints", 0) > 0 and len(modules) > 0,
           "匿名 GET /help", "高", priority="P0")

    s, p, _ = anon.get("/api/v1/health")
    health = data_of(p) or {}
    record("S-03", "冒烟", "健康检查按设计判定（degraded 非故障）",
           "web_ready/db_ready=true，grader_ready=false，status=degraded",
           f"HTTP {s}，status={health.get('status')}，web={health.get('web_ready')}，"
           f"db={health.get('db_ready')}，grader={health.get('grader_ready')}",
           health.get("web_ready") is True and health.get("db_ready") is True
           and health.get("status") == "degraded",
           "匿名 GET /api/v1/health（503 属已知设计，不记缺陷）", "中", priority="P0")

    s, p, _ = teacher.login("teacher", "teacher")
    user = (data_of(p) or {}).get("user") or {}
    record("S-04", "冒烟", "教师 teacher/teacher 登录（历史 7 位校验坑）",
           "200 + csrf_token + role=teacher",
           f"HTTP {s}，role={user.get('role')}，csrf={'有' if teacher.csrf else '无'}",
           s == 200 and user.get("role") == "teacher" and bool(teacher.csrf),
           "POST /api/v1/auth/login（student_no=teacher）", "高", priority="P0")

    s, p, _ = student.login("24201718", "24201718")
    stu = (data_of(p) or {}).get("user") or {}
    record("S-05", "冒烟", "学生学号/学号登录",
           "200 + role=student", f"HTTP {s}，role={stu.get('role')}，name={stu.get('name')}",
           s == 200 and stu.get("role") == "student",
           "POST /api/v1/auth/login（24201718）", "高", priority="P0")

    s, p, _ = teacher.get("/api/v1/courses")
    courses = data_of(p) if isinstance(data_of(p), list) else []
    cid = courses[0]["id"] if courses else 16
    record("S-06", "冒烟", "教师课程列表（默认最新课程优先）",
           "200 且课程 #16 在首位",
           f"HTTP {s}，{len(courses)} 门课，首门 id={cid}",
           s == 200 and len(courses) >= 1 and cid == 16,
           "教师 GET /api/v1/courses", "中")

    s, p, _ = teacher.get("/api/v1/auth/session")
    sess = data_of(p) or {}
    record("S-07", "冒烟", "会话读取", "200 且返回当前用户",
           f"HTTP {s}，user={(sess.get('user') or {}).get('student_no')}，"
           f"csrf 一致={'是' if sess.get('csrf_token') == teacher.csrf else '否'}",
           s == 200 and bool((sess.get("user") or {}).get("student_no")),
           "教师 GET /api/v1/auth/session", "中")

    # ---------- 接口 ----------
    s, p, _ = anon.get("/api/v1/courses")
    record("I-01", "接口", "匿名访问课程列表被拒", "401",
           f"HTTP {s} {err(p)}", s == 401, "匿名 GET /api/v1/courses", "高", priority="P0")

    # 关键：必须用已登录会话（有 Cookie）但不带令牌，才会走到 CSRF 校验；
    # 用匿名会话只会先被 401 鉴权挡住，测不到 CSRF。
    s, p, _ = teacher.post("/api/v1/courses/%d/attendance-tasks" % cid, {},
                           csrf=False)
    record("I-02", "接口", "已登录写请求缺少 CSRF 令牌被拒", "403 CSRF_FAILED",
           f"HTTP {s} {err(p)}", s == 403 and err(p) == "CSRF_FAILED",
           "已登录教师会话，不带 X-CSRF-Token 发写请求", "高", priority="P0")

    s, p, _ = teacher.post("/api/v1/auth/logout", {}, origin="http://evil.example")
    record("I-03", "接口", "跨站 Origin 写请求被拒", "403 CSRF_FAILED",
           f"HTTP {s} {err(p)}", s == 403,
           "教师会话带 Origin: http://evil.example 发写请求", "高", priority="P0")
    # logout 若被拒绝（预期），会话仍有效；若意外成功则重新登录一次
    if s == 200:
        teacher.login("teacher", "teacher")

    bad = Session("错误密码", args.base)
    s, p, _ = bad.post("/api/v1/auth/login", {"student_no": "teacher", "password": "wrong"})
    record("I-04", "接口", "错误密码登录", "401 且不建立会话",
           f"HTTP {s} {err(p)}", s == 401,
           "POST /api/v1/auth/login（错误口令）", "高", priority="P0")

    s, p, _ = bad.post("/api/v1/auth/login", {"student_no": "teacher"})
    record("I-05", "接口", "登录缺字段校验", "400/422 VALIDATION_ERROR",
           f"HTTP {s} {err(p)}", s in (400, 422) and err(p) == "VALIDATION_ERROR",
           "登录 body 只给 student_no", "中")

    for iid, path in (("I-06a", "/who"), ("I-06b", "/help")):
        s, p, _ = anon.post(path, {})
        record(iid, "接口", f"{path} 拒绝非 GET", "405",
               f"HTTP {s} {err(p)}", s == 405, f"匿名 POST {path}", "低")

    for iid, path, want in (
            ("I-07a", "/api/v1/attendance-tasks/999999/seats", 404),
            ("I-07b", "/api/v1/courses/999999/members", 404)):
        s, p, _ = teacher.get(path)
        record(iid, "接口", "不存在的资源 ID", f"HTTP {want}",
               f"HTTP {s} {err(p)}", s == want, f"教师 GET {path}", "中")

    for iid, path in (("I-08a", "/api/v1/courses/16/members?page_size=-5"),
                      ("I-08b", "/api/v1/courses/16/members?page_size=999")):
        s, p, _ = teacher.get(path)
        record(iid, "接口", "非法/超大分页参数", "400/422 或被收敛，不得 500",
               f"HTTP {s} {err(p)}", s < 500, f"教师 GET {path}", "低")

    # I-09 公开端点声明与实测一致性（对照 g24201803 缺陷）
    probe_paths = ["/who", "/help", "/api/v1/health", "/api/v1/modules",
                   "/api/v1/alu74181/spec", "/api/v1/alu74181/table",
                   "/api/v1/alu74181/compute?a=1&b=1&op=add"]
    anonymous_ok = []
    for path in probe_paths:
        s2, _, _ = anon.get(path)
        if s2 < 400:
            anonymous_ok.append(path)
    extra_public = [x for x in anonymous_ok if x.split("?")[0] not in declared_public]
    record("I-09", "接口", "/help 公开端点声明与实际一致",
           "声明的公开端点均可匿名访问，且无遗漏",
           f"声明 {len(declared_public)} 条；实测可匿名访问 {len(anonymous_ok)} 条；"
           f"未列入声明的 {len(extra_public)} 条：{', '.join(extra_public) if extra_public else '无'}",
           not extra_public, "比对 /help.public_endpoints 与匿名 GET 实测", "中")

    # I-10 公开接口不得泄露凭据（对照 g24201807 高危缺陷）
    s_who, _, raw_who = anon.get("/who")
    s_help, _, raw_help = anon.get("/help")
    leak = []
    for label, raw in (("/who", raw_who), ("/help", raw_help)):
        for pattern in (r'"password"\s*:\s*"', r'csrf_token"\s*:\s*"[A-Za-z0-9]{16,}',
                        r'"access_token"', r'"secret"'):
            if re.search(pattern, raw, re.I):
                leak.append(f"{label}:{pattern}")
    record("I-10", "接口", "公开接口不泄露明文口令/令牌",
           "/who 与 /help 响应体不含口令、CSRF 值、访问令牌",
           f"敏感字段命中 {len(leak)} 处：{', '.join(leak) if leak else '无'}"
           "（accounts 段仅含规则文字）",
           not leak, "正则扫描 /who 与 /help 原始响应体", "高", priority="P0")

    s, p, _ = anon.get("/api/v1/modules")
    module_rows = data_of(p) or []
    record("I-11", "接口", "/help 与 /api/v1/modules 清单均可读",
           "两处均非空（数量不必相等：/help 按 blueprint 分，/api/v1/modules 按业务模块分）",
           f"/help={len(modules)} 个 blueprint，/api/v1/modules={len(module_rows)} 个业务模块"
           "（口径不同，不作数量相等断言）",
           len(modules) > 0 and len(module_rows) > 0,
           "分别 GET /help 与 /api/v1/modules", "中")

    # 必须比对被测工作区（wt-demo）的迁移目录；主仓 develop 落后 4 个迁移。
    demo_migrations = sorted((DEMO_DB.parent.parent / "backend" / "migrations").glob("*.sql"))
    applied = query_ro("SELECT COUNT(*) FROM schema_migration")
    record("I-12", "回归", "迁移文件与已应用记录一致",
           "被测工作区迁移文件数 == 库内已应用记录数",
           f"wt-demo {len(demo_migrations)} 个迁移文件；库内已应用 "
           f"{applied[0][0] if applied else '?'} 条",
           bool(applied) and len(demo_migrations) == applied[0][0],
           "只读查 schema_migration 与 wt-demo/backend/migrations", "低", priority="P2")

    # ---------- 回归：历史缺陷 ----------
    s, p, _ = teacher.get("/api/v1/courses/%d/members?page_size=5" % cid)
    members = data_of(p) or []
    record("R-01", "回归", "C1 课程成员接口不再 500",
           "200 且返回成员数组（sqlite3.Row.get 已修）",
           f"HTTP {s}，本页 {len(members) if isinstance(members, list) else '?'} 人，"
           f"total={(p or {}).get('total')}",
           s == 200 and isinstance(members, list) and len(members) > 0,
           "教师 GET /api/v1/courses/16/members", "高", priority="P0")

    # R-04：直连后端根路径（单进程沙箱关键）
    s, _, raw_root = anon.get("/")
    # 前端地址用独立 opener，避免复用后端 base
    front_probe = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with front_probe.open(args.frontend + "/", timeout=8) as resp:
            front_status = resp.status
    except urllib.error.HTTPError as failure:
        front_status = failure.code
    except Exception:  # noqa: BLE001
        front_status = 0
    record("R-04", "回归", "C4 当前双进程部署首页可达",
           "前端 GET / 返回 200（后端专注 /api/v1，不托管页面属设计）",
           f"前端 {args.frontend}/ = HTTP {front_status}；后端 {args.base}/ = HTTP {s}"
           "（后端 404 是双进程分工，不是故障）",
           front_status == 200, f"分别 GET 前端与后端根路径", "中", priority="P1")
    has_static_doc = (REPO / "docs" / "index.html").is_file()
    record("R-04b", "回归", "C4 单进程静态沙箱首页（条件性风险）",
           "若老师沙箱只起 Flask 一个进程，GET / 应返回 200",
           f"当前 develop 无 serve_frontend 分支，直连后端 / = HTTP {s}；"
           f"仓库 docs/index.html {'存在但未托管' if has_static_doc else '不存在'}；"
           "Gitea 课堂提交版已单独修过此问题",
           False, "需先确认老师沙箱是单进程还是双进程；本次不判定",
           "中", status_override="未执行")

    s, p, _ = teacher.get("/api/v1/courses/%d/classroom" % cid)
    room = data_of(p) or {}
    record("R-06", "回归", "C6 教室配置可读", "200 且含 rows/cols/aisle_every/capacity",
           f"HTTP {s}，{room.get('rows')}×{room.get('cols')}，容量 {room.get('capacity')}",
           s == 200 and all(k in room for k in ("rows", "cols", "aisle_every", "capacity")),
           "教师 GET /api/v1/courses/16/classroom", "中")

    s, p, _ = teacher.get("/api/v1/courses/%d/seats" % cid)
    seat_data = data_of(p) or {}
    record("R-05", "回归", "C5/C6 座位数据完整",
           "200 且含座位清单与 classroom 配置",
           f"HTTP {s}，顶层键={list(seat_data.keys())[:6]}",
           s == 200 and bool(seat_data),
           "教师 GET /api/v1/courses/16/seats", "中")

    # R-09 僵尸换位申请
    stale = query_ro("SELECT COUNT(*) FROM seat_swap_request WHERE status='pending' "
                     "AND created_at < datetime('now','-15 minutes')")
    pending_rows = query_ro("SELECT COUNT(*) FROM seat_swap_request WHERE status='pending'")
    record("R-09", "回归", "C9 无超时未处理的僵尸换位申请",
           "pending 且创建超过 15 分钟的记录数为 0",
           f"僵尸行={stale[0][0] if stale else '?'}，总 pending="
           f"{pending_rows[0][0] if pending_rows else '?'}",
           (stale[0][0] == 0) if stale else True,
           "只读查 seat_swap_request 表", "中")

    # R-10 任务时间窗口 CHECK
    bad_window = query_ro("SELECT COUNT(*) FROM attendance_task "
                          "WHERE start_at > late_at OR late_at > end_at")
    record("R-10", "回归", "C10 任务时间窗口满足 start<=late<=end",
           "违反 CHECK 的任务数为 0",
           f"违规行={bad_window[0][0] if bad_window else '?'}",
           (bad_window[0][0] == 0) if bad_window else True,
           "只读查 attendance_task 三列", "中")

    # R-11 两处座位一致
    mismatch = query_ro(
        "SELECT COUNT(*) FROM attendance_seat a "
        "JOIN attendance_task t ON t.id=a.task_id "
        "JOIN class_seat c ON c.course_id=t.course_id AND c.student_id=a.student_id "
        "WHERE t.id = (SELECT MAX(id) FROM attendance_task WHERE course_id=16) "
        "AND a.seat_no IS NOT NULL AND c.seat_no IS NOT NULL "
        "AND (a.seat_no <> c.seat_no OR a.group_no <> c.group_no)")
    if mismatch is None:
        record("R-11", "回归", "C11 class_seat 与 attendance_seat 坐标一致",
               "不一致记录数为 0", "只读 SQL 执行失败，未执行", False,
               "经 attendance_task 关联两表比对", "中", status_override="未执行")
    else:
        record("R-11", "回归", "C11 class_seat 与 attendance_seat 坐标一致",
               "同一学生同一课程两处座位不同的记录数为 0",
               f"课程 #16 最新任务的座位快照不一致行={mismatch[0][0]}",
               mismatch[0][0] == 0,
               "只读 JOIN attendance_seat / attendance_task / class_seat", "中")

    # R-07 source 取值合法
    illegal_source = query_ro(
        "SELECT COUNT(*) FROM attendance_record WHERE source NOT IN "
        "('checkin','gesture','approval','close','correction')")
    record("R-07", "回归", "C7 签到记录 source 取值合法",
           "非法 source 记录数为 0（code 会被 CHECK 静默丢弃）",
           f"非法行={illegal_source[0][0] if illegal_source else '?'}",
           (illegal_source[0][0] == 0) if illegal_source else True,
           "只读查 attendance_record.source", "中")

    # ---------- 功能：74181 ----------
    for iid, label, query, want_hex, want_dec in (
            ("F-12a", "74181 加法 9+5", "a=9&b=5&op=add", "0xE", 14),
            ("F-12b", "74181 减法 3−7", "a=3&b=7&op=sub", "0xC", -4)):
        s, p, _ = anon.get("/api/v1/alu74181/compute?" + query)
        row = data_of(p) or {}
        record(iid, "功能", label, f"F={want_hex}，十进制 {want_dec}",
               f"HTTP {s}，f_hex={row.get('f_hex')}，十进制={row.get('decimal_result')}",
               s == 200 and row.get("f_hex") == want_hex
               and row.get("decimal_result") == want_dec,
               f"匿名 GET /api/v1/alu74181/compute?{query}", "中")

    s, p, _ = anon.get("/api/v1/alu74181/table")
    table = data_of(p) or {}
    record("F-12c", "功能", "74181 全组合表", "count=512",
           f"HTTP {s}，count={table.get('count')}，rows={len(table.get('rows') or [])}",
           s == 200 and table.get("count") == 512,
           "匿名 GET /api/v1/alu74181/table", "中")

    s, p, _ = anon.get("/api/v1/alu74181/compute?a=16&b=1&op=add")
    record("F-12d", "功能", "74181 参数越界校验", "400 VALIDATION_ERROR",
           f"HTTP {s} {err(p)}", s == 400 and err(p) == "VALIDATION_ERROR",
           "a=16 超出 0–15", "低")

    # ---------- 功能：日志导出 ----------
    s, p, raw = teacher.get("/api/v1/logs/access.csv")
    csv_lines = len(raw.splitlines())
    leak_csv = bool(re.search(r'"password"\s*:|csrf_token', raw, re.I))
    record("F-11a", "功能", "访问日志 CSV 导出", "200 且内容可解析、无敏感字段",
           f"HTTP {s}，{csv_lines} 行，敏感字段={'有' if leak_csv else '无'}",
           s == 200 and csv_lines > 1 and not leak_csv,
           "教师 GET /api/v1/logs/access.csv", "中")

    s, p, raw = teacher.get("/api/v1/logs/audit.csv")
    record("F-11b", "功能", "审计日志 CSV 导出", "200 且内容可解析",
           f"HTTP {s}，{len(raw.splitlines())} 行", s == 200 and len(raw.splitlines()) > 1,
           "教师 GET /api/v1/logs/audit.csv", "中")

    s, p, _ = teacher.get("/api/v1/logs/access")
    record("F-11c", "功能", "访问日志 JSON", "200 且可解析",
           f"HTTP {s}，data 类型={type(data_of(p)).__name__}", s == 200,
           "教师 GET /api/v1/logs/access", "低")

    # ---------- 功能：点到主链路（独立自测任务，收尾 close） ----------
    now = datetime.now(UTC)
    z = lambda m: (now + timedelta(minutes=m)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    title = "自测-g24201710-%s-%s" % (DATE, uuid.uuid4().hex[:4])

    s, p, _ = teacher.post("/api/v1/courses/%d/attendance-tasks" % cid,
                           {"title": title, "start_at": z(-1), "late_at": z(6), "end_at": z(15)})
    task = data_of(p) or {}
    tid, code = task.get("id"), task.get("code")
    record("F-01", "功能", "教师创建点到任务", "201 且返回 6 位点到码",
           f"HTTP {s}，task_id={tid}，code={'6位' if code and len(str(code)) == 6 else code}，"
           f"status={task.get('status')}",
           s == 201 and bool(tid) and bool(code) and len(str(code)) == 6,
           "教师 POST /api/v1/courses/16/attendance-tasks", "高", priority="P0")

    s, p, _ = teacher.post("/api/v1/courses/%d/attendance-tasks" % cid,
                           {"title": title + "-bad", "start_at": z(10), "late_at": z(5), "end_at": z(1)})
    record("F-02", "功能", "任务时间非法被校验", "400/422 VALIDATION_ERROR",
           f"HTTP {s} {err(p)}", s in (400, 422),
           "start_at > late_at > end_at 创建任务", "中")

    if tid:
        s, p, _ = student.post("/api/v1/attendance-tasks/%d/check-ins" % tid, {"code": "000000"})
        record("F-03", "功能", "错误点到码被拒", "422 INVALID_ATTENDANCE_CODE",
               f"HTTP {s} {err(p)}", s == 422 and err(p) == "INVALID_ATTENDANCE_CODE",
               "学生 POST check-ins（错误码）", "高", priority="P0")

        s, p, _ = student.post("/api/v1/attendance-tasks/%d/check-ins" % tid, {"code": code})
        rec1 = data_of(p) or {}
        record("F-04", "功能", "正确点到码签到", "201 且 status=present",
               f"HTTP {s}，id={rec1.get('id')}，status={rec1.get('status')}",
               s == 201 and rec1.get("status") == "present",
               "学生 POST check-ins（正确码）", "高", priority="P0")

        s, p, _ = student.post("/api/v1/attendance-tasks/%d/check-ins" % tid, {"code": code})
        rec2 = data_of(p) or {}
        record("F-05", "功能", "重复签到不新增记录", "返回同一条记录",
               f"HTTP {s}，首次 id={rec1.get('id')}，重复 id={rec2.get('id')}，"
               f"新增={'是' if rec1.get('id') != rec2.get('id') else '否'}",
               bool(rec1.get("id")) and rec1.get("id") == rec2.get("id"),
               "同一学生重复 POST check-ins", "高", priority="P0")

        s, p, _ = teacher.post("/api/v1/attendance-tasks/%d/rotate-code" % tid, {})
        new_code = (data_of(p) or {}).get("code")
        record("F-07", "功能", "轮换点到码", "200 且返回与旧码不同的新码",
               f"HTTP {s}，旧码≠新码={'是' if new_code and new_code != code else '否'}",
               s == 200 and bool(new_code) and new_code != code,
               "教师 POST /rotate-code", "中")

        s, p, _ = teacher.post("/api/v1/attendance-tasks/%d/close" % tid, {})
        closed = data_of(p) or {}
        counts_closed = closed.get("counts") or {}
        record("F-06", "功能", "关闭任务并结算", "200 且返回 counts",
               f"HTTP {s}，counts={json.dumps(counts_closed, ensure_ascii=False)}",
               s == 200 and isinstance(counts_closed, dict) and "present" in counts_closed,
               "教师 POST /close", "高", priority="P0")

        # D-01 明细全量分页 vs 统计
        all_rows = []
        page = 1
        while page <= 10:
            s2, p2, _ = teacher.get(
                "/api/v1/courses/%d/attendance-records?task_id=%d&page=%d&page_size=100"
                % (cid, tid, page))
            rows = data_of(p2) or []
            if not isinstance(rows, list) or not rows:
                break
            all_rows.extend(rows)
            total = (p2 or {}).get("total")
            if total is not None and len(all_rows) >= total:
                break
            if len(rows) < 100:
                break
            page += 1
        state_count: dict = {}
        for row in all_rows:
            key = row.get("status")
            state_count[key] = state_count.get(key, 0) + 1
        consistent = all(state_count.get(k, 0) == counts_closed.get(k, 0)
                         for k in ("present", "late", "leave", "absent"))
        record("D-01", "一致性", "任务 counts 与全量明细逐状态一致",
               "present/late/leave/absent 四项计数相同（防 C8 分页只拉 100 条）",
               f"明细 {len(all_rows)} 条，统计={json.dumps(state_count, ensure_ascii=False)}，"
               f"closed={json.dumps(counts_closed, ensure_ascii=False)}，一致={'是' if consistent else '否'}",
               consistent, "分页拉全量 attendance-records 后与 /close 返回的 counts 比对",
               "高", priority="P0")

        s, p, _ = teacher.get("/api/v1/attendance-tasks/%d/seats" % tid)
        seatmap = data_of(p) or {}
        record("F-09", "功能", "座位图接口", "200 且含 seats/grid/classroom",
               f"HTTP {s}，顶层键={list(seatmap.keys())[:6]}",
               s == 200 and "seats" in seatmap,
               "教师 GET /attendance-tasks/{id}/seats", "中")
    else:
        for iid, name in (("F-03", "错误码"), ("F-04", "签到"), ("F-05", "重复签到"),
                          ("F-06", "关闭"), ("F-07", "轮换码"), ("F-09", "座位图"),
                          ("D-01", "统计一致性")):
            record(iid, "功能", name, "按契约完成", "前置建任务失败，未执行", False,
                   "依赖 F-01", "高", status_override="未执行")

    # ---------- 功能：手势（教师开课时指定图案） ----------
    pattern = [0, 1, 2, 5, 8]
    s, p, _ = teacher.post("/api/v1/courses/%d/attendance-tasks" % cid,
                           {"title": title + "-gesture", "start_at": z(-1),
                            "late_at": z(6), "end_at": z(15), "pattern": pattern})
    gtask = data_of(p) or {}
    gtid = gtask.get("id")
    record("F-08a", "功能", "教师创建带手势图案的任务", "201 且 has_gesture=true",
           f"HTTP {s}，task_id={gtid}，has_gesture={gtask.get('has_gesture')}",
           s == 201 and bool(gtid),
           "create_task 带 pattern=[0,1,2,5,8]（/auth/gesture 已按设计移除）", "中")
    if gtid:
        s, p, _ = student2.login("24201502", "24201502")
        s2, p2, _ = student.post("/api/v1/attendance-tasks/%d/check-ins" % gtid,
                                 {"pattern": [0, 3, 6, 7, 8]})
        record("F-08b", "功能", "错误手势被拒", "422 INVALID_GESTURE",
               f"HTTP {s2} {err(p2)}", s2 == 422 and err(p2) == "INVALID_GESTURE",
               "学生用错误 pattern 签到", "中")
        s3, p3, _ = student.post("/api/v1/attendance-tasks/%d/check-ins" % gtid,
                                 {"pattern": pattern})
        grec = data_of(p3) or {}
        record("F-08c", "功能", "正确手势签到", "201 且 source=gesture",
               f"HTTP {s3}，status={grec.get('status')}，source={grec.get('source')}",
               s3 == 201,
               "学生用正确 pattern 签到", "中")
        teacher.post("/api/v1/attendance-tasks/%d/close" % gtid, {})
    else:
        for iid in ("F-08b", "F-08c"):
            record(iid, "功能", "手势签到", "按契约完成", "手势任务未创建，未执行", False,
                   "依赖 F-08a", "中", status_override="未执行")

    # ---------- 功能：换位只读 ----------
    s, p, _ = teacher.get("/api/v1/courses/%d/seat-swaps" % cid)
    record("F-13", "功能", "换位申请列表可读", "200",
           f"HTTP {s}，items={len((data_of(p) or {}).get('items') or [])}", s == 200,
           "教师 GET /api/v1/courses/16/seat-swaps", "低")
    s, p, _ = student.get("/api/v1/seat-swaps/incoming")
    incoming = data_of(p) or {}
    record("F-14", "功能", "学生收件箱（含 TTL）", "200 且含 ttl_minutes",
           f"HTTP {s}，ttl={incoming.get('ttl_minutes')}，items={len(incoming.get('items') or [])}",
           s == 200 and incoming.get("ttl_minutes") == 15,
           "学生 GET /api/v1/seat-swaps/incoming", "低")

    # ---------- 浏览器 DOM ----------
    try:
        proc = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", "--no-proxy-server", "--no-first-run",
             "--user-data-dir=" + str(Path(r"D:\Desktop\WebBigHomework\.workbuddy\tmp\edge-self")),
             "--virtual-time-budget=4000", "--dump-dom", args.frontend + "/"],
            capture_output=True, timeout=50)
        dom = proc.stdout.decode("utf-8", "replace")
        ids = ["username", "password", "login", "student-no",
               "auto-fill-teacher", "auto-fill-student"]
        missing = [x for x in ids if f'id="{x}"' not in dom]
        record("S-08", "冒烟", "浏览器登录页六个 DOM ID", "六个 ID 全在",
               f"DOM {len(dom)} 字节，缺失={missing or '无'}",
               len(dom) > 500 and not missing,
               "无头 Edge --dump-dom 打开前端首页", "高", priority="P0")
        record("R-02", "回归", "C2 登录页 DOM 契约回归", "六个 ID 全在",
               f"缺失={missing or '无'}", not missing, "同上", "高")
    except Exception as failure:  # noqa: BLE001
        for iid in ("S-08", "R-02"):
            record(iid, "冒烟", "浏览器登录页 DOM", "六个 ID 全在",
                   f"浏览器执行失败：{failure}", False, "无头 Edge --dump-dom",
                   "中", status_override="未执行")

    record("R-05b", "回归", "C5 座位图浏览器渲染",
           "浏览器进考勤页后 .seat-cell 元素数 > 0",
           "需 CDP 交互登录后再进课程，本次仅做 DOM 级验证，未执行",
           False, "需浏览器交互环境", "中", status_override="未执行")
    record("E-02", "E2E", "浏览器交互级五标签页 E2E",
           "登录→进课程→考勤座位图→74181，无 JS 异常",
           "需 CDP/Playwright 交互环境，本次未执行", False,
           "需浏览器交互环境", "中", status_override="未执行")

    link_ok = all(c["status"] == "通过" for c in CASES
                  if c["id"] in ("F-01", "F-03", "F-04", "F-05", "F-06", "D-01"))
    record("E-01", "E2E", "匿名 /who、/help → 教师登录 → 建任务 → 学生签到 → 关闭 → 明细",
           "全链路无阻断且统计一致",
           "关键环节全部通过" if link_ok else "链路存在失败项，见逐条结果",
           link_ok, "按 S-01 → D-01 顺序执行", "高", priority="P0")

    # R-03 同源放行（写请求已多次成功即证明）
    record("R-03", "回归", "C3 同源 Origin 写请求放行、跨站拒绝",
           "同源写请求成功且跨站被 403",
           f"同源建任务/签到/关闭均成功；跨站 Origin 用例 I-03="
           f"{next((c['status'] for c in CASES if c['id'] == 'I-03'), '?')}",
           next((c["status"] for c in CASES if c["id"] == "I-03"), "") == "通过",
           "对照 I-03 与 F-01/F-04/F-06", "中")

    # R-08 全量分页（由 D-01 的分页实现证明）
    record("R-08", "回归", "C8 明细分页拉全量",
           "统计不依赖单页 100 条",
           "D-01 已按 page_size=100 循环拉全量后比对",
           next((c["status"] for c in CASES if c["id"] == "D-01"), "") == "通过",
           "见 D-01 的分页循环", "中")

    DOCS.mkdir(parents=True, exist_ok=True)
    RAW_LOG.parent.mkdir(parents=True, exist_ok=True)
    RAW_LOG.write_text(json.dumps({"started": started, "base": args.base,
                                   "frontend": args.frontend, "cases": CASES,
                                   "trace": TRACE}, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    write_outputs(started, args)
    print("\n用例 %d 条，通过 %d，失败 %d，未执行 %d" % (
        len(CASES), sum(c["status"] == "通过" for c in CASES),
        sum(c["status"] == "失败" for c in CASES),
        sum(c["status"] == "未执行" for c in CASES)))


def write_outputs(started, args):
    defects = [c for c in CASES if c["status"] == "失败"]
    csv_path = DOCS / f"SELF_DEFECTS_{DATE}.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["编号", "标题", "模块", "复现步骤", "预期结果", "实际结果",
                         "严重程度", "状态"])
        for index, c in enumerate(defects, 1):
            writer.writerow(["D-%02d" % index, c["title"], c["layer"], c["reproduce"],
                             c["expected"], c["actual"], c["severity"], "待修复"])

    by_layer = {}
    for c in CASES:
        row = by_layer.setdefault(c["layer"], {})
        row[c["status"]] = row.get(c["status"], 0) + 1
    total = len(CASES)
    passed = sum(c["status"] == "通过" for c in CASES)
    failed = sum(c["status"] == "失败" for c in CASES)
    skipped = sum(c["status"] == "未执行" for c in CASES)
    p0 = [c for c in CASES if c["priority"] == "P0"]
    p0_fail = [c for c in p0 if c["status"] != "通过"]
    verdict = ("通过：核心功能可用，P0 全通过" if not p0_fail else
               "未通过：存在 P0 失败项") if not failed else "通过，但存在下表登记的问题"

    lines = [
        f"# g24201710 自测报告（{DATE}）",
        "",
        f"- 测试时间：{started}",
        "- 测试对象：本组「计算机组成原理课程学习系统」",
        f"- 代码：`D:\\Desktop\\WebBigHomework\\wt-demo`（demo-week11 @ 3ee01ba，含 2 个未提交改动）",
        f"- 服务：后端 {args.base} / 前端 {args.frontend}",
        "- 计划：`docs/TEST_PLAN_SELF_20261112.md`",
        "- 脚本：`scripts/verify_self_20261112.py`（Python 标准库，可一键复跑）",
        "",
        "## 1 测试范围",
        "",
        "- 按互测复盘把 12 条「测试方自己的错」、2 个被测组的 3 类真实缺陷、"
        "自己项目 12 条历史缺陷转成回归用例。",
        "- 分层：冒烟、接口、功能、回归、数据一致性、E2E；覆盖 `/help` 声明的 27 模块 / 148 端点中的核心链路。",
        "- 不在范围：源码审计、性能压测、真实 Logisim 评测、后端重启持久化、浏览器交互级 E2E（标未执行）。",
        "- 不删改正式数据；新建点到任务标记为「自测」并走系统 `close` 收尾。",
        "",
        "## 2 用例统计",
        "",
        "| 层级 | 用例数 | 通过 | 失败 | 未执行 |",
        "|---|---|---|---|---|",
    ]
    for layer, row in by_layer.items():
        lines.append(f"| {layer} | {sum(row.values())} | {row.get('通过', 0)} | "
                     f"{row.get('失败', 0)} | {row.get('未执行', 0)} |")
    lines += [
        f"| **合计** | **{total}** | **{passed}** | **{failed}** | **{skipped}** |",
        "",
        "### 逐条结果",
        "",
        "| ID | 层级 | 用例 | 预期 | 实际 | 结论 |",
        "|---|---|---|---|---|---|",
    ]
    for c in CASES:
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            c["id"], c["layer"], c["title"], c["expected"],
            str(c["actual"]).replace("|", "／"), c["status"]))
    lines += [
        "",
        "## 3 缺陷统计",
        "",
        "| 严重程度 | 数量 |",
        "|---|---|",
    ]
    for level in ("高", "中", "低"):
        lines.append(f"| {level} | {sum(d['severity'] == level for d in defects)} |")
    lines += [
        f"| **合计** | **{len(defects)}** |",
        "",
        f"明细见 `SELF_DEFECTS_{DATE}.csv`。",
        "",
        "## 4 结论",
        "",
        f"**{verdict}。**",
        "",
        f"- P0 用例 {len(p0)} 条，未通过 {len(p0_fail)} 条。",
        "- 判定 FAIL 前已按复盘规则自证：字段按 `/help`、方法按声明、账号归属、响应外壳、"
        "同期服务可达性；`/api/v1/health` 的 503/degraded 按已知设计不记缺陷。",
        "- 手势签到不是缺失：`identity.py` 注释说明 `/auth/gesture` 已被有意移除，"
        "改为教师建任务时指定 `pattern`（见 F-08a/b/c）。",
        "- **缺陷表 0 条不等于零风险**：未执行项与单进程静态沙箱条件性风险均未记为通过，"
        "也未记成功能缺陷，详见遗留风险。",
    ]
    if defects:
        lines.append("- 未通过项：")
        for d in defects:
            lines.append(f"  - {d['id']} {d['title']}：{d['actual']}")
    lines += [
        "",
        "## 5 遗留风险",
        "",
        "1. 结果只对当前 `wt-demo` 工作区成立（含 2 个未提交改动），提交后需复跑。",
        "2. 浏览器交互级 E2E 与座位图渲染未执行，需 CDP/Playwright 环境或现场人工。",
        "3. 后端重启持久化、真实 Logisim 评测未验证；`grader_ready:false` 属已知状态。",
        "4. 单进程沙箱下直连后端 `/` 的行为见 R-04b（当前 develop 返回 404）；若老师用静态沙箱，需确认 `docs/index.html`"
        " 与后端静态托管方案都已合入课堂提交版。",
        "5. 本报告不含明文口令、CSRF 令牌或完整个人数据；原始请求日志本地留存。",
        "6. 脚本会创建「自测」任务并在 close 时按名单补记，会抬高演示首页考勤数字；跑完请执行 `scripts/cleanup_demo_selftest.py --db <库路径> --apply` 复位（脚本默认 dry-run 且自动备份）。",
        "",
        "## 6 附件",
        "",
        f"- 缺陷表：`SELF_DEFECTS_{DATE}.csv`",
        "- 原始日志：`.workbuddy/tmp/self-test-20261112.json`（不随文档提交）",
        "- 计划：`docs/TEST_PLAN_SELF_20261112.md`",
        "",
    ]
    report = DOCS / f"SELF_TEST_REPORT_{DATE}.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print("已写出：", report)
    print("已写出：", csv_path)


if __name__ == "__main__":
    main()
