"""SPEC-001 identity and administrator endpoints."""

import hashlib
import re
import secrets
import sqlite3
from datetime import timedelta

from flask import Blueprint, current_app, g, make_response, request
from werkzeug.security import check_password_hash, generate_password_hash

from backend.shared.api import (
    ApiError,
    audit,
    body,
    now,
    page_args,
    paged,
    rate_limit,
    result,
    stamp,
    text_field,
)
from backend.shared.auth import (
    COOKIE,
    csrf_for,
    require_admin,
    require_user,
)
from backend.shared.db import get_db, write

bp = Blueprint("identity", __name__)
DUMMY_HASH = generate_password_hash("not-a-real-account-password")


def public_user(row):
    return {key: row[key] for key in ("id", "student_no", "name", "role", "active")}


def student_no(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9]{8,20}", value):
        raise ApiError(400, "VALIDATION_ERROR", "学号必须是 8–20 位字母或数字")
    return value


def password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise ApiError(400, "VALIDATION_ERROR", "password must be 12–128 characters")
    return value


@bp.post("/auth/register")
def register():
    data = body(("student_no", "name", "password"))
    number = student_no(data["student_no"])
    name = text_field(data["name"], "name", maximum=50)
    hashed = generate_password_hash(password(data["password"]))
    timestamp = stamp()
    try:
        with write() as db:
            cursor = db.execute(
                "INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                "VALUES(?,?,?,'student',1,?,?)", (number, name, hashed, timestamp, timestamp),
            )
            user = db.execute("SELECT * FROM user WHERE id=?", (cursor.lastrowid,)).fetchone()
            audit("user.register", "user", user["id"], after={"role": "student"}, actor_id=user["id"])
    except sqlite3.IntegrityError as exc:
        raise ApiError(409, "DUPLICATE", "该学号已注册") from exc
    return result({"user": public_user(user)}, 201)


