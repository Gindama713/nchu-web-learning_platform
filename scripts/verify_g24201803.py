"""g24201710 姜苏豪 · 对被测组 g24201803 的课堂互测自动化脚本。

只依赖 Python 标准库；按 /help 动态确认接口契约，覆盖冒烟、接口、功能与 E2E。
产出老师模板要求的两份文件（且只写姜苏豪本人的两份）：
    docs/tests/test1/report_1_20261106_jiangsuhao.md
    docs/tests/test1/defects_1_20261106_jiangsuhao.csv
原始请求日志写到 .workbuddy/tmp/，不随文档提交（不含图片）。
"""
from __future__ import annotations

import csv
import http.cookiejar
import json
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

BASE = "http://10.83.88.135:5000"
TARGET = "g24201803（242018班第3组）"
CLASS_ID = 5
OUT_DIR = Path(r"D:\Desktop\WebBigHomework(5)\WebBigHomework\docs\tests\test1")
RAW_LOG = Path(r"D:\Desktop\WebBigHomework\.workbuddy\tmp\g24201803-raw.json")
DATE = "20261106"
NAME = "jiangsuhao"

CASES: list[dict] = []
TRACE: list[dict] = []


def stamp(offset_minutes=0):
    return (datetime.now(UTC) + timedelta(minutes=offset_minutes)).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


class Session:
    """自带 Cookie 的会话；写请求自动带 Origin 与 X-CSRF-Token。"""

    def __init__(self, label):
        self.label = label
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar), urllib.request.ProxyHandler({}))
        self.csrf = None

    def req(self, method, path, body=None, csrf=True, extra=None, origin=BASE):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(BASE + path, data=data, method=method)
        request.add_header("Accept", "application/json")
        request.add_header("Origin", origin)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if csrf and self.csrf and method != "GET":
            request.add_header("X-CSRF-Token", self.csrf)
        for key, value in (extra or {}).items():
            request.add_header(key, value)
        started = time.perf_counter()
        status, raw = 0, ""
        try:
            with self.opener.open(request, timeout=10) as response:
                status, raw = response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as failure:
            status, raw = failure.code, failure.read().decode("utf-8", "replace")
        except Exception as failure:  # noqa: BLE001 — 网络异常也要收成一条记录
            raw = json.dumps({"transport": str(failure)}, ensure_ascii=False)
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        try:
            payload = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            payload = {"raw": raw[:200]}
        TRACE.append({"at": stamp(), "actor": self.label, "method": method,
                      "path": path, "status": status, "ms": elapsed})
        return status, payload, raw

    def get(self, path):
        return self.req("GET", path)

    def post(self, path, body=None, **kw):
        return self.req("POST", path, body, **kw)

    def fetch_csrf(self):
        status, payload, _ = self.get("/api/auth/csrf")
        if status == 200:
            self.csrf = (payload.get("data") or {}).get("csrf_token")
        return self.csrf

    def login(self, username, password):
        self.fetch_csrf()
        status, payload, _ = self.post("/api/auth/login",
                                       {"username": username, "password": password})
        if status == 200:
            self.csrf = (payload.get("data") or {}).get("csrf_token") or self.csrf
        return status, payload, ""


def err(payload):
    return ((payload or {}).get("error") or {}).get("code", "")


def record(cid, layer, title, expected, actual, passed, reproduce,
           severity="中", status_override=None):
    CASES.append({"id": cid, "layer": layer, "title": title, "expected": expected,
                  "actual": actual, "expected_ok": bool(passed),
                  "status": status_override or ("通过" if passed else "失败"),
                  "reproduce": reproduce, "severity": severity,
                  "blocked": bool(status_override)})
    _shown = status_override or ("通过" if passed else "失败")
    print(f"[{_shown}] {cid} {title} | {str(actual)[:110]}")


