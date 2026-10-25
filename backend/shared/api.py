"""Shared REST boundary: validation, time, responses and audit."""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from flask import current_app, g, jsonify, request

from backend.shared.db import get_db


class ApiError(Exception):
    def __init__(self, status, code, message, details=None):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.details = details or {}


def request_id():
    if "request_id" not in g:
        g.request_id = uuid4().hex
    return g.request_id


def result(data, status=200, **extra):
    return jsonify(data=data, request_id=request_id(), **extra), status


def paged(items, total, page, page_size, **extra):
    return jsonify(data=items, page=page, page_size=page_size, total=total,
                   request_id=request_id(), **extra)


def page_args():
    page = positive_int(request.args.get("page", "1"), "page")
    size = positive_int(request.args.get("page_size", "20"), "page_size")
    if size > 100:
        raise ApiError(400, "VALIDATION_ERROR", "page_size must be at most 100")
    return page, size


def positive_int(value, field):
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]*", str(value)):
        raise ApiError(400, "VALIDATION_ERROR", f"{field} must be a positive integer")
    return int(value)


def non_negative_int(value, field):
    if isinstance(value, bool) or not re.fullmatch(r"0|[1-9][0-9]*", str(value)):
        raise ApiError(400, "VALIDATION_ERROR", f"{field} must be a non-negative integer")
    return int(value)


def body(required=(), allowed=()):
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ApiError(400, "VALIDATION_ERROR", "JSON object required")
    missing = set(required) - value.keys()
    unknown = value.keys() - set(required) - set(allowed)
    if missing or unknown:
        raise ApiError(400, "VALIDATION_ERROR", "Invalid request fields",
                       {"missing": sorted(missing), "unknown": sorted(unknown)})
    return value


def text_field(value, field, minimum=1, maximum=100):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ApiError(400, "VALIDATION_ERROR", f"{field} length is invalid")
    return value.strip()


def now():
    if current_app.testing and current_app.config.get("TEST_NOW"):
        return current_app.config["TEST_NOW"]
    return datetime.now(UTC)


def stamp(value=None):
    return (value or now()).astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_time(value, field):
    if not isinstance(value, str):
        raise ApiError(400, "VALIDATION_ERROR", f"{field} must be an ISO 8601 time")
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return parsed.astimezone(UTC)
    except ValueError as exc:
        raise ApiError(400, "VALIDATION_ERROR", f"{field} must include a timezone") from exc


def date_range():
    end = now()
    start = end - timedelta(days=28)
    if request.args.get("from"):
        start = parse_time(request.args["from"], "from")
    if request.args.get("to"):
        end = parse_time(request.args["to"], "to")
    if start > end or end > now() or end - start > timedelta(days=366):
        raise ApiError(400, "VALIDATION_ERROR", "Invalid date range")
    return stamp(start), stamp(end)


def audit(action, object_type, object_id, before=None, after=None, actor_id=None):
    get_db().execute(
        "INSERT INTO audit_event(actor_id,action,object_type,object_id,request_id,"
        "before_summary,after_summary,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (actor_id if actor_id is not None else getattr(g, "user", {}).get("id"),
         action, object_type, object_id, request_id(),
         json.dumps(before, ensure_ascii=False) if before is not None else None,
         json.dumps(after, ensure_ascii=False) if after is not None else None, stamp()),
    )


def notify(user_id, course_id, title, target_type, target_id, event_key):
    get_db().execute(
        "INSERT OR IGNORE INTO notification(user_id,course_id,title,target_type,target_id,"
        "event_key,created_at) VALUES(?,?,?,?,?,?,?)",
        (user_id, course_id, title, target_type, target_id, event_key, stamp()),
    )


def rate_limit(key, limit, minutes=1):
    db = get_db()
    hashed = hashlib.sha256(key.encode()).hexdigest()
    since = stamp(now() - timedelta(minutes=minutes))
    count = db.execute("SELECT COUNT(*) FROM rate_event WHERE key_hash=? AND at>=?", (hashed, since)).fetchone()[0]
    if count >= limit:
        raise ApiError(429, "RATE_LIMITED", "Too many requests")
    db.execute("INSERT INTO rate_event(key_hash,at) VALUES(?,?)", (hashed, stamp()))