@bp.post("/auth/login")
def login():
    data = body(("student_no", "password"))
    number = student_no(data["student_no"])
    supplied = data["password"] if isinstance(data["password"], str) else ""
    with write():
        rate_limit(f"login:ip:{request.remote_addr}", 20)
        rate_limit(f"login:account:{number.lower()}", 5)
    user = get_db().execute("SELECT * FROM user WHERE student_no=?", (number,)).fetchone()
    valid = check_password_hash(user["password_hash"] if user else DUMMY_HASH, supplied)
    if not user or not user["active"] or not valid:
        raise ApiError(401, "UNAUTHENTICATED", "学号或密码不正确")
    with write() as db:
        token = secrets.token_urlsafe(32)
        csrf = csrf_for(token)
        timestamp = stamp()
        expires = stamp(now() + timedelta(hours=2))
        db.execute("INSERT INTO session(token_hash,user_id,csrf_hash,session_version,"
                   "expires_at,last_seen_at,created_at) VALUES(?,?,?,?,?,?,?)",
                   (hashlib.sha256(token.encode()).hexdigest(), user["id"],
                    hashlib.sha256(csrf.encode()).hexdigest(), user["session_version"],
                    expires, timestamp, timestamp))
        audit("auth.login", "user", user["id"], actor_id=user["id"])
    response = make_response(result({"user": public_user(user), "csrf_token": csrf})[0])
    response.set_cookie(COOKIE, token, httponly=True, secure=current_app.config["COOKIE_SECURE"],
                        samesite="Lax", path="/", max_age=7200)
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/auth/session")
def session_info():
    user = require_user()
    expires = get_db().execute("SELECT expires_at FROM session WHERE id=?", (g.session_id,)).fetchone()[0]
    response = make_response(result({"user": user, "csrf_token": csrf_for(g.session_token),
                                     "expires_at": expires})[0])
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.post("/auth/logout")
def logout():
    user = require_user()
    with write() as db:
        db.execute("DELETE FROM session WHERE id=?", (g.session_id,))
        audit("auth.logout", "user", user["id"])
    response = make_response("", 204)
    g.logged_out = True
    response.delete_cookie(COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.patch("/users/me")
def update_me():
    user = require_user()
    data = body(allowed=("name", "old_password", "new_password"))
    if not data or ("old_password" in data) != ("new_password" in data):
        raise ApiError(400, "VALIDATION_ERROR", "name or both password fields required")
    name = text_field(data["name"], "name", maximum=50) if "name" in data else user["name"]
    with write() as db:
        row = db.execute("SELECT * FROM user WHERE id=?", (user["id"],)).fetchone()
        hashed = row["password_hash"]
        changed = "new_password" in data
        if changed:
            if not isinstance(data["old_password"], str) or not check_password_hash(hashed, data["old_password"]):
                raise ApiError(403, "FORBIDDEN", "Old password is invalid")
            hashed = generate_password_hash(password(data["new_password"]))
        db.execute("UPDATE user SET name=?,password_hash=?,session_version=session_version+?,"
                   "updated_at=? WHERE id=?", (name, hashed, int(changed), stamp(), user["id"]))
        if changed:
            db.execute("DELETE FROM session WHERE user_id=? AND id<>?", (user["id"], g.session_id))
            db.execute("UPDATE session SET session_version=session_version+1 WHERE id=?", (g.session_id,))
        audit("user.update_self", "user", user["id"], before={"name": row["name"]},
              after={"name": name, "password_changed": changed})
        updated = db.execute("SELECT * FROM user WHERE id=?", (user["id"],)).fetchone()
    return result(public_user(updated))


@bp.get("/users")
def users():
    require_admin()
    role = request.args.get("role")
    if role and role not in ("student", "teacher", "admin"):
        raise ApiError(400, "VALIDATION_ERROR", "Invalid role")
    query = request.args.get("q", "").strip()
    if len(query) > 100:
        raise ApiError(400, "VALIDATION_ERROR", "q too long")
    page, size = page_args()
    conditions, params = [], []
    if role:
        conditions.append("role=?")
        params.append(role)
    if query:
        conditions.append("(student_no LIKE ? OR name LIKE ?)")
        params += [f"%{query}%", f"%{query}%"]
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM user" + where, params).fetchone()[0]
    rows = db.execute("SELECT * FROM user" + where + " ORDER BY id LIMIT ? OFFSET ?",
                      (*params, size, (page - 1) * size)).fetchall()
    return paged([public_user(row) for row in rows], total, page, size)


@bp.patch("/users/<int:user_id>")
def update_user(user_id):
    actor = require_admin()
    data = body(allowed=("role", "active"))
    if not data:
        raise ApiError(400, "VALIDATION_ERROR", "role or active required")
    role = data.get("role")
    if role is not None and role not in ("student", "teacher", "admin"):
        raise ApiError(400, "VALIDATION_ERROR", "Invalid role")
    if "active" in data and not isinstance(data["active"], bool):
        raise ApiError(400, "VALIDATION_ERROR", "active must be boolean")
    with write() as db:
        row = db.execute("SELECT * FROM user WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise ApiError(404, "NOT_FOUND", "User not found")
        new_role, active = role or row["role"], int(data.get("active", bool(row["active"])))
        if row["role"] == "admin" and row["active"] and (new_role != "admin" or not active):
            count = db.execute("SELECT COUNT(*) FROM user WHERE role='admin' AND active=1").fetchone()[0]
            if count <= 1:
                raise ApiError(409, "STATE_CONFLICT", "At least one active administrator is required")
        if row["role"] == "teacher" and (new_role != "teacher" or not active):
            count = db.execute("SELECT COUNT(*) FROM course WHERE teacher_id=?", (user_id,)).fetchone()[0]
            if count:
                raise ApiError(409, "STATE_CONFLICT", "Transfer responsible courses first")
        db.execute("UPDATE user SET role=?,active=?,session_version=session_version+1,updated_at=? WHERE id=?",
                   (new_role, active, stamp(), user_id))
        db.execute("UPDATE course_member SET active=0,updated_at=? WHERE user_id=? "
                   "AND (member_role<>? OR ?=0)", (stamp(), user_id, new_role, active))
        audit("user.admin_update", "user", user_id,
              before={"role": row["role"], "active": bool(row["active"])},
              after={"role": new_role, "active": bool(active)}, actor_id=actor["id"])
        updated = db.execute("SELECT * FROM user WHERE id=?", (user_id,)).fetchone()
    return result(public_user(updated))


@bp.get("/users/lookup")
def lookup():
    user = require_user()
    if user["role"] not in ("teacher", "admin"):
        raise ApiError(403, "FORBIDDEN", "Teacher or administrator required")
    number = student_no(request.args.get("student_no"))
    with write() as db:
        rate_limit(f"lookup:{user['id']}", 20)
        row = db.execute("SELECT * FROM user WHERE student_no=?", (number,)).fetchone()
        audit("user.lookup", "user", row["id"] if row else None, after={"found": bool(row)})
    if not row:
        raise ApiError(404, "NOT_FOUND", "User not found")
    return result(public_user(row))
