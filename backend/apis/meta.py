"""SPEC-019 互测公开信息：GET /help 与 GET /who。

两个接口都无需登录、无需 CSRF，供课堂互测方自动发现接口与登录方式。
/help 的接口清单直接从 Flask url_map 生成，路由增删后无需手动维护。
"""

import re

from flask import Blueprint, current_app

from backend.shared import group
from backend.shared.api import request_id

bp = Blueprint("meta", __name__)


def readable(data, status=200):
    """这两个接口主要用于人工阅读与互测抓取，中文不转义成 \\uXXXX。

    响应形状与全局 result() 一致：{data, request_id}，只是编码方式不同。
    """
    text = current_app.json.dumps({"data": data, "request_id": request_id()}, ensure_ascii=False)
    return current_app.response_class(f"{text}\n", status=status, mimetype="application/json")


# blueprint 名 -> (SPEC 号, 中文模块名)。SPEC 号取自各 apis/*.py 首行 docstring。
MODULES = {
    "identity": ("SPEC-001", "用户与课程（身份与账号）"),
    "courses": ("SPEC-001", "用户与课程（课程与成员）"),
    "attendance": ("SPEC-002", "考勤（课堂点到）"),
    "resources": ("SPEC-003", "教学资源"),
    "preparations": ("SPEC-004", "备课"),
    "knowledge": ("SPEC-005", "课程知识"),
    "questions": ("SPEC-006", "习题测评（题库）"),
    "papers": ("SPEC-006", "习题测评（试卷）"),
    "attempts": ("SPEC-006", "习题测评（作答与批阅）"),
    "practices": ("SPEC-006", "习题测评（练习与错题）"),
    "demo": ("SPEC-007", "课堂演示"),
    "quizzes": ("SPEC-008", "随堂测"),
    "experiments": ("SPEC-009", "实验辅助"),
    "analytics": ("SPEC-010", "学习分析"),
    "qa": ("SPEC-011", "智能问答"),
    "recommendations": ("SPEC-012", "个性化推荐"),
    "warnings": ("SPEC-014", "学习预警"),
    "recognition": ("SPEC-016", "识别辅助"),
    "wiring": ("SPEC-017", "实验箱连线模拟"),
    "grading": ("SPEC-018", "Logisim 在线评测"),
    "alu": ("SPEC-019", "专业组在线实验（74181 加减运算器）"),
    "meta": ("SPEC-019", "互测公开信息"),
    "app": ("SPEC-019", "服务状态"),
}

# 只有已核实无需登录就能访问的接口才对外声明为 public。
PUBLIC_PATHS = {
    "/help",
    "/who",
    "/api/v1/health",
    "/api/v1/modules",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/alu74181/spec",
    "/api/v1/alu74181/table",
    "/api/v1/alu74181/compute",
}

