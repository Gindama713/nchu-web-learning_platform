"""第 10 周互测脚本骨架：批量打被测组，产出测试报告。

流程严格按《大作业互测及演示方案》：
    1. GET /who、GET /help 取被测组信息与接口说明
    2. 教师登录 → 建点到任务 → 取 6 位点到码
    3. 学生登录 → 点到（含重复点到、错误码两个异常用例）
    4. 关闭任务 → 读回统计，核对 present/late/absent
    5. 生成 Markdown 报告 + 原始 JSON 日志

用法：
    python scripts/peer_test.py --self
    python scripts/peer_test.py --target http://192.168.1.5:5173
    python scripts/peer_test.py --targets targets.txt --out docs/week10-test-report.md

只依赖标准库，不需要 pip 安装 requests。
"""

from __future__ import annotations

# ruff: noqa: UP031  — 报表行以 % 拼接更直观，无需转 f-string
import argparse
import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

GROUP = "g24201710"
TIMEOUT = 12


def now_stamp(offset_minutes=0):
    moment = datetime.now(UTC) + timedelta(minutes=offset_minutes)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ApiResult:
    def __init__(self, status, body, elapsed):
        self.status = status
        self.body = body
        self.elapsed = elapsed
        self.data = None
        self.error = None
        if isinstance(body, dict):
            self.data = body.get("data")
            self.error = body.get("error")

    @property
    def ok(self):
        return 200 <= self.status < 300

    def describe(self):
        if self.ok:
            return "HTTP %d" % self.status
        if self.error:
            return "HTTP %d %s" % (self.status, self.error.get("code", ""))
        return "HTTP %d" % self.status


class Peer:
    """一个被测组的会话：自带 cookie，写请求带 Origin 与 X-CSRF-Token。"""

    def __init__(self, base, actor="教师"):
        self.base = base.rstrip("/")
        self.actor = actor
        self.jar = http.cookiejar.CookieJar()
        # 被测组通常是局域网地址，必须绕开系统/环境代理，否则会打到代理上
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar), urllib.request.ProxyHandler({}))
        self.csrf = None
        self.trace = []

    def request(self, method, path, payload=None):
        url = self.base + path
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        request.add_header("Origin", self.base)
        if self.csrf and method != "GET":
            request.add_header("X-CSRF-Token", self.csrf)

        started = time.perf_counter()
        status, body = 0, None
        try:
            with self.opener.open(request, timeout=TIMEOUT) as response:
                status = response.status
                raw = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as failure:
            status = failure.code
            raw = failure.read().decode("utf-8", "replace")
        except Exception as failure:  # noqa: BLE001 — 连不上、超时、DNS 都要收成一条测试记录
            raw = json.dumps({"transport": str(failure)}, ensure_ascii=False)
        elapsed = (time.perf_counter() - started) * 1000

        try:
            body = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            body = {"raw": raw[:400]}

        result = ApiResult(status, body, elapsed)
        self.trace.append({"at": now_stamp(), "actor": self.actor, "method": method, "path": path,
                           "status": status, "ms": round(elapsed, 1),
                           "error": (result.error or {}).get("code") if result.error else None})
        return result

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, payload):
        return self.request("POST", path, payload)

    def login(self, number, password):
        result = self.post("/api/v1/auth/login", {"student_no": number, "password": password})
        if result.ok and isinstance(result.data, dict):
            self.csrf = result.data.get("csrf_token")
        return result


