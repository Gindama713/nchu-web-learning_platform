"""SPEC-001 日志：访问日志写入与导出（CSV / JSON）。

任务书要求访问日志能说明「具体用户在何时访问了哪个模块、页面或 API」，
并能导出成 CSV 或 JSON。audit_event 记录的是关键操作的输入与结果，
这里补的是每次请求的访问轨迹。
"""

import atexit
import csv
import io
import sqlite3
import threading
import time

from flask import Blueprint, Response, current_app, g, request

from backend.shared.api import ApiError, date_range, page_args, paged, result, stamp
from backend.shared.auth import require_user
from backend.shared.db import get_db

bp = Blueprint("logs", __name__)

# 导出接口自身不记访问日志，否则导出动作会把日志越写越多
SKIP_PREFIX = ("/api/v1/logs/",)

# 访问日志原来每个请求 INSERT 一次并 commit，等于把只读请求也变成写请求：
# 每个请求多一次 fsync，并发时这些写事务互相排队，读请求被拖到秒级
# （实测 6 读 + 2 写下 p95 约 7 秒、5% 请求拿到 503 DB_BUSY）。
# 改成先攒在内存里，够一批或隔一段时间再一次性落库，写次数降到 1/20。
ACCESS_FLUSH_ROWS = 20
ACCESS_FLUSH_SECONDS = 2.0

INSERT_ACCESS = ("INSERT INTO access_log(user_id,student_no,name,role,method,path,status,ip,"
                 "duration_ms,at) VALUES(?,?,?,?,?,?,?,?,?,?)")

_pending = []
_pending_lock = threading.Lock()
_last_flush = 0.0
_database_path = None


def flush_access(force=False):
    """把攒下的访问记录一次性写库；失败只记 debug，绝不反压业务请求。"""
    global _last_flush
    with _pending_lock:
        if not _pending:
            return
        if not force and len(_pending) < ACCESS_FLUSH_ROWS and \
                (time.monotonic() - _last_flush) < ACCESS_FLUSH_SECONDS:
            return
        rows = _pending[:]
        _pending.clear()
        _last_flush = time.monotonic()
    try:
        db = get_db()
        db.executemany(INSERT_ACCESS, rows)
        db.commit()
    except Exception as failure:  # noqa: BLE001 — 日志失败绝不能把业务请求带崩
        current_app.logger.debug("access log flush failed: %s", failure)
        try:
            get_db().rollback()
        except Exception:  # noqa: BLE001
            pass


def _flush_at_exit():
    """进程正常退出时把没落库的尾部记录补上；用的是独立连接，此时没有请求上下文。"""
    with _pending_lock:
        rows = _pending[:]
        _pending.clear()
    if not rows or not _database_path:
        return
    try:
        db = sqlite3.connect(_database_path, timeout=5)
        db.executemany(INSERT_ACCESS, rows)
        db.commit()
        db.close()
    except Exception:  # noqa: BLE001
        pass


atexit.register(_flush_at_exit)


def should_log(path):
    if not (path.startswith("/api/v1/") or path in ("/help", "/who")):
        return False
    return not path.startswith(SKIP_PREFIX)


def write_access(status, duration_ms):
    """在 after_request 里记一条访问轨迹；任何异常都不能影响正常响应。"""
    global _database_path
    path = request.path
    if not should_log(path):
        return
    user = getattr(g, "user", None) or {}
    try:
        _database_path = current_app.config["DATABASE_PATH"]
    except Exception:  # noqa: BLE001
        pass
    with _pending_lock:
        _pending.append((user.get("id"), user.get("student_no"), user.get("name"), user.get("role"),
                         request.method, path, status,
                         request.headers.get("X-Forwarded-For", request.remote_addr),
                         round(duration_ms, 1), stamp()))
    flush_access()


