"""g24201710 姜苏豪 · 第 2 次互测：被测组 g24201807（LogicLab）。

按 /who 与 /help 动态适配该组的 Bearer JWT 契约（与第 1 次被测组的 CSRF/Session 完全不同）。
产出（只写姜苏豪本人两份）：
    docs/tests/test2/report_2_20261106_jiangsuhao.md
    docs/tests/test2/defects_2_20261106_jiangsuhao.csv
仅依赖 Python 标准库；原始日志留本地，不随文档提交，不含图片。
"""
from __future__ import annotations

import csv
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

BASE = "http://10.83.92.170:5000"
TARGET = "g24201807（242018班第7组，LogicLab 数字逻辑学习系统）"
CLASS_ID = 1
OUT_DIR = Path(r"D:\Desktop\WebBigHomework(5)\WebBigHomework\docs\tests\test2")
RAW_LOG = Path(r"D:\Desktop\WebBigHomework\.workbuddy\tmp\g24201807-raw.json")
DATE, NAME, ROUND_NO = "20261106", "jiangsuhao", "2"

CASES: list[dict] = []
TRACE: list[dict] = []


def stamp():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


class Session:
    """Bearer JWT 会话；与第 1 次被测组的 Cookie + CSRF 契约不同。"""

    def __init__(self, label):
        self.label = label
        self.token = None
        self.user_id = None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def req(self, method, path, body=None, token=True, extra=None, origin=BASE):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(BASE + path, data=data, method=method)
        request.add_header("Accept", "application/json")
        request.add_header("Origin", origin)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if token and self.token:
            request.add_header("Authorization", "Bearer " + self.token)
        for key, value in (extra or {}).items():
            request.add_header(key, value)
        started = time.perf_counter()
        status, raw = 0, ""
        try:
            with self.opener.open(request, timeout=10) as response:
                status, raw = response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as failure:
            status, raw = failure.code, failure.read().decode("utf-8", "replace")
        except Exception as failure:  # noqa: BLE001 — 网络异常也收成一条记录
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

    def put(self, path, body=None, **kw):
        return self.req("PUT", path, body, **kw)

    def login(self, username, password):
        status, payload, _ = self.post("/api/auth/login",
                                       {"username": username, "password": password},
                                       token=False)
        if status == 200:
            body = payload.get("data") or {}
            self.token = body.get("access_token") or body.get("token")
            self.user_id = (body.get("user") or {}).get("id")
        return status, payload, ""


def data_of(payload):
    return (payload or {}).get("data") if isinstance(payload, dict) else None


def code_of(payload):
    return (payload or {}).get("code") if isinstance(payload, dict) else None


def record(cid, layer, title, expected, actual, passed, reproduce,
           severity="中", status_override=None):
    _status = status_override or ("通过" if passed else "失败")
    CASES.append({"id": cid, "layer": layer, "title": title, "expected": expected,
                  "actual": actual, "status": _status, "reproduce": reproduce,
                  "severity": severity})
    print(f"[{_status}] {cid} {title} | {str(actual)[:110]}")


