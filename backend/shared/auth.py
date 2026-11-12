"""Database-backed sessions and course membership checks."""

import hashlib
import hmac
import sqlite3
from datetime import datetime, timedelta

from flask import current_app, g, request

from backend.shared.api import ApiError, now, stamp
from backend.shared.db import get_db

COOKIE = "cpu_session"

# 会话有效期 2 小时，心跳没必要每个请求都续一次；60 秒一次足够让活跃会话不超时。
HEARTBEAT_SECONDS = 60


def csrf_for(token):
    return hmac.new(current_app.config["SECRET_KEY"].encode(), token.encode(), "sha256").hexdigest()


def _heartbeat_due(last_seen_at):
    """距上次续期是否已经超过阈值；时间串解析不了就当作需要续期。"""
    try:
        seen = datetime.fromisoformat(str(last_seen_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    return (now() - seen).total_seconds() >= HEARTBEAT_SECONDS


def session_user():
    if hasattr(g, "user"):
        return g.user
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = get_db().execute(
        "SELECT s.*,u.student_no,u.name,u.role,u.active,u.session_version AS current_version "
        "FROM session s JOIN user u ON u.id=s.user_id WHERE s.token_hash=?", (token_hash,),
    ).fetchone()
    if not row or not row["active"] or row["session_version"] != row["current_version"] or row["expires_at"] <= stamp():
        return None
    g.user = {"id": row["user_id"], "student_no": row["student_no"],
              "name": row["name"], "role": row["role"]}
    g.session_id, g.session_token, g.csrf_hash = row["id"], token, row["csrf_hash"]
    # 续期只在超过阈值时才写库。原来每个请求都 UPDATE 一次 session，等于把只读请求
    # 也变成写请求：多人同时刷新时所有连接抢同一把写锁，回滚日志模式下会直接
    # SQLITE_BUSY（表现为 503）。续期只是记「最近活跃」，失败不该带崩本次请求。
    if _heartbeat_due(row["last_seen_at"]):
        try:
            get_db().execute("UPDATE session SET last_seen_at=?,expires_at=? WHERE id=?",
                             (stamp(), stamp(now() + timedelta(hours=2)), row["id"]))
        except sqlite3.OperationalError:
            current_app.logger.warning("session heartbeat skipped: database busy")
    return g.user


def require_user():
    user = session_user()
    if not user:
        raise ApiError(401, "UNAUTHENTICATED", "Login required")
    current = get_db().execute("SELECT u.active,u.role,u.session_version,s.session_version AS saved_version "
                               "FROM session s JOIN user u ON u.id=s.user_id WHERE s.id=?",
                               (g.session_id,)).fetchone()
    if not current or not current["active"] or current["role"] != user["role"] or current["session_version"] != current["saved_version"]:
        raise ApiError(401, "UNAUTHENTICATED", "Session revoked")
    return user


def require_admin():
    user = require_user()
    if user["role"] != "admin":
        raise ApiError(403, "FORBIDDEN", "Administrator required")
    return user


def course_access(course_id, teacher=False, manager=False):
    user = require_user()
    course = get_db().execute("SELECT * FROM course WHERE id=?", (course_id,)).fetchone()
    if not course:
        raise ApiError(404, "NOT_FOUND", "Course not found")
    if user["role"] == "admin" and manager:
        return course, "admin"
    member = get_db().execute(
        "SELECT member_role FROM course_member WHERE course_id=? AND user_id=? AND active=1",
        (course_id, user["id"]),
    ).fetchone()
    if not member or member["member_role"] != user["role"]:
        raise ApiError(404, "NOT_FOUND", "Course not found")
    if teacher and member["member_role"] != "teacher":
        raise ApiError(403, "FORBIDDEN", "Course teacher required")
    return course, member["member_role"]


def check_csrf():
    require_user()
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not hmac.compare_digest(hashlib.sha256(supplied.encode()).hexdigest(), g.csrf_hash):
        raise ApiError(403, "CSRF_FAILED", "Invalid CSRF token")