def _filtered():
    """教师与管理员可看日志；按时间与用户筛选。"""
    user = require_user()
    if user["role"] not in ("teacher", "admin"):
        raise ApiError(403, "FORBIDDEN", "Teacher or administrator required")
    # 导出前先把内存里还没落库的记录刷进去，否则刚发生的访问查不到
    flush_access(force=True)
    start, end = date_range()
    conditions, params = ["at>=?", "at<=?"], [start, end]
    number = request.args.get("student_no", "").strip()
    if number:
        conditions.append("student_no=?")
        params.append(number)
    if request.args.get("path"):
        conditions.append("path LIKE ?")
        params.append(request.args["path"].strip()[:100] + "%")
    return " WHERE " + " AND ".join(conditions), params


@bp.get("/logs/access")
def access_logs():
    where, params = _filtered()
    page, size = page_args()
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM access_log" + where, params).fetchone()[0]
    rows = db.execute("SELECT * FROM access_log" + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
                      (*params, size, (page - 1) * size)).fetchall()
    return paged([{key: row[key] for key in
                   ("id", "student_no", "name", "role", "method", "path", "status", "ip",
                    "duration_ms", "at")} for row in rows], total, page, size)


@bp.get("/logs/access.csv")
def access_csv():
    where, params = _filtered()
    rows = get_db().execute("SELECT * FROM access_log" + where + " ORDER BY id", params).fetchall()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["时间", "学号", "姓名", "角色", "方法", "路径", "状态", "IP", "耗时毫秒"])
    for row in rows:
        writer.writerow([row["at"], row["student_no"] or "", row["name"] or "", row["role"] or "",
                         row["method"], row["path"], row["status"], row["ip"] or "",
                         row["duration_ms"]])
    text = buffer.getvalue()
    return Response("\ufeff" + text, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="week10-server-log.csv"'})


@bp.get("/logs/audit.csv")
def audit_csv():
    """关键操作审计导出：谁做了什么、输入与结果。"""
    user = require_user()
    if user["role"] not in ("teacher", "admin"):
        raise ApiError(403, "FORBIDDEN", "Teacher or administrator required")
    start, end = date_range()
    rows = get_db().execute(
        "SELECT a.*,u.student_no,u.name FROM audit_event a LEFT JOIN user u ON u.id=a.actor_id "
        "WHERE a.created_at>=? AND a.created_at<=? ORDER BY a.id", (start, end)).fetchall()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["时间", "学号", "姓名", "动作", "对象类型", "对象ID", "变更前", "变更后", "请求ID"])
    for row in rows:
        writer.writerow([row["created_at"], row["student_no"] or "", row["name"] or "",
                         row["action"], row["object_type"], row["object_id"] or "",
                         row["before_summary"] or "", row["after_summary"] or "", row["request_id"] or ""])
    return Response("\ufeff" + buffer.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="week10-server-audit.csv"'})


@bp.get("/logs/summary")
def logs_summary():
    user = require_user()
    if user["role"] not in ("teacher", "admin"):
        raise ApiError(403, "FORBIDDEN", "Teacher or administrator required")
    start, end = date_range()
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM access_log WHERE at>=? AND at<=?", (start, end)).fetchone()[0]
    people = db.execute("SELECT COUNT(DISTINCT user_id) FROM access_log WHERE at>=? AND at<=? "
                        "AND user_id IS NOT NULL", (start, end)).fetchone()[0]
    failed = db.execute("SELECT COUNT(*) FROM access_log WHERE at>=? AND at<=? AND status>=400",
                        (start, end)).fetchone()[0]
    rows = db.execute("SELECT path,COUNT(*) n FROM access_log WHERE at>=? AND at<=? "
                      "GROUP BY path ORDER BY n DESC LIMIT 10", (start, end)).fetchall()
    return result({"from": start, "to": end, "requests": total, "users": people,
                   "failed": failed, "top_paths": [{"path": row["path"], "count": row["n"]} for row in rows]})