def run_scenario(base, teacher, student, want_checkin=True):
    """对一个被测组跑完整流程，返回结构化结果。"""
    peer = Peer(base)
    steps = {}

    who = peer.get("/who")
    steps["who"] = {"result": who, "detail": who.data}

    help_page = peer.get("/help")
    modules = help_page.data.get("modules") if isinstance(help_page.data, dict) else None
    steps["help"] = {"result": help_page,
                     "detail": {"modules": len(modules or []),
                                "endpoints": help_page.data.get("counts", {}).get("endpoints")
                                if isinstance(help_page.data, dict) else None}}

    teacher_no, teacher_pw = teacher
    login = peer.login(teacher_no, teacher_pw)
    steps["teacher_login"] = {"result": login,
                              "detail": (login.data or {}).get("user") if login.data else None}
    if not login.ok:
        return {"base": base, "steps": steps, "trace": peer.trace, "verdict": "教师登录失败"}

    courses = peer.get("/api/v1/courses")
    rows = courses.data if isinstance(courses.data, list) else []
    steps["courses"] = {"result": courses,
                        "detail": [{"id": row.get("id"), "title": row.get("title")} for row in rows]}
    if not rows:
        return {"base": base, "steps": steps, "trace": peer.trace, "verdict": "教师没有可见课程"}
    course_id = rows[0]["id"]

    created = peer.post("/api/v1/courses/%d/attendance-tasks" % course_id, {
        "title": "第10周互测点到",
        "start_at": now_stamp(-1),
        "late_at": now_stamp(5),
        "end_at": now_stamp(10),
    })
    task = created.data or {}
    steps["create_task"] = {"result": created,
                            "detail": {"task_id": task.get("id"), "code": task.get("code"),
                                       "status": task.get("status")}}
    if not created.ok or not task.get("code"):
        return {"base": base, "steps": steps, "trace": peer.trace, "verdict": "建点到任务失败"}

    task_id, code = task["id"], task["code"]

    if want_checkin:
        student_no, student_pw = student
        learner = Peer(base, actor="学生")
        student_login = learner.login(student_no, student_pw)
        steps["student_login"] = {"result": student_login,
                                  "detail": (student_login.data or {}).get("user") if student_login.data else None}

        if student_login.ok:
            # 顺序很重要：先试错误码（此时还没有记录，必须 422），再正常签到，最后重复签。
            # 若先签到，服务端会走"已有记录直接返回"的分支，错误码用例就测不出来了。
            bad = learner.post("/api/v1/attendance-tasks/%d/check-ins" % task_id, {"code": "000000"})
            steps["checkin_bad_code"] = {"result": bad,
                                         "detail": {"期望": "422 INVALID_ATTENDANCE_CODE",
                                                    "实际": (bad.error or {}).get("code")}}

            first = learner.post("/api/v1/attendance-tasks/%d/check-ins" % task_id, {"code": code})
            steps["checkin"] = {"result": first, "detail": first.data}

            again = learner.post("/api/v1/attendance-tasks/%d/check-ins" % task_id, {"code": code})
            first_id = (first.data or {}).get("id")
            again_id = (again.data or {}).get("id")
            steps["checkin_repeat"] = {"result": again,
                                       "detail": {"期望": "不新增记录，返回同一条记录",
                                                  "实际": {"首次记录": first_id, "重复记录": again_id,
                                                           "是否新增": first_id != again_id}}}
            peer.trace.extend(learner.trace)
        else:
            steps["checkin"] = {"result": student_login, "detail": {"跳过": "学生账号不可用"}}

    closed = peer.post("/api/v1/attendance-tasks/%d/close" % task_id, {})
    steps["close_task"] = {"result": closed,
                           "detail": {"counts": (closed.data or {}).get("counts") if closed.data else None}}

    records = peer.get("/api/v1/courses/%d/attendance-records?task_id=%d&page_size=100"
                       % (course_id, task_id))
    steps["records"] = {"result": records,
                        "detail": {"total": records.body.get("total") if isinstance(records.body, dict) else None}}

    problems = []
    if not who.ok:
        problems.append("/who 不可用")
    if not help_page.ok:
        problems.append("/help 不可用")
    if not created.ok:
        problems.append("建任务失败")
    if not closed.ok:
        problems.append("关闭任务失败")
    if want_checkin and "checkin" in steps and not steps["checkin"]["result"].ok:
        problems.append("学生签到失败")
    bad_code = steps.get("checkin_bad_code", {}).get("result")
    if want_checkin and bad_code is not None and bad_code.status not in (422,):
        problems.append("错误点到码未按 422 拒绝")

    return {"base": base, "steps": steps, "trace": peer.trace,
            "verdict": "通过" if not problems else "；".join(problems)}


def verdict_cell(scenario, key):
    step = scenario["steps"].get(key)
    if not step:
        return "—"
    return step["result"].describe()