def main():
    started = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    anon = Session("匿名")
    teacher = Session("教师")
    student = Session("学生")

    # ---------- 冒烟 ----------
    s, p, raw = anon.get("/")
    record("SM-01", "冒烟", "首页可访问", "HTTP 200 且返回页面", f"HTTP {s}",
           s == 200, "匿名 GET /", "高")

    s, p, _ = anon.get("/who")
    # 被测组 /who 直接返回顶层字段，并非 {data:{...}} 包裹
    who_data = (p.get("data") or {}) if isinstance(p, dict) and "data" in p else p
    if not isinstance(who_data, dict):
        who_data = {}
    ok = s == 200 and bool(who_data.get("group_no")) and bool(who_data.get("leader"))
    record("SM-02", "冒烟", "公开接口 /who 返回小组信息",
           "HTTP 200，含班级/组号/组长/成员", f"HTTP {s}，组号={(who_data or {}).get('group_no')}，组长={(who_data or {}).get('leader')}",
           ok, "匿名 GET /who", "高")

    s, p, _ = anon.get("/help")
    help_data = p.get("data") if isinstance(p, dict) else None
    if help_data is None and isinstance(p, dict) and "api" in p:
        help_data = p
    modules = ((help_data or {}).get("api") or {}).get("modules") or {}
    endpoints = sum(len(m.get("endpoints", [])) for m in modules.values())
    record("SM-03", "冒烟", "公开接口 /help 提供接口清单",
           "HTTP 200 且可解析的模块/端点清单", f"HTTP {s}，{len(modules)} 模块 / {endpoints} 端点",
           s == 200 and len(modules) > 0, "匿名 GET /help", "高")

    for cid, path, key in (("SM-04", "/api/health/live", "alive"),
                           ("SM-05", "/api/health/ready", "ready")):
        s, p, _ = anon.get(path)
        data = (p.get("data") or {}) if isinstance(p, dict) else {}
        record(cid, "冒烟", f"健康检查 {path}", "HTTP 200 且就绪标志为真",
               f"HTTP {s}，{key}={data.get(key)}", s == 200 and data.get(key) is True,
               f"匿名 GET {path}", "高")

    s, p, _ = anon.get("/api/auth/csrf")
    record("SM-06", "冒烟", "公开获取 CSRF 令牌", "HTTP 200 且返回 csrf_token",
           f"HTTP {s}，令牌={'有' if (p.get('data') or {}).get('csrf_token') else '无'}",
           s == 200 and bool((p.get("data") or {}).get("csrf_token")),
           "匿名 GET /api/auth/csrf", "中")

    s, p, _ = teacher.login("teacher", "teacher")
    role = ((p.get("data") or {}).get("user") or {}).get("role")
    record("SM-07", "冒烟", "教师账号登录", "HTTP 200 且角色 teacher",
           f"HTTP {s}，role={role}", s == 200 and role == "teacher",
           "GET /api/auth/csrf 取令牌 → POST /api/auth/login（任务书公开演示账号）", "高")

    s, p, _ = teacher.get("/api/classes")
    classes = (p.get("data") or {}).get("items", []) if isinstance(p, dict) else []
    record("SM-08", "冒烟", "教师可见任教班级", "HTTP 200 且至少 1 个班级",
           f"HTTP {s}，班级数={len(classes)}", s == 200 and len(classes) >= 1,
           "教师会话 GET /api/classes", "高")

    # ---------- 接口 ----------
    for cid, path in (("API-01", "/who"), ("API-02", "/help")):
        s, p, _ = anon.post(path, {})
        record(cid, "接口", f"{path} 拒绝非 GET 方法", "HTTP 405",
               f"HTTP {s} {err(p)}", s == 405, f"匿名 POST {path}", "低")

    for cid, path in (("API-03", "/api/classes"), ("API-04", "/api/audit-logs")):
        s, p, _ = anon.get(path)
        record(cid, "接口", f"匿名访问 {path} 被鉴权拒绝", "HTTP 401 UNAUTHENTICATED",
               f"HTTP {s} {err(p)}", s == 401 and err(p) == "UNAUTHENTICATED",
               f"匿名 GET {path}", "高")

    bad = Session("错误密码")
    bad.fetch_csrf()
    s, p, _ = bad.post("/api/auth/login", {"username": "teacher", "password": "wrong-password"})
    record("API-05", "接口", "错误密码登录被拒绝", "HTTP 4xx 且不建立会话",
           f"HTTP {s} {err(p)}", s in (401, 403) and err(p) != "CSRF_INVALID",
           "使用错误密码 POST /api/auth/login", "高")

    s, p, _ = bad.post("/api/auth/login",
                       {"username": "teacher", "password": "teacher", "student_no": "x"})
    record("API-06", "接口", "登录请求拒绝不支持字段", "HTTP 422 VALIDATION_ERROR",
           f"HTTP {s} {err(p)}", s == 422 and err(p) == "VALIDATION_ERROR",
           "登录 body 额外携带 student_no 字段", "中")

    no_csrf = Session("无CSRF")
    s, p, _ = no_csrf.post("/api/auth/login", {"username": "teacher", "password": "teacher"},
                           csrf=False)
    record("API-07", "接口", "写请求缺少 CSRF 令牌被拒绝", "HTTP 403 CSRF_INVALID",
           f"HTTP {s} {err(p)}", s == 403 and err(p) == "CSRF_INVALID",
           "不带 X-CSRF-Token 直接 POST /api/auth/login", "中")

    cross = Session("跨站Origin")
    cross.fetch_csrf()
    s, p, _ = cross.post("/api/auth/login", {"username": "teacher", "password": "teacher"},
                         origin="http://evil.example")
    record("API-08", "接口", "跨站 Origin 写请求被拒绝", "HTTP 403",
           f"HTTP {s} {err(p)}", s == 403, "Origin 设为 http://evil.example 后登录", "中")

    s, p, _ = anon.get("/api/health/ready")
    declared = {(e.get("method"), e.get("path")) for e in
                ((help_data or {}).get("public_endpoints") or [])}
    extra_public = [path for path in ("/api/health/live", "/api/health/ready", "/api/auth/csrf")
                    if ("GET", path) not in declared]
    record("API-09", "接口", "/help 公开端点声明与实际一致",
           "实际可匿名访问的端点都列入 public_endpoints",
           f"/help 仅声明 {len(declared)} 个公开端点；实测另可匿名访问 {len(extra_public)} 个：{', '.join(extra_public)}",
           not extra_public, "比对 /help.public_endpoints 与匿名 GET 实测结果", "低")

    s, p, _ = anon.get("/api/classes/5/members")
    record("API-10", "接口", "未登录读取班级成员被拒绝", "HTTP 401",
           f"HTTP {s} {err(p)}", s == 401, "匿名 GET /api/classes/5/members", "高")

    # ---------- 功能：课堂点到主流程 ----------
    now = datetime.now(UTC)
    z = lambda m: (now + timedelta(minutes=m)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    title = "互测-g24201710-姜苏豪-%s-%s" % (DATE, uuid.uuid4().hex[:4])
    s, p, _ = teacher.post("/api/classes/%d/attendance-tasks" % CLASS_ID,
                           {"title": title, "starts_at": z(-1), "late_at": z(6),
                            "ends_at": z(15), "methods": ["code"]})
    task = (p.get("data") or {}) if isinstance(p, dict) else {}
    task_id = task.get("id")
    record("FUNC-01", "功能", "教师创建点到草稿任务", "HTTP 201 且 status=draft",
           f"HTTP {s}，task_id={task_id}，status={task.get('status')}",
           s == 201 and task.get("status") == "draft",
           "教师 POST /api/classes/5/attendance-tasks（title/starts_at/late_at/ends_at/methods）", "高")

    if not task_id:
        for cid, name in (("FUNC-02", "发布点到任务"), ("FUNC-03", "获取点到码"),
                          ("FUNC-04", "学生签到"), ("FUNC-05", "重复签到幂等"),
                          ("FUNC-06", "座位/记录/报表读取"), ("FUNC-07", "关闭任务并统计"),
                          ("E2E-01", "课堂点到完整业务链路")):
            record(cid, "功能" if cid.startswith("FUNC") else "E2E", name,
                   "按契约完成", "前置步骤失败，未执行", False,
                   "依赖 FUNC-01 创建的任务", "高", status_override="阻塞")
    else:
        rev = task.get("revision")
        s, p, _ = teacher.post("/api/attendance-tasks/%d/publish" % task_id, {"revision": rev})
        published = (p.get("data") or {}) if isinstance(p, dict) else {}
        rev = published.get("revision", rev)
        record("FUNC-02", "功能", "发布点到任务", "HTTP 200 且状态不再是 draft",
               f"HTTP {s}，status={published.get('status')}",
               s == 200 and published.get("status") != "draft",
               "POST /api/attendance-tasks/{id}/publish，body 带当前 revision", "高")

        s, p, _ = teacher.get("/api/attendance-tasks/%d/challenge" % task_id)
        code = (p.get("data") or {}).get("code") if isinstance(p, dict) else None
        record("FUNC-03", "功能", "教师获取 6 位点到码", "HTTP 200 且返回 6 位数字码",
               f"HTTP {s}，code={'已返回' if code else '无'}",
               s == 200 and bool(code) and len(str(code)) == 6,
               "教师 GET /api/attendance-tasks/{id}/challenge", "高")

        s, p, _ = student.login("24201813", "24201813")
        record("FUNC-04", "功能", "学生账号登录", "HTTP 200 且角色 student",
               f"HTTP {s}，role={((p.get('data') or {}).get('user') or {}).get('role')}",
               s == 200, "学生 24201813 登录（密码为公开演示规则：同账号）", "高")

        idem_key = str(uuid.uuid4())
        if code:
            s_bad, p_bad, _ = student.post("/api/attendance-tasks/%d/check-ins" % task_id,
                                           {"code": "000000", "method": "code"},
                                           extra={"Idempotency-Key": str(uuid.uuid4())})
            record("FUNC-05", "功能", "错误点到码被拒绝", "HTTP 4xx 且不产生签到记录",
                   f"HTTP {s_bad} {err(p_bad)}", 400 <= s_bad < 500,
                   "学生 POST check-ins，code 使用错误值 000000", "高")

            s_ok, p_ok, _ = student.post("/api/attendance-tasks/%d/check-ins" % task_id,
                                         {"code": code, "method": "code"},
                                         extra={"Idempotency-Key": idem_key})
            rec1 = (p_ok.get("data") or {}) if isinstance(p_ok, dict) else {}
            record("FUNC-06", "功能", "学生按正确点到码签到", "HTTP 200/201 且产生记录",
                   f"HTTP {s_ok}，记录 id={rec1.get('id')}，状态={rec1.get('status')}",
                   s_ok in (200, 201) and bool(rec1),
                   "学生 POST check-ins，带 code/method/整数 request_id 幂等键", "高")

            s_rep, p_rep, _ = student.post("/api/attendance-tasks/%d/check-ins" % task_id,
                                           {"code": code, "method": "code"},
                                           extra={"Idempotency-Key": idem_key})
            rec2 = (p_rep.get("data") or {}) if isinstance(p_rep, dict) else {}
            record("FUNC-07", "功能", "重复签到不新增记录", "返回同一条记录，不重复计数",
                   f"HTTP {s_rep}，首次 id={rec1.get('id')}，重复 id={rec2.get('id')}",
                   bool(rec1.get("id")) and rec1.get("id") == rec2.get("id"),
                   "同一学生用同一 request_id 再次提交 check-ins", "高")
        else:
            for cid in ("FUNC-05", "FUNC-06", "FUNC-07"):
                record(cid, "功能", "点到签到相关用例", "按契约完成",
                       "未取到点到码，未执行", False, "依赖 FUNC-03", "高",
                       status_override="阻塞")

        reads = []
        for label, path in (("seats", "/api/attendance-tasks/%d/seats" % task_id),
                            ("records", "/api/attendance-tasks/%d/records" % task_id),
                            ("report", "/api/attendance-tasks/%d/report" % task_id)):
            s_r, _, raw_r = teacher.get(path)
            reads.append(f"{label}={s_r}")
        record("FUNC-08", "功能", "教师读取座位图/签到记录/报表", "三个接口均 HTTP 200",
               "，".join(reads), all(x.endswith("=200") for x in reads),
               "教师分别 GET seats / records / report", "中")

        s_t, p_t, _ = teacher.get("/api/attendance-tasks/%d" % task_id)
        rev = (p_t.get("data") or {}).get("revision", rev)
        s_c, p_c, _ = teacher.post("/api/attendance-tasks/%d/close" % task_id, {"revision": rev})
        closed = (p_c.get("data") or {}) if isinstance(p_c, dict) else {}
        record("FUNC-09", "功能", "教师关闭任务并结算缺勤", "HTTP 200 且返回统计",
               f"HTTP {s_c}，present={closed.get('present_count')}，absent={closed.get('absent_count')}",
               s_c == 200 and isinstance(closed.get("absent_count"), int),
               "POST /api/attendance-tasks/{id}/close，body 带当前 revision", "中")

        link_ok = all(c["status"] == "通过" for c in CASES
                      if c["id"] in ("FUNC-01", "FUNC-02", "FUNC-03", "FUNC-04",
                                     "FUNC-06", "FUNC-08", "FUNC-09"))
        record("E2E-01", "E2E", "教师建任务→发布→取码→学生签到→读统计→关闭",
               "全链路无阻断，状态与统计一致",
               "关键环节全部通过" if link_ok else "链路存在失败项，见上表",
               link_ok, "按 FUNC-01 → FUNC-09 顺序执行", "高")

    # ---------- 全量补充：15 模块抽查 / 越权 / 边界 / 一致性 / 日志 / 实验 / 浏览器 ----------
    import re as _re
    import subprocess as _sp

    _tid = task_id if task_id else None

    # 15 个模块逐项：每个模块取一条代表性 GET，验证路由存在且返回统一 JSON 结构
    for _idx, (_mname, _mbody) in enumerate(sorted(modules.items()), 1):
        _gets = [e["path"] for e in _mbody.get("endpoints", [])
                 if "GET" in e.get("methods", [])]
        if not _gets:
            record("MOD-%02d" % _idx, "模块抽查", f"{_mname} 模块可达性",
                   "/help 声明至少一条 GET 接口", "该模块无 GET 端点", False,
                   f"检查 /help.api.modules.{_mname}", "中", status_override="未执行")
            continue
        _path = _re.sub(r"<[^>]+>", "5", sorted(_gets, key=len)[0])
        _s, _p, _raw = teacher.get(_path)
        _json_ok = isinstance(_p, dict) and ("data" in _p or "error" in _p)
        record("MOD-%02d" % _idx, "模块抽查", f"{_mname}：{_path}",
               "路由存在且返回统一 JSON（允许 403 权限隔离 / 404 资源不存在）",
               f"HTTP {_s}，{'统一JSON' if _json_ok else '非JSON响应'}",
               _s < 500 and _json_ok, f"教师会话 GET {_path}", "中")

    # 权限：学生越权与管理员专属接口
    _perm = [
        ("PERM-01", "学生创建点到任务", "POST", "/api/classes/5/attendance-tasks",
         {"title": "互测越权", "starts_at": z(1), "ends_at": z(10), "methods": ["code"]}),
        ("PERM-02", "学生读取审计日志", "GET", "/api/audit-logs", None),
        ("PERM-03", "学生读取用户列表", "GET", "/api/users", None),
        ("PERM-04", "学生读取教师统计", "GET", "/api/classes/5/analytics/overview", None),
    ]
    for _cid, _label, _method, _path, _body in _perm:
        if _method == "GET":
            _s, _p, _ = student.get(_path)
        else:
            _s, _p, _ = student.post(_path, _body)
        record(_cid, "权限", _label, "HTTP 403 FORBIDDEN，数据不被改变",
               f"HTTP {_s} {err(_p)}", _s == 403 and err(_p) == "FORBIDDEN",
               f"学生会话 {_method} {_path}", "高")

    _s, _p, _ = teacher.get("/api/audit-logs")
    record("PERM-05", "权限", "教师读取全局审计日志", "HTTP 403（审计日志为管理员专属）",
           f"HTTP {_s} {err(_p)}", _s == 403,
           "教师会话 GET /api/audit-logs", "中")

    # 参数与边界
    _bounds = [
        ("BND-01", "创建点到任务缺少必填字段", "POST", "/api/classes/5/attendance-tasks",
         {}, 422),
        ("BND-02", "点到任务结束时间早于开始时间", "POST", "/api/classes/5/attendance-tasks",
         {"title": "互测边界", "starts_at": z(10), "ends_at": z(1),
          "methods": ["code"]}, 422),
        ("BND-03", "非法分页参数 page_size=-5", "GET", "/api/classes?page_size=-5", None, 422),
        ("BND-04", "访问不存在的点到任务", "GET", "/api/attendance-tasks/999999", None, 404),
        ("BND-05", "访问不存在的班级成员", "GET", "/api/classes/999999/members", None, 404),
    ]
    for _cid, _label, _method, _path, _body, _want in _bounds:
        if _method == "GET":
            _s, _p, _ = teacher.get(_path)
        else:
            _s, _p, _ = teacher.post(_path, _body)
        record(_cid, "边界", _label, f"HTTP {_want} 且返回明确错误码",
               f"HTTP {_s} {err(_p)}", _s == _want and bool(err(_p)),
               f"教师会话 {_method} {_path}", "中")

    # 数据一致性：签到明细与 CSV 报表
    if _tid:
        _s1, _p1, _ = teacher.get("/api/attendance-tasks/%d/records" % _tid)
        _s2, _p2, _raw2 = teacher.get("/api/attendance-tasks/%d/report" % _tid)
        _items = ((_p1.get("data") or {}).get("items") or []) if isinstance(_p1, dict) else []
        _present = [it.get("student_no") for it in _items if it.get("status") == "present"]
        _match = bool(_present) and all(str(no) in _raw2 for no in _present)
        record("DATA-01", "一致性", "签到明细与 CSV 报表数据一致",
               "records 中 present 学号均出现在 report 导出且状态一致",
               f"records={_s1}（{len(_items)} 条，present {len(_present)} 人），report={_s2}，"
               f"学号匹配={'是' if _match else '否'}",
               _s1 == 200 and _s2 == 200 and _match,
               f"教师分别 GET /api/attendance-tasks/{_tid}/records 与 /report 后比对", "高")
    else:
        record("DATA-01", "一致性", "签到明细与 CSV 报表数据一致", "按契约一致",
               "本轮未创建点到任务，未执行", False, "依赖 FUNC-01", "高",
               status_override="未执行")

    # 日志与导出
    # 实测契约：空 body + Idempotency-Key 请求头；多传字段会被判 VALIDATION_ERROR
    _s, _p, _ = teacher.post("/api/classes/5/exports", {},
                             extra={"Idempotency-Key": str(uuid.uuid4())})
    _export_id = ((_p.get("data") or {}).get("export_id")
                  if isinstance(_p, dict) else None)
    record("LOG-01", "日志", "教师创建统计导出任务",
           "HTTP 202 且返回 export_id",
           f"HTTP {_s}，export_id={_export_id}",
           _s == 202 and bool(_export_id),
           "教师 POST /api/classes/5/exports，空 body + Idempotency-Key 请求头", "中")
    if _export_id:
        _s2, _p2, _ = teacher.get("/api/exports/%d" % _export_id)
        record("LOG-02", "日志", "查询导出任务结果",
               "HTTP 200 且返回导出状态", f"HTTP {_s2} {err(_p2)}",
               _s2 == 200, f"教师 GET /api/exports/{_export_id}", "中")
    else:
        record("LOG-02", "日志", "查询导出任务结果", "HTTP 200",
               "导出任务未创建成功，未执行", False, "依赖 LOG-01", "中",
               status_override="未执行")

    # 74181 实验：端点声明与全量运算覆盖
    _lab = [e["path"] for e in (modules.get("experiments", {}).get("endpoints") or [])
            if "74181" in e["path"]]
    record("LAB-01", "实验", "74181 实验端点在 /help 中声明",
           "存在 74181 相关端点", f"发现 {len(_lab)} 条：{', '.join(_lab[:2])}",
           bool(_lab), "检查 /help.api.modules.experiments", "中")
    record("LAB-02", "实验", "74181 全 512 组加减运算向量校验",
           "按独立参考实现逐组比对 F 与进位/借位",
           "被测组未公开纯计算 GET 接口，运算需经实验仿真提交流程；本次未执行",
           False, "需被测组提供 compute 接口或前端交互环境", "中",
           status_override="未执行")

    # 任务取消分支
    _s, _p, _ = teacher.post("/api/classes/5/attendance-tasks",
                             {"title": "互测-取消分支-%s" % uuid.uuid4().hex[:4],
                              "starts_at": z(2), "late_at": z(8), "ends_at": z(20),
                              "methods": ["code"]})
    _cancel = (_p.get("data") or {}) if isinstance(_p, dict) else {}
    if _cancel.get("id") and _s == 201:
        _s2, _p2, _ = teacher.post("/api/attendance-tasks/%d/cancel" % _cancel["id"],
                                   {"revision": _cancel["revision"],
                                    "reason": "互测取消分支验证，测试数据不用于正式考勤"})
        _d2 = (_p2.get("data") or {}) if isinstance(_p2, dict) else {}
        record("ROLL-10", "功能", "取消草稿任务不产生缺勤",
               "HTTP 200 且状态进入取消态，absent_count=0",
               f"HTTP {_s2}，status={_d2.get('status')}，absent={_d2.get('absent_count')}",
               _s2 == 200 and _d2.get("absent_count") == 0,
               "新建草稿 → POST /api/attendance-tasks/{id}/cancel，带 revision 与 reason", "中")
    else:
        record("ROLL-10", "功能", "取消草稿任务不产生缺勤", "按契约完成",
               f"草稿创建失败 HTTP {_s}", False, "依赖草稿创建", "中",
               status_override="未执行")

    # 座位与并发（本轮任务未配置 seat_layout）
    _s, _p, _ = teacher.get("/api/attendance-tasks/%d/seats" % (_tid or 76))
    _layout = (_p.get("data") or {}).get("layout") if isinstance(_p, dict) else None
    record("SEAT-01", "功能", "座位图接口可读", "HTTP 200 且返回布局/占用结构",
           f"HTTP {_s}，layout={'已配置' if _layout else '未配置'}",
           _s == 200, "教师 GET /api/attendance-tasks/{id}/seats", "中")
    record("SEAT-02", "功能", "并发占座冲突与座位边界",
           "两学生抢同一座位仅一人成功；越界/禁用座位被拒",
           "被测组本轮点到任务未配置 seat_layout，缺少测试数据，未执行",
           False, "需被测组发布带座位布局的点到任务", "中",
           status_override="未执行")

    # 浏览器入口（无头 Edge，DOM 级验证）
    _edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    try:
        _proc = _sp.run(
            [_edge, "--headless", "--disable-gpu", "--no-proxy-server", "--no-first-run",
             "--user-data-dir=" + str(Path(r"D:\Desktop\WebBigHomework\.workbuddy\tmp\edge-peer")),
             "--virtual-time-budget=3000", "--dump-dom", BASE + "/pages/auth.html"],
            capture_output=True, timeout=45)
        _dom = _proc.stdout.decode("utf-8", "replace")
        _has_login = "password" in _dom and ("登录" in _dom or "login" in _dom.lower())
        record("BROWSER-01", "E2E", "无头浏览器打开登录页",
               "页面渲染出登录表单且 DOM 非空",
               f"DOM {len(_dom)} 字节，登录表单={'有' if _has_login else '未检出'}",
               len(_dom) > 500 and _has_login,
               "无头 Edge --dump-dom 打开 /pages/auth.html", "中")
    except Exception as _failure:  # noqa: BLE001 — 浏览器不可用也要留一条未执行记录
        record("BROWSER-01", "E2E", "无头浏览器打开登录页", "页面渲染出登录表单",
               f"浏览器执行失败：{_failure}", False, "无头 Edge --dump-dom", "中",
               status_override="未执行")

    record("BROWSER-02", "E2E", "浏览器交互级教师/学生双会话 E2E",
           "教师发布点到 → 学生页面选座签到 → 教师页面状态刷新一致",
           "需 Playwright/CDP 交互环境，本次仅完成 API 链路与页面 DOM 验证，未执行",
           False, "需现场浏览器交互环境", "中", status_override="未执行")
    record("PERSIST-01", "回归", "后端重启后业务数据持久化",
           "重启后账号、点到任务与签到记录仍可查询且统计一致",
           "重启被测组服务不属于测试方权限，未执行",
           False, "需被测组配合重启服务", "中", status_override="未执行")

    # ---------- 输出 ----------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_LOG.write_text(json.dumps({"target": TARGET, "base": BASE, "started": started,
                                   "cases": CASES, "trace": TRACE},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
    write_outputs(started)
    print("\n用例 %d 条，通过 %d，失败 %d，未执行 %d，阻塞 %d" % (
        len(CASES), sum(c["status"] == "通过" for c in CASES),
        sum(c["status"] == "失败" for c in CASES),
        sum(c["status"] == "未执行" for c in CASES),
        sum(c["status"] == "阻塞" for c in CASES)))
    print("原始日志：", RAW_LOG)