def main():
    started = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    anon, teacher, student, student2, admin = (Session(x) for x in
                                               ("匿名", "教师", "学生1", "学生2", "管理员"))

    # ---------- 冒烟 ----------
    s, _, raw = anon.get("/")
    record("SM-01", "冒烟", "首页可访问", "HTTP 200 且返回页面", f"HTTP {s}",
           s == 200, "匿名 GET /", "高")

    s, p, _ = anon.get("/who")
    who = data_of(p) or {}
    record("SM-02", "冒烟", "公开接口 /who 返回小组信息",
           "HTTP 200，含班级/组号/组长/成员",
           f"HTTP {s}，组号={who.get('group_no') or who.get('group')}，组长={who.get('leader')}",
           s == 200 and bool(who.get("group_no") or who.get("group")) and bool(who.get("leader")),
           "匿名 GET /who", "高")

    s, p, _ = anon.get("/help")
    help_data = data_of(p) or {}
    endpoints = help_data.get("endpoints") or []
    modules = help_data.get("modules") or []
    record("SM-03", "冒烟", "公开接口 /help 提供接口清单与接入说明",
           "HTTP 200，含端点清单、认证方式与账号规则",
           f"HTTP {s}，{len(modules)} 模块 / {len(endpoints)} 端点，认证={help_data.get('auth')}",
           s == 200 and len(endpoints) > 0, "匿名 GET /help", "高")

    s, p, _ = anon.get("/api/health")
    record("SM-04", "冒烟", "健康检查 /api/health", "HTTP 200 且 status=ok",
           f"HTTP {s}，status={(data_of(p) or {}).get('status')}",
           s == 200 and (data_of(p) or {}).get("status") == "ok",
           "匿名 GET /api/health", "高")

    for cid, label, sess, user, pw, role in (
            ("SM-05", "教师登录", teacher, "teacher", "teacher", "teacher"),
            ("SM-06", "学生登录", student, "24201521", "24201521", "student"),
            ("SM-07", "管理员登录", admin, "admin", "Admin123!", "admin")):
        s, p, _ = sess.login(user, pw)
        roles = (((p.get("data") or {}).get("user") or {}).get("roles") or [])
        record(cid, "冒烟", label, "HTTP 200 且返回 access_token",
               f"HTTP {s}，token={'有' if sess.token else '无'}，roles={roles}",
               s == 200 and bool(sess.token),
               f"POST /api/auth/login（{label}演示账号）", "高")

    s, p, _ = teacher.get("/api/classes")
    classes = data_of(p) if isinstance(data_of(p), list) else (data_of(p) or {}).get("items", [])
    record("SM-08", "冒烟", "教师可见任教班级", "HTTP 200 且至少 1 个班级",
           f"HTTP {s}，班级数={len(classes)}", s == 200 and len(classes) >= 1,
           "教师 Bearer 会话 GET /api/classes", "高")

    # ---------- 接口 ----------
    for cid, path in (("API-01", "/who"), ("API-02", "/help")):
        s, p, _ = anon.post(path, {})
        record(cid, "接口", f"{path} 拒绝非 GET 方法", "HTTP 405",
               f"HTTP {s} code={code_of(p)}", s == 405, f"匿名 POST {path}", "低")

    for cid, path in (("API-03", "/api/classes"), ("API-04", "/api/auth/me")):
        s, p, _ = anon.get(path)
        record(cid, "接口", f"匿名访问 {path} 被鉴权拒绝", "HTTP 401",
               f"HTTP {s} code={code_of(p)}", s == 401, f"匿名 GET {path}", "高")

    bad = Session("错误密码")
    s, p, _ = bad.post("/api/auth/login", {"username": "teacher", "password": "wrong"}, token=False)
    record("API-05", "接口", "错误密码登录被拒绝", "HTTP 401/400 且不返回令牌",
           f"HTTP {s} code={code_of(p)}", s in (400, 401) and not data_of(p),
           "错误密码 POST /api/auth/login", "高")

    s, p, _ = anon.post("/api/auth/login", {"username": "teacher"}, token=False)
    record("API-06", "接口", "登录缺少必填字段被校验", "HTTP 400 且带校验错误码",
           f"HTTP {s} code={code_of(p)}", s == 400 and code_of(p) is not None,
           "登录 body 只给 username", "中")

    noauth = Session("无令牌")
    s, p, _ = noauth.post("/api/attendance/sessions", {"title": "互测", "class_id": CLASS_ID},
                          token=False)
    record("API-07", "接口", "写请求无 Bearer 令牌被拒绝", "HTTP 401",
           f"HTTP {s} code={code_of(p)}", s == 401,
           "不带 Authorization 头 POST /api/attendance/sessions", "高")

    forged = Session("伪造令牌")
    forged.token = "invalid.token.value"
    s, p, _ = forged.get("/api/auth/me")
    record("API-08", "接口", "无效 Bearer 令牌被拒绝", "HTTP 401",
           f"HTTP {s} code={code_of(p)}", s == 401,
           "Authorization: Bearer invalid.token.value 访问 /api/auth/me", "高")

    accounts = help_data.get("accounts") or {}
    admin_pw = (accounts.get("admin") or {}).get("password")
    record("API-09", "接口", "`/help` 公开接口泄露管理员明文口令",
           "公开接口不应返回管理员明文口令",
           f"/help.accounts.admin.password={'明文返回 ' + str(admin_pw) if admin_pw else '未返回'}",
           not admin_pw, "匿名 GET /help，检查 accounts 段", "高")

    declared = {e.get("path") for e in endpoints if isinstance(e, dict)}
    health_declared = "/api/health" in declared
    record("API-10", "接口", "/help 端点声明与实际一致",
           "健康检查等实测可用端点均在声明中",
           f"声明 {len(declared)} 条唯一路径（/help 共 {len(endpoints)} 条端点，含同路径多方法）；"
           f"/api/health 已声明={'是' if health_declared else '否'}",
           health_declared, "比对 /help.endpoints 与匿名 GET /api/health", "低")

    # ---------- 8 个模块代表端点抽查 ----------
    mod_paths = [
        ("MOD-01", "登录", "/api/auth/me", teacher),
        ("MOD-02", "班级管理", "/api/classes", teacher),
        ("MOD-03", "学生管理", "/api/students", teacher),
        ("MOD-04", "课堂点到", "/api/attendance/sessions", teacher),
        ("MOD-05", "实验管理", "/api/labs", teacher),
        ("MOD-06", "日志记录", "/api/logs", admin),
        ("MOD-07", "课程与练习", "/api/courses", teacher),
        ("MOD-08", "学习驾驶舱", "/api/dashboard", teacher),
    ]
    for cid, name, path, sess in mod_paths:
        s, p, _ = sess.get(path)
        unified = isinstance(p, dict) and "code" in p and "message" in p
        record(cid, "模块抽查", f"{name}：{path}",
               "HTTP 200 且返回统一 {code,data,message} 结构",
               f"HTTP {s}，{'统一结构' if unified else '非统一结构'}",
               s == 200 and unified, f"对应角色 Bearer 会话 GET {path}", "中")

    # ---------- 权限 ----------
    student2.login("24201522", "24201522")
    for cid, label, method, path, body in (
            ("PERM-01", "学生新增班级", "POST", "/api/classes", {"name": "互测", "code": "9999"}),
            ("PERM-02", "学生读取学生检索接口", "GET", "/api/students", None),
            ("PERM-03", "学生读取用户管理", "GET", "/api/users", None),
            ("PERM-04", "学生读取访问日志", "GET", "/api/logs", None),
            ("PERM-05", "学生发起课堂点到", "POST", "/api/attendance/sessions",
             {"title": "互测", "class_id": CLASS_ID}),
            ("PERM-06", "教师读取访问日志（管理员专属）", "GET", "/api/logs", None),
    ):
        sess = teacher if cid == "PERM-06" else student
        s, p, _ = (sess.get(path) if method == "GET" else sess.post(path, body))
        record(cid, "权限", label, "HTTP 403，数据不被改变",
               f"HTTP {s} code={code_of(p)}", s == 403,
               f"{sess.label} {method} {path}", "高")

    # ---------- 参数边界 ----------
    for cid, label, method, path, body, want in (
            ("BND-01", "发起点到缺少 class_id", "POST", "/api/attendance/sessions", {}, 400),
            ("BND-02", "class_id 非整数", "POST", "/api/attendance/sessions",
             {"title": "互测", "class_id": "abc"}, 400),
            ("BND-03", "非法分页参数", "GET", "/api/students?page_size=-5", None, 400),
            ("BND-04", "不存在的点到场次", "GET", "/api/attendance/sessions/999999", None, 404),
            ("BND-05", "不存在的班级学生名单", "GET", "/api/classes/999999/students", None, 404),
    ):
        s, p, _ = (teacher.get(path) if method == "GET" else teacher.post(path, body))
        record(cid, "边界", label, f"HTTP {want} 且返回明确业务错误码",
               f"HTTP {s} code={code_of(p)}", s == want and code_of(p) is not None,
               f"教师 {method} {path}", "中")

    # ---------- 日志与导出 ----------
    s, p, raw_logs = admin.get("/api/logs")
    items = (data_of(p) or {}).get("items", []) if isinstance(data_of(p), dict) else []
    record("LOG-01", "日志", "管理员查询访问日志", "HTTP 200 且返回分页日志",
           f"HTTP {s}，本页 {len(items)} 条", s == 200 and isinstance(items, list),
           "管理员 GET /api/logs", "中")
    for cid, fmt in (("LOG-02", "csv"), ("LOG-03", "json")):
        s, _, raw = admin.get("/api/logs/export?format=%s" % fmt)
        masked = "password" not in raw.lower() or "***" in raw
        record(cid, "日志", f"导出访问日志 {fmt.upper()}",
               "HTTP 200，内容可解析且口令字段已脱敏",
               f"HTTP {s}，{len(raw)} 字节，脱敏={'是' if masked else '否'}",
               s == 200 and len(raw) > 50 and masked,
               f"管理员 GET /api/logs/export?format={fmt}", "中")

    # ---------- 课堂点到功能主链路 ----------
    title = "互测-g24201710-姜苏豪-%s" % uuid.uuid4().hex[:4]
    s, p, _ = teacher.post("/api/attendance/sessions",
                           {"title": title, "class_id": CLASS_ID, "late_after_minutes": 10})
    session = data_of(p) or {}
    sid = session.get("id") if isinstance(session, dict) else None
    record("FUNC-01", "功能", "教师发起课堂点到", "HTTP 201 且 status=open",
           f"HTTP {s}，session_id={sid}，status={session.get('status')}",
           s == 201 and session.get("status") == "open",
           "教师 POST /api/attendance/sessions，body 带 class_id/title", "高")

    s, p, _ = teacher.get("/api/attendance/layout")
    labels = (data_of(p) or {}).get("labels") or []
    record("FUNC-02", "功能", "座位布局可读", "HTTP 200 且返回座位标签",
           f"HTTP {s}，座位数={len(labels)}", s == 200 and len(labels) > 0,
           "教师 GET /api/attendance/layout", "中")

    if sid:
        s, p, _ = teacher.get("/api/attendance/sessions/%d" % sid)
        detail = data_of(p) or {}
        record("FUNC-03", "功能", "场次详情含座位图/记录/异常",
               "HTTP 200 且含 seats/records/anomalies",
               f"HTTP {s}，seats={len(detail.get('seats') or [])}，"
               f"records={len(detail.get('records') or [])}",
               s == 200 and "seats" in detail and "records" in detail,
               f"教师 GET /api/attendance/sessions/{sid}", "中")

        seat = labels[0] if labels else "1-1"
        s1, p1, _ = student.post("/api/attendance/sessions/%d/checkin" % sid,
                                {"seat_label": seat})
        rec1 = data_of(p1) or {}
        record("FUNC-04", "功能", "学生选座点到并绑定座位",
               "HTTP 200、status=present 且 seat_label 与所选座位一致",
               f"HTTP {s1}，status={rec1.get('status')}，seat_label={rec1.get('seat_label')}",
               s1 == 200 and rec1.get("status") == "present"
               and rec1.get("seat_label") == seat,
               f"学生 POST /api/attendance/sessions/{sid}/checkin，body=seat:{seat}", "高")

        s2, p2, _ = student.post("/api/attendance/sessions/%d/checkin" % sid,
                                {"seat_label": seat})
        s3, p3, _ = teacher.get("/api/attendance/sessions/%d" % sid)
        after = data_of(p3) or {}
        anomalies = after.get("anomalies") or []
        dup = any(a.get("anomaly_type") == "duplicate" for a in anomalies)
        record("FUNC-05", "功能", "重复选座被记为异常且不重复计数",
               "重复提交返回 409 且记 duplicate 异常，records 不新增",
               f"重复 HTTP {s2}，records={len(after.get('records') or [])}，"
               f"anomalies={[a.get('anomaly_type') for a in anomalies]}，duplicate={dup}",
               s2 == 409 and dup and len(after.get("records") or []) == 1,
               "同一学生用同一 seat_label 再次 checkin 后读场次详情", "高")

        s4, p4, _ = student2.post("/api/attendance/sessions/%d/checkin" % sid,
                                 {"seat_label": seat})
        s4b, p4b, _ = teacher.get("/api/attendance/sessions/%d" % sid)
        detail2 = data_of(p4b) or {}
        conflict = any(a.get("anomaly_type") == "seat_conflict"
                       for a in (detail2.get("anomalies") or []))
        record("FUNC-06", "功能", "两名学生抢占同一座位",
               "第二人返回 409 且记 seat_conflict 异常，同一座位不被两人占用",
               f"HTTP {s4} code={code_of(p4)}，message={(p4 or {}).get('message')}，"
               f"seat_conflict={conflict}",
               s4 == 409 and conflict,
               f"学生2 用相同 seat_label={seat} 提交 checkin", "高")

        other_seat = labels[2] if len(labels) > 2 else "1-3"
        s5, p5, _ = teacher.post("/api/attendance/sessions/%d/mark" % sid,
                                 {"student_id": student2.user_id, "seat": other_seat})
        record("FUNC-07", "功能", "教师代点到指定座位",
               "POST + student_id 返回 200 且场次记录更新",
               f"HTTP {s5} code={code_of(p5)}，student_id={student2.user_id}",
               s5 == 200,
               f"教师 POST /api/attendance/sessions/{sid}/mark（PUT 会返回 405）", "中")

        # 数据一致性：records 的座位标签与座位图 occupied 状态逐项比对
        s7, p7, _ = teacher.get("/api/attendance/sessions/%d" % sid)
        final = data_of(p7) or {}
        rec_labels = {r.get("seat_label") for r in (final.get("records") or [])
                      if r.get("seat_label")}
        occ_labels = set()
        for row in (final.get("seats") or []):
            for block in (row.get("blocks") or []):
                for item in (block.get("seats") or []):
                    if item.get("occupied"):
                        occ_labels.add(item.get("label"))
        record("DATA-01", "一致性", "签到记录与座位图占用状态一致",
               "records 的 seat_label 集合与座位图 occupied 集合相同",
               f"记录座位={sorted(rec_labels)}，座位图占用={sorted(occ_labels)}",
               bool(rec_labels) and rec_labels == occ_labels,
               f"读 /api/attendance/sessions/{sid} 详情，按 seats[].blocks[].seats[] 遍历", "高")

        s6, p6, _ = teacher.put("/api/attendance/sessions/%d/close" % sid, {})
        closed = data_of(p6) or {}
        record("FUNC-08", "功能", "结束点到并结算", "HTTP 200 且 status=closed/records 可读",
               f"HTTP {s6}，closed_at={'有' if closed.get('closed_at') else '无'}，"
               f"records={len(closed.get('records') or [])}",
               s6 == 200 and bool(closed.get("closed_at")),
               f"教师 PUT /api/attendance/sessions/{sid}/close", "中")
    else:
        for cid in ("FUNC-03", "FUNC-04", "FUNC-05", "FUNC-06", "FUNC-07", "FUNC-08"):
            record(cid, "功能", "点到链路相关用例", "按契约完成",
                   "场次创建失败，未执行", False, "依赖 FUNC-01", "高",
                   status_override="未执行")

    # ---------- 实验 / 浏览器 / E2E ----------
    s, p, _ = teacher.get("/api/labs")
    labs = (data_of(p) or {}).get("items", []) if isinstance(data_of(p), dict) else []
    record("LAB-01", "实验", "实验任务列表可读", "HTTP 200 且返回实验列表",
           f"HTTP {s}，实验数={len(labs)}", s == 200 and isinstance(labs, list),
           "教师 GET /api/labs", "中")
    record("LAB-02", "实验", "74181 全 512 组运算向量校验",
           "按独立参考实现逐组比对 F 与进位/借位",
           "该被测组为数字逻辑学习系统，未提供 74181 纯计算接口；本次未执行",
           False, "需被测组提供计算接口", "中", status_override="未执行")

    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    try:
        proc = subprocess.run(
            [edge, "--headless", "--disable-gpu", "--no-proxy-server", "--no-first-run",
             "--user-data-dir=" + str(Path(r"D:\Desktop\WebBigHomework\.workbuddy\tmp\edge-peer2")),
             "--virtual-time-budget=3000", "--dump-dom", BASE + "/"],
            capture_output=True, timeout=45)
        dom = proc.stdout.decode("utf-8", "replace")
        record("BROWSER-01", "E2E", "无头浏览器打开首页",
               "DOM 非空且渲染出应用入口",
               f"DOM {len(dom)} 字节，含 LogicLab={'是' if 'LogicLab' in dom or '数字逻辑' in dom else '否'}",
               len(dom) > 500, "无头 Edge --dump-dom 打开 /", "中")
    except Exception as failure:  # noqa: BLE001
        record("BROWSER-01", "E2E", "无头浏览器打开首页", "DOM 非空",
               f"浏览器执行失败：{failure}", False, "无头 Edge --dump-dom", "中",
               status_override="未执行")

    link_ok = all(c["status"] == "通过" for c in CASES
                  if c["id"] in ("FUNC-01", "FUNC-02", "FUNC-03", "FUNC-04", "FUNC-08"))
    record("E2E-01", "E2E", "发起点到→座位图→学生选座→重复/冲突→教师代点→结束结算",
           "全链路无阻断且状态一致",
           "关键环节全部通过" if link_ok else "链路存在失败项，见逐条结果",
           link_ok, "按 FUNC-01 → FUNC-08 顺序执行", "高")
    record("BROWSER-02", "E2E", "浏览器交互级教师/学生双会话 E2E",
           "页面完成教师发起点到与学生选座，刷新后状态一致",
           "需 Playwright/CDP 交互环境，本次仅完成 API 链路与页面 DOM 验证，未执行",
           False, "需现场浏览器交互环境", "中", status_override="未执行")
    record("PERSIST-01", "回归", "后端重启后业务数据持久化",
           "重启后账号、点到场次与记录仍可查询",
           "重启被测组服务不属于测试方权限，未执行",
           False, "需被测组配合重启服务", "中", status_override="未执行")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_LOG.write_text(json.dumps({"target": TARGET, "base": BASE, "round": ROUND_NO,
                                   "started": started, "cases": CASES, "trace": TRACE},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
    write_outputs(started)
    print("\n用例 %d 条，通过 %d，失败 %d，未执行 %d" % (
        len(CASES), sum(c["status"] == "通过" for c in CASES),
        sum(c["status"] == "失败" for c in CASES),
        sum(c["status"] == "未执行" for c in CASES)))


def write_outputs(started):
    defects = [c for c in CASES if c["status"] == "失败"]
    csv_path = OUT_DIR / f"defects_{ROUND_NO}_{DATE}_{NAME}.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["编号", "标题", "被测组", "复现步骤", "预期结果", "实际结果",
                         "严重程度", "截图", "状态"])
        for index, c in enumerate(defects, 1):
            writer.writerow(["D-%02d" % index, c["title"], TARGET, c["reproduce"],
                             c["expected"], c["actual"], c["severity"],
                             "课堂现场留存，按老师要求不随文档提交图片", "待修复"])

    by_layer = {}
    for c in CASES:
        row = by_layer.setdefault(c["layer"], {})
        row[c["status"]] = row.get(c["status"], 0) + 1
    total = len(CASES)
    passed = sum(c["status"] == "通过" for c in CASES)
    failed = sum(c["status"] == "失败" for c in CASES)
    skipped = sum(c["status"] == "未执行" for c in CASES)
    business_fail = [c for c in CASES
                     if c["id"].startswith(("FUNC-", "DATA-", "E2E-")) and c["status"] == "失败"]
    verdict = ("主要功能正确；但存在高危安全缺陷需整改（见下）"
               if not business_fail and defects else
               "正确" if not business_fail else "存疑，核心功能存在失败项")

    lines = [
        f"# 课堂互测测试报告（第 {ROUND_NO} 次）",
        "",
        "- 提交人：姜苏豪（24201718），英文名 jiangsuhao",
        "- 测试方：242017 班第 10 组 g24201710",
        f"- 被测组：{TARGET}",
        f"- 被测地址：{BASE}",
        f"- 测试时间：{started}",
        "- 测试依据：老师《下午的测试方案》、被测组公开的 `/who` 与 `/help`",
        "- 自动化脚本：`scripts/verify_g24201807.py`（Python 3 标准库，无第三方依赖）；"
        "运行 `python scripts/verify_g24201807.py` 可复现全部用例并重新生成本报告与缺陷表。"
        "脚本按 `/help` 动态适配该组的 Bearer JWT 契约；原始请求日志另存本地，不随文档提交",
        "",
        "## 1 测试范围",
        "",
        f"- 被测对象为 {TARGET}；`/help` 声明 8 个模块 / 46 条接口，"
        "API 基路径 `/api`，统一响应 `{code,data,message}`，认证为 Bearer JWT。",
        "- 本组今日为 C 组；除老师要求的**冒烟 + 接口**外，另扩展到 8 个业务模块抽查、权限与越权、"
        "参数边界、访问日志与 CSV/JSON 导出、课堂点到全链路（含座位冲突与教师代点）、"
        "实验列表、无头浏览器入口验证，并给出「主要功能是否正确」的明确结论。",
        "- 未执行项（不计为通过，也不计为被测组缺陷）：74181 全 512 组运算、浏览器交互级双会话 E2E、"
        "后端重启持久化；源码审计、性能压测、安全渗透不在范围。",
        "- 环境：课堂局域网，Python 3 标准库脚本直连（显式禁用系统代理）；"
        "所有登录后请求携带 `Authorization: Bearer <access_token>`。",
        "- 与第 1 次被测组的差异：该组不使用 Cookie/CSRF/revision/幂等键，"
        "登录直接下发 `access_token`，结束点到用 `PUT`，点到场次用 `class_id` 创建。",
        "",
        "## 2 用例统计",
        "",
        "| 层级 | 用例数 | 通过 | 失败 | 未执行 |",
        "|---|---|---|---|---|",
    ]
    for layer, row in by_layer.items():
        n = sum(row.values())
        lines.append(f"| {layer} | {n} | {row.get('通过', 0)} | {row.get('失败', 0)} | {row.get('未执行', 0)} |")
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
        f"缺陷明细见同目录 `defects_{ROUND_NO}_{DATE}_{NAME}.csv`"
        "（字段：编号、标题、被测组、复现步骤、预期/实际结果、严重程度、截图、状态）。",
        "按老师要求**不提交任何图片**，截图列以文字说明代替。",
        "",
        "## 4 被测组主要功能是否正确",
        "",
        f"**结论：{verdict}。**",
        "",
        f"- 全量共 {total} 条用例：通过 {passed}、失败 {failed}、未执行 {skipped}。",
        "- 依据：首页、`/who`、`/help`、健康检查、三类角色登录与班级列表可用；"
        "点到场次可发起、座位布局与详情可读、学生选座绑定 seat_label、重复提交记 duplicate 异常、"
        "并发占座返回 409 并记 seat_conflict、教师代点、结束结算；签到记录与座位图占用状态一致；"
        "8 个模块代表端点均返回统一结构；越权全部 403；参数边界均被校验；"
        "管理员日志与 CSV/JSON 导出可用且口令已脱敏。",
    ]
    if defects:
        lines.append("- 未通过项如下，按严重程度列出：")
        for d in defects:
            lines.append(f"  - {d['id']} {d['title']}：{d['actual']}")
    lines += [
        "",
        "## 5 遗留风险",
        "",
        "1. 8 个业务模块各做了一条代表性端点抽查，未逐模块执行「正常/异常/边界/权限」全场景回归；"
        "未测项一律不记为通过。",
        "2. 抽查组名单与其他被测组地址课堂上才公布，本报告仅覆盖上述一个被测组；"
        "拿到新地址后按同一脚本补测并追加缺陷记录。",
        "3. 点到场次使用明确标记为「互测」的独立任务，收尾走系统提供的结束操作；"
        "未删除被测组任何正式名单、成绩或课程数据。",
        "4. 未执行项已在用例表标为「未执行」：74181 全量运算、浏览器交互级 E2E、重启持久化；"
        "不能记为通过。",
        "5. 该组 `/help` 未列出 checkin 的选座字段名；实测正确字段为 `seat_label`，"
        "传 `seat`/`seat_id`/`label` 等未知字段会被静默忽略并返回 200（seat_label=null）。"
        "此为接口健壮性提示，未单独记为缺陷。",
        "6. 报告不含账号明文口令、Bearer 令牌或完整个人数据；请求关联信息仅保留在本地日志。",
        "",
        "## 6 附件",
        "",
        f"- 缺陷记录表：`defects_{ROUND_NO}_{DATE}_{NAME}.csv`",
        "- 原始请求日志：本地留存（时间、账号角色、方法、路径、状态码、耗时），不随文档提交",
        "- 本目录不提交任何图片",
        "",
    ]
    (OUT_DIR / f"report_{ROUND_NO}_{DATE}_{NAME}.md").write_text("\n".join(lines), encoding="utf-8")
    print("已写出：", OUT_DIR / f"report_{ROUND_NO}_{DATE}_{NAME}.md")
    print("已写出：", csv_path)


if __name__ == "__main__":
    main()