def to_markdown(scenarios, started):
    lines = [
        "# 第10周 大作业互测报告",
        "",
        f"- 测试方：{GROUP}（计算机组成原理组）",
        f"- 测试时间：{started}",
        "- 被测组数量：%d" % len(scenarios),
        "",
        "## 1 汇总",
        "",
        "| # | 被测组 | /who | /help | 教师登录 | 建点到 | 学生签到 | 关闭统计 | 结论 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for index, item in enumerate(scenarios, 1):
        counts = item["steps"].get("close_task", {}).get("detail", {}).get("counts") or {}
        stat = "/".join("{}={}".format(key, counts.get(key, "?"))
                        for key in ("present", "late", "leave", "absent")) if counts else "—"
        lines.append("| %d | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            index, item["base"],
            verdict_cell(item, "who"), verdict_cell(item, "help"),
            verdict_cell(item, "teacher_login"), verdict_cell(item, "create_task"),
            verdict_cell(item, "checkin"), stat, item["verdict"]))
    lines.append("")

    lines.append("## 2 明细")
    for index, item in enumerate(scenarios, 1):
        lines.append("")
        lines.append("### 2.%d %s" % (index, item["base"]))
        lines.append("")
        who = item["steps"].get("who", {}).get("detail")
        if isinstance(who, dict):
            lines.append("- 小组信息：{} {}，组长 {}，成员 {} 人".format(
                who.get("class_name", "?"), who.get("group_no", "?"),
                (who.get("leader") or {}).get("name", "?"), who.get("member_count", "?")))
        else:
            lines.append("- 小组信息：无法解析 /who 响应")
        help_detail = item["steps"].get("help", {}).get("detail") or {}
        lines.append("- 接口清单：{} 个模块，{} 条接口".format(
            help_detail.get("modules", "?"), help_detail.get("endpoints", "?")))
        task = item["steps"].get("create_task", {}).get("detail") or {}
        if task.get("task_id"):
            lines.append("- 点到任务：#{}，码 {}，状态 {}".format(
                task.get("task_id"), task.get("code"), task.get("status")))
        repeat = item["steps"].get("checkin_repeat", {}).get("detail")
        if repeat:
            lines.append("- 重复点到：{}".format(json.dumps(repeat.get("实际"), ensure_ascii=False)))
        bad = item["steps"].get("checkin_bad_code", {}).get("detail")
        if bad:
            lines.append("- 错误码：期望 {}，实际 {}".format(bad.get("期望"), bad.get("实际")))
        lines.append("")
        lines.append("访问过程：")
        lines.append("")
        lines.append("| 时间 | 账号 | 方法 | 路径 | 状态 | 耗时(ms) |")
        lines.append("|---|---|---|---|---|---|")
        for row in sorted(item["trace"], key=lambda entry: entry["at"]):
            lines.append("| {} | {} | {} | {} | {} | {} |".format(
                row["at"], row.get("actor", "—"), row["method"], row["path"],
                row["status"], row["ms"]))
    lines.append("")
    lines.append("## 3 结论")
    lines.append("")
    passed = [item for item in scenarios if item["verdict"] == "通过"]
    lines.append("- 通过 %d / %d 组。" % (len(passed), len(scenarios)))
    failed = [item for item in scenarios if item["verdict"] != "通过"]
    for item in failed:
        lines.append("- {}：{}".format(item["base"], item["verdict"]))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="第10周互测脚本骨架")
    parser.add_argument("--target", action="append", default=[], help="被测组地址，可重复")
    parser.add_argument("--targets", help="每行一个被测组地址的文件")
    parser.add_argument("--self", action="store_true", help="测本机 http://127.0.0.1:5173")
    parser.add_argument("--teacher", default="teacher:teacher", help="教师账号，默认 teacher:teacher")
    parser.add_argument("--student", default="", help="学生账号，格式 学号:密码；不填则跳过签到用例")
    parser.add_argument("--out", default="docs/week10-test-report.md", help="报告输出路径")
    parser.add_argument("--json", default="", help="原始 JSON 日志输出路径，默认与报告同名")
    args = parser.parse_args(argv)

    targets = list(args.target)
    if args.targets:
        targets += [line.strip() for line in Path(args.targets).read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.startswith("#")]
    if args.self:
        targets.append("http://127.0.0.1:5173")
    if not targets:
        parser.error("至少给一个 --target、--targets 或 --self")

    teacher = tuple(args.teacher.split(":", 1))
    student = tuple(args.student.split(":", 1)) if args.student else ("", "")
    started = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    scenarios = []
    for base in targets:
        print(f"→ 正在测试 {base}", flush=True)
        scenarios.append(run_scenario(base, teacher, student, want_checkin=bool(args.student)))

    report = to_markdown(scenarios, started)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")

    raw = Path(args.json) if args.json else out.with_suffix(".json")
    raw.write_text(json.dumps({"group": GROUP, "started": started,
                               "scenarios": [
                                   {"base": item["base"], "verdict": item["verdict"],
                                    "trace": item["trace"],
                                    "steps": {name: {"status": step["result"].status,
                                                     "detail": step["detail"]}
                                              for name, step in item["steps"].items()
                                              if not name.startswith("_")}}
                                   for item in scenarios]},
                              ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"报告已写入 {out}")
    print(f"原始日志已写入 {raw}")
    for item in scenarios:
        print("  {} -> {}".format(item["base"], item["verdict"]))
    return 0 if all(item["verdict"] == "通过" for item in scenarios) else 1


if __name__ == "__main__":
    sys.exit(main())