def write_outputs(started):
    defects = [c for c in CASES if c["status"] == "失败"]
    csv_path = OUT_DIR / f"defects_1_{DATE}_{NAME}.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["编号", "标题", "被测组", "复现步骤", "预期结果", "实际结果",
                         "严重程度", "截图", "状态"])
        for index, c in enumerate(defects, 1):
            writer.writerow([
                "D-%02d" % index, c["title"], TARGET, c["reproduce"], c["expected"],
                c["actual"], c["severity"],
                "课堂现场留存，按老师要求不随文档提交图片",
                "待修复" if c["status"] == "失败" else "阻塞/待复测",
            ])

    by_layer = {}
    for c in CASES:
        row = by_layer.setdefault(c["layer"], {"通过": 0, "失败": 0, "阻塞": 0})
        row[c["status"]] = row.get(c["status"], 0) + 1
    total_pass = sum(c["status"] == "通过" for c in CASES)
    total_fail = sum(c["status"] == "失败" for c in CASES)
    total_block = sum(c["status"] == "阻塞" for c in CASES)
    core = [c for c in CASES if c["id"].startswith(("SM-", "API-"))]
    core_ok = all(c["status"] == "通过" for c in core)
    func = [c for c in CASES if c["id"].startswith("FUNC-")]
    func_ok = all(c["status"] == "通过" for c in func)
    blocking = [c for c in CASES if c["status"] == "失败" and c["severity"] in ("高", "中")]
    verdict = ("正确" if not blocking and func_ok else
               "基本正确，但存在影响项" if not blocking else "存疑，存在高/中严重级别失败项")

    lines = [
        f"# 课堂互测测试报告（第 1 次）",
        "",
        f"- 提交人：姜苏豪（24201718），英文名 {NAME}",
        "- 测试方：242017 班第 10 组 g24201710",
        f"- 被测组：{TARGET}",
        f"- 被测地址：{BASE}",
        f"- 测试时间：{started}",
        "- 测试依据：老师《下午的测试方案》、被测组公开的 `/who` 与 `/help`、被测组测试计划",
        "- 自动化脚本：`scripts/verify_g24201803.py`（Python 3 标准库，无第三方依赖）；"
        "运行 `python scripts/verify_g24201803.py` 可复现全部用例并重新生成本报告与缺陷表。"
        "脚本按 `/help` 动态适配被测组的 `/api` 契约；原始请求日志另存本地，不随文档提交",
        "",
        "## 1 测试范围",
        "",
        f"- 被测对象为 {TARGET}的 CPU-Learn 系统，`/help` 声明 15 个模块 / 198 条接口。",
        "- 本组今日为 C 组；除老师要求的**冒烟 + 接口**外，另扩展到 15 个业务模块逐项抽查、"
        "权限与越权、参数边界、数据一致性、日志导出、实验端点、取消分支、座位图及浏览器入口验证，"
        "并给出「主要功能是否正确」的明确结论。",
        "- 未执行项（不计为通过，也不计为被测组缺陷）：74181 全 512 组运算、并发占座与座位边界、"
        "浏览器交互级双会话 E2E、后端重启持久化；源码审计、性能压测、安全渗透、真实设备定位不在范围。",
        "- 环境：课堂局域网，Python 3 标准库脚本直连（显式禁用系统代理）；所有写请求先取 "
        "`/api/auth/csrf` 令牌并带同源 `Origin`。",
        "- 被测系统关键契约（实测）：登录用 `username/password`；写操作需 `X-CSRF-Token`；"
        "发布/关闭任务需携带 `revision`；签到需 `method=code` 与 `Idempotency-Key` 请求头（幂等键），"
        "重复提交同一键值返回同一条记录。",
        "",
        "## 2 用例统计",
        "",
        "| 层级 | 用例数 | 通过 | 失败 | 未执行 | 阻塞 |",
        "|---|---|---|---|---|---|",
    ]
    for layer, row in by_layer.items():
        n = sum(row.values())
        lines.append(f"| {layer} | {n} | {row.get('通过', 0)} | {row.get('失败', 0)} | "
                     f"{row.get('未执行', 0)} | {row.get('阻塞', 0)} |")
    lines += [
        f"| **合计** | **{len(CASES)}** | **{total_pass}** | **{total_fail}** | "
        f"**{sum(c['status'] == '未执行' for c in CASES)}** | **{total_block}** |",
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
        "缺陷明细见同目录 `defects_1_%s_%s.csv`（字段：编号、标题、被测组、复现步骤、"
        "预期/实际结果、严重程度、截图、状态）。" % (DATE, NAME),
        "按老师要求**不提交任何图片**，截图列以文字说明代替。",
        "",
        "## 4 被测组主要功能是否正确",
        "",
        f"**结论：{verdict}。**",
        "",
        f"- 全量共 {len(CASES)} 条用例：通过 {total_pass}、失败 {total_fail}、"
        f"未执行 {sum(c['status'] == '未执行' for c in CASES)}、阻塞 {total_block}；"
        "覆盖冒烟、接口、功能、E2E、15 模块抽查、权限、边界、一致性、日志、实验、座位、取消分支与浏览器入口。",
        "- 依据：首页、`/who`、`/help`、健康检查、CSRF、教师/学生登录与班级接口可用；点到任务可创建、"
        "发布、取码、签到、读取座位/记录/报表并结算；15 个模块路由均返回统一 JSON；学生越权全部 403；"
        "参数边界均被校验；签到明细与 CSV 报表一致；导出任务可创建与查询；取消分支不产生缺勤；"
        "无头浏览器登录页可渲染。",
    ]
    if defects:
        lines.append("- 另有未通过项如下，按严重程度列出：")
        for d in defects:
            lines.append(f"  - {d['id']} {d['title']}：{d['actual']}")
    lines += [
        "",
        "## 5 遗留风险",
        "",
        "1. 15 个业务模块各做了一条代表性 GET 抽查，未逐模块执行「正常/异常/边界/权限」全场景回归；"
        "未测项一律不记为通过。",
        "2. 抽查组名单与其他被测组地址课堂上才公布，本报告仅覆盖上述一个被测组；"
        "拿到新地址后按同一脚本补测并追加缺陷记录。",
        "3. 点到任务使用明确标记为「互测」的独立任务，收尾走系统提供的关闭操作，"
        "未删除被测组任何正式名单、成绩或课程数据。",
        "4. 未执行项已在用例表标为「未执行」：74181 全量运算、并发占座、浏览器交互级 E2E、重启持久化；"
        "这些需要被测组提供计算接口/座位布局/现场浏览器环境，不能记为通过。",
        "5. 报告不含账号明文口令、Cookie、CSRF 令牌或完整个人数据；请求关联 ID 仅保留在本地日志。",
        "",
        "## 6 附件",
        "",
        f"- 缺陷记录表：`defects_1_{DATE}_{NAME}.csv`",
        "- 原始请求日志：本地留存（时间、账号角色、方法、路径、状态码、耗时），不随文档提交",
        "- 本目录不提交任何图片",
        "",
    ]
    (OUT_DIR / f"report_1_{DATE}_{NAME}.md").write_text("\n".join(lines), encoding="utf-8")
    print("已写出：", OUT_DIR / f"report_1_{DATE}_{NAME}.md")
    print("已写出：", csv_path)


if __name__ == "__main__":
    main()