GUIDES = [
    {
        "name": "统一响应格式",
        "points": [
            "成功：{data, request_id}；分页接口额外返回 page/page_size/total",
            "失败：HTTP 4xx/5xx + {error:{code,message,details}, request_id}",
            "时间为 UTC 的 ISO 8601 字符串，带 Z 后缀，例如 2026-11-01T06:10:28.000Z",
        ],
    },
    {
        "name": "登录与 CSRF",
        "points": [
            ("POST /api/v1/auth/login body={\"student_no\":\"teacher\",\"password\":\"teacher\"}，"
            "成功后 Set-Cookie: cpu_session"),
            "响应 data.csrf_token 供后续写请求使用",
            ("POST/PATCH/PUT/DELETE 必须同时带上与站点来源完全一致的 Origin 头"
            "（默认 http://127.0.0.1:5173）和 X-CSRF-Token 头，否则 403 CSRF_FAILED"),
            "GET /api/v1/auth/session 读取当前用户；POST /api/v1/auth/logout 注销并返回 204",
            "登录限流：同一账号每分钟最多 5 次，超过返回 429",
        ],
    },
    {
        "name": "课堂点到（互测主流程）",
        "points": [
            "1. 教师登录后 GET /api/v1/courses 取课程 id",
            ("2. POST /api/v1/courses/{course_id}/attendance-tasks "
            "body={title,start_at,late_at,end_at}，时间需带时区且 start_at<=late_at<=end_at，返回 201"),
            "3. 创建响应 data.code 为 6 位点到码；服务端只存哈希，仅在创建与轮换时各返回一次",
            ("4. 学生登录后 POST /api/v1/attendance-tasks/{task_id}/check-ins body={\"code\":\"123456\"} 返回 201；"
            "start_at~late_at 记为 present，late_at~end_at 记为 late"),
            "5. 重复点到不重复插记录，直接返回已有记录；码错误 422 INVALID_ATTENDANCE_CODE，窗口外 409 STATE_CONFLICT",
            ("6. POST /api/v1/attendance-tasks/{task_id}/close 返回 counts{present,late,leave,absent}，"
            "未签到者自动补记 absent"),
            "7. POST /api/v1/attendance-tasks/{task_id}/rotate-code 换新码，旧码立即失效，便于连续打多轮",
            "8. 明细统计：GET /api/v1/courses/{course_id}/attendance-records?task_id= 分页读取",
        ],
    },
]

PARAM = re.compile(r"<(?:[a-z]+:)?([A-Za-z_][A-Za-z0-9_]*)>")


def _path(rule):
    """把 /x/<int:id> 转成 /x/{id}，方便互测方直接拼 URL。"""
    return PARAM.sub(r"{\1}", rule.rule)


def _endpoints():
    items = []
    for rule in current_app.url_map.iter_rules():
        methods = sorted(rule.methods - {"HEAD", "OPTIONS"})
        if not methods or rule.endpoint == "static":
            continue
        module = rule.endpoint.rsplit(".", 1)[0] if "." in rule.endpoint else "app"
        spec, name = MODULES.get(module, (None, module))
        items.append({
            "module": module,
            "spec": spec,
            "module_name": name,
            "method": "/".join(methods),
            "path": _path(rule),
            "public": rule.rule in PUBLIC_PATHS,
        })
    items.sort(key=lambda item: (item["module"], item["path"], item["method"]))
    return items


def _groups(endpoints):
    grouped = {}
    for item in endpoints:
        grouped.setdefault(item["module"], []).append({"method": item["method"], "path": item["path"]})
    rows = []
    for module, module_endpoints in grouped.items():
        spec, name = MODULES.get(module, (None, module))
        rows.append({"spec": spec, "name": name, "blueprint": module, "endpoints": module_endpoints})
    rows.sort(key=lambda row: (row["spec"] or "zzz", row["name"]))
    return rows


@bp.get("/help")
def help_document():
    """公开：接口清单与接入说明。"""
    endpoints = _endpoints()
    return readable({
        "service": {
            "name": group.PROJECT,
            "class_name": group.CLASS_NAME,
            "group_no": group.GROUP_NO,
            "group_name": group.GROUP_NAME,
            "api_base": "/api/v1",
        },
        "response_format": {
            "success": {"data": "业务数据", "request_id": "本次请求 id"},
            "paged": {"data": "列表", "page": "页码", "page_size": "每页条数",
                      "total": "总数", "request_id": "本次请求 id"},
            "error": {"error": {"code": "错误码", "message": "描述", "details": "细节"},
                      "request_id": "本次请求 id"},
            "time_format": "UTC ISO 8601，例如 2026-11-01T06:10:28.000Z",
        },
        "accounts": dict(group.ACCOUNT_RULES),
        "public_endpoints": sorted(PUBLIC_PATHS),
        "guides": GUIDES,
        "modules": _groups(endpoints),
        "counts": {"endpoints": len(endpoints),
                   "modules": len({item["module"] for item in endpoints})},
    })


@bp.get("/who")
def who():
    """公开：本组信息。"""
    return readable(group.payload())
