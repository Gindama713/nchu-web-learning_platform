"""SPEC-017 实验箱连线 HTTP 适配器。

实验与版本定义由 SPEC-009 管理，本模块只处理连线 attempt。
"""

import hashlib
import json

from flask import Blueprint, request

from backend.engines import wiring
from backend.shared.api import (
    ApiError,
    audit,
    body,
    non_negative_int,
    now,
    page_args,
    paged,
    parse_time,
    positive_int,
    result,
    stamp,
)
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db, write

bp = Blueprint("wiring", __name__)

MAX_ACTIONS_PER_SAVE = 500
MAX_ACTIONS_TOTAL = 10000
VALIDATOR_VERSION = "wiring-struct-v1"
# 动作重放（engines.wiring.replay / _apply_edit）会直接读这些键。缺失时不能等
# 引擎 KeyError 冒泡成 500（RE-001），也不能让引擎跳过、动作照常入库造成
# 动作表与状态永久不一致，因此在重放前统一挡成 400。
ACTION_REQUIRED_FIELDS = {
    "connect": ("id", "from_terminal", "to_terminal"),
    "disconnect": ("wire_id",),
    "set_input": ("terminal_id", "value"),
}
VALID_ACTION_TYPES = frozenset(ACTION_REQUIRED_FIELDS) | {"step", "reset", "undo", "redo"}
# _row 用 f-string 拼表名，只接受本模块内联调用的固定白名单，防止后续传入外部值。
_ROW_TABLES = frozenset({"experiment", "experiment_version"})


def _row(db, table, rid):
    if table not in _ROW_TABLES:
        raise ValueError(f"unsupported table: {table}")
    return db.execute(f"SELECT * FROM {table} WHERE id=?", (rid,)).fetchone()


def _parse_json(text, field):
    if text is None:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        raise ApiError(500, "INTERNAL_ERROR", f"invalid {field}")


# ---------- 连线 attempt 接口 ----------

def _attempt_row(db, aid):
    return db.execute("SELECT * FROM wiring_attempt WHERE id=?", (aid,)).fetchone()


def _student_version(db, version_id, student_id, *, require_window=False):
    version = _row(db, "experiment_version", version_id)
    if not version:
        raise ApiError(404, "NOT_FOUND", "Experiment version not found")
    experiment = _row(db, "experiment", version["experiment_id"])
    course_access(experiment["course_id"])
    participant = db.execute(
        "SELECT 1 FROM experiment_participant WHERE experiment_version_id=? AND student_id=?",
        (version_id, student_id)).fetchone()
    if not participant:
        raise ApiError(404, "NOT_FOUND", "Experiment version not found")
    if "wiring" not in _parse_json(version["submission_modes_json"], "submission_modes"):
        raise ApiError(409, "STATE_CONFLICT", "Wiring is not enabled for this version")
    if require_window and (version["status"] != "published" or not
                           (parse_time(version["start_at"], "start_at") <= now()
                            < parse_time(version["end_at"], "end_at"))):
        raise ApiError(409, "WINDOW_CLOSED", "Experiment is outside its submission window")
    return version


def _action_counts(db, ids):
    """一次聚合查询取出多个 attempt 的动作数，避免列表接口逐行 COUNT(*) 的 N+1。"""
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    rows = db.execute(
        f"SELECT attempt_id,COUNT(*) AS n FROM wiring_action WHERE attempt_id IN ({marks}) "
        "GROUP BY attempt_id", tuple(ids))
    return {r["attempt_id"]: r["n"] for r in rows}


def _serialize_attempt(db, row, include_state=True, action_counts=None):
    state = _parse_json(row["state_json"], "state") if include_state else None
    item = {
        "id": row["id"], "experiment_version_id": row["experiment_version_id"],
        "student_id": row["student_id"], "revision": row["revision"],
        "status": row["status"], "state": state,
        "latest_seq": row["latest_seq"], "snapshot_hash": row["snapshot_hash"],
        "submitted_at": row["submitted_at"], "completed": bool(row["completed"]),
        "functional_results": _parse_json(row["functional_results_json"], "functional_results"),
        "saved_at": row["saved_at"], "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    item["action_count"] = (action_counts.get(row["id"], 0) if action_counts is not None else
                            db.execute("SELECT COUNT(*) FROM wiring_action WHERE attempt_id=?",
                                       (row["id"],)).fetchone()[0])
    return item


@bp.post("/experiment-versions/<int:version_id>/wiring-attempts")
def create_attempt(version_id):
    user = require_user()
    if user["role"] != "student":
        raise ApiError(403, "FORBIDDEN", "Only students can create wiring attempts")
    with write() as wdb:
        version = _student_version(wdb, version_id, user["id"], require_window=True)
        existing = wdb.execute(
            "SELECT * FROM wiring_attempt WHERE experiment_version_id=? AND student_id=? "
            "AND status='draft' ORDER BY id DESC LIMIT 1",
            (version_id, user["id"])).fetchone()
        if existing:
            return result(_serialize_attempt(wdb, existing))
        panel = _parse_json(version["panel_json"], "panel")
        state = wiring.initial_state(panel)
        timestamp = stamp()
        cursor = wdb.execute(
            "INSERT INTO wiring_attempt(experiment_version_id,student_id,revision,status,state_json,"
            "latest_seq,completed,created_at,updated_at) VALUES(?,?,0,'draft',?,0,0,?,?)",
            (version_id, user["id"], json.dumps(state, ensure_ascii=False),
             timestamp, timestamp))
        aid = cursor.lastrowid
        audit("wiring_attempt.create", "wiring_attempt", aid,
              after={"experiment_version_id": version_id})
        row = _attempt_row(wdb, aid)
    return result(_serialize_attempt(wdb, row), 201)


@bp.get("/wiring-attempts/<int:aid>")
def get_attempt(aid):
    user = require_user()
    db = get_db()
    row = _attempt_row(db, aid)
    if not row:
        raise ApiError(404, "NOT_FOUND", "Wiring attempt not found")
    exp = db.execute(
        "SELECT e.course_id FROM experiment_version v JOIN experiment e ON e.id=v.experiment_id "
        "WHERE v.id=?", (row["experiment_version_id"],)).fetchone()
    _, role = course_access(exp["course_id"])
    if role != "teacher" and row["student_id"] != user["id"]:
        raise ApiError(404, "NOT_FOUND", "Wiring attempt not found")
    return result(_serialize_attempt(db, row))


@bp.put("/wiring-attempts/<int:aid>")
def save_attempt(aid):
    user = require_user()
    data = body(("revision", "state", "actions"))
    revision = data["revision"]
    state = data["state"]
    actions = data["actions"]
    if not isinstance(state, dict):
        raise ApiError(400, "VALIDATION_ERROR", "state must be an object")
    if not isinstance(actions, list):
        raise ApiError(400, "VALIDATION_ERROR", "actions must be a list")
    if len(actions) > MAX_ACTIONS_PER_SAVE:
        raise ApiError(400, "VALIDATION_ERROR", f"too many actions (max {MAX_ACTIONS_PER_SAVE})")
    for act in actions:
        if not isinstance(act, dict) or not isinstance(act.get("type"), str):
            raise ApiError(400, "VALIDATION_ERROR", "each action requires a string type")
        if act["type"] not in VALID_ACTION_TYPES:
            # 数据库 017_wiring.sql 对 type 有 CHECK 约束；在此挡成 400 而不是
            # 让 IntegrityError 变成含义不明的 409 DATA_CONFLICT。
            raise ApiError(400, "VALIDATION_ERROR", f"unknown action type: {act['type']}")
        payload = act.get("payload", {})
        if not isinstance(payload, dict):
            raise ApiError(400, "VALIDATION_ERROR", "action payload must be an object")
        for field in ACTION_REQUIRED_FIELDS.get(act["type"], ()):
            if field not in payload:
                raise ApiError(400, "VALIDATION_ERROR", f"{act['type']} payload missing {field}")
            if field != "value" and (not isinstance(payload[field], str) or not payload[field]):
                raise ApiError(400, "VALIDATION_ERROR",
                               f"{act['type']} payload field {field} must be a non-empty string")
        if act["type"] == "set_input":
            # 非整数值会在 _propagate 的位运算里抛出 500；布尔值是 int 子类，单独排除。
            value = payload["value"]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ApiError(400, "VALIDATION_ERROR", "set_input value must be an integer")
    with write() as db:
        row = _attempt_row(db, aid)
        if not row:
            raise ApiError(404, "NOT_FOUND", "Wiring attempt not found")
        if row["student_id"] != user["id"]:
            raise ApiError(403, "FORBIDDEN", "Not your attempt")
        _student_version(db, row["experiment_version_id"], user["id"])
        if row["status"] != "draft":
            raise ApiError(409, "STATE_CONFLICT", "Submitted attempt cannot be edited")
        if row["revision"] != revision:
            raise ApiError(409, "REVISION_CONFLICT", "stale revision",
                           {"current": row["revision"], "provided": revision})
        ver = _row(db, "experiment_version", row["experiment_version_id"])
        panel = _parse_json(ver["panel_json"], "panel")
        # 服务端重放校验
        all_actions = db.execute(
            "SELECT seq,type,payload_json FROM wiring_action WHERE attempt_id=? ORDER BY seq", (aid,)).fetchall()
        replayed = wiring.replay(panel, [{"type": r["type"], "payload": _parse_json(r["payload_json"], "payload")}
                                         for r in all_actions])
        # 追加本次动作一次性重放：undo/redo 依赖同一批内的操作栈，逐条重放会丢失语义
        replayed = wiring.replay(panel, actions, base_state=replayed)
        # 比较关键字段
        if replayed.get("wires", []) != state.get("wires", []):
            raise ApiError(422, "STATE_MISMATCH", "server replay wires differ from client state")
        if replayed.get("inputs", {}) != state.get("inputs", {}):
            raise ApiError(422, "STATE_MISMATCH", "server replay inputs differ from client state")

        # 先整体预检，避免写完一半动作才抛错（虽会回滚，但错误语义与耗时都不好）。
        if row["latest_seq"] + len(actions) > MAX_ACTIONS_TOTAL:
            raise ApiError(400, "VALIDATION_ERROR", f"max actions exceeded ({MAX_ACTIONS_TOTAL})")
        new_seq = row["latest_seq"]
        for act in actions:
            new_seq += 1
            db.execute(
                "INSERT INTO wiring_action(attempt_id,seq,type,payload_json,client_at,received_at) "
                "VALUES(?,?,?,?,?,?)",
                (aid, new_seq, act["type"], json.dumps(act.get("payload", {}), ensure_ascii=False),
                 act.get("client_at"), stamp()))
        new_revision = revision + 1
        now = stamp()
        # 客户端 state 只作为 wires/inputs 的比对输入；运行时字段（tick/phase/
        # 寄存器/标志位）一律以服务端重放结果为准，submit 的功能判定与
        # snapshot_hash 因此不再受客户端伪造值影响（设计报告 §5.2）。
        db.execute(
            "UPDATE wiring_attempt SET revision=?,state_json=?,latest_seq=?,saved_at=?,updated_at=? WHERE id=?",
            (new_revision, json.dumps(replayed, ensure_ascii=False), new_seq, now, now, aid))
        row = _attempt_row(db, aid)
        audit("wiring_attempt.save", "wiring_attempt", aid,
              after={"revision": new_revision, "latest_seq": new_seq})
    return result({"id": aid, "revision": new_revision, "latest_seq": new_seq, "saved_at": now})


@bp.post("/wiring-attempts/<int:aid>/validate")
def validate_attempt(aid):
    user = require_user()
    data = body(("revision",))
    revision = data["revision"]
    with write() as db:
        row = _attempt_row(db, aid)
        if not row:
            raise ApiError(404, "NOT_FOUND", "Wiring attempt not found")
        if row["student_id"] != user["id"]:
            raise ApiError(403, "FORBIDDEN", "Not your attempt")
        _student_version(db, row["experiment_version_id"], user["id"])
        if row["status"] != "draft":
            raise ApiError(409, "STATE_CONFLICT", "Submitted attempt cannot be validated")
        if row["revision"] != revision:
            raise ApiError(409, "REVISION_CONFLICT", "stale revision")
        ver = _row(db, "experiment_version", row["experiment_version_id"])
        panel = _parse_json(ver["panel_json"], "panel")
        state = _parse_json(row["state_json"], "state")
        valid, errors = wiring.validate_structure(panel, state)
        db.execute(
            "INSERT INTO wiring_validation(attempt_id,revision,valid,errors_json,validator_version,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (aid, revision, 1 if valid else 0, json.dumps(errors, ensure_ascii=False),
             VALIDATOR_VERSION, stamp()))
        return result({"valid": valid, "errors": errors, "revision": revision})


@bp.post("/wiring-attempts/<int:aid>/submit")
def submit_attempt(aid):
    user = require_user()
    data = body(("revision",))
    revision = data["revision"]
    with write() as db:
        row = _attempt_row(db, aid)
        if not row:
            raise ApiError(404, "NOT_FOUND", "Wiring attempt not found")
        if row["student_id"] != user["id"]:
            raise ApiError(403, "FORBIDDEN", "Not your attempt")
        _student_version(db, row["experiment_version_id"], user["id"])
        if row["status"] == "submitted":
            return result(_serialize_attempt(db, row))
        _student_version(db, row["experiment_version_id"], user["id"], require_window=True)
        if row["revision"] != revision:
            raise ApiError(409, "REVISION_CONFLICT", "stale revision")
        ver = _row(db, "experiment_version", row["experiment_version_id"])
        panel = _parse_json(ver["panel_json"], "panel")
        state = _parse_json(row["state_json"], "state")
        valid, errors = wiring.validate_structure(panel, state)
        if not valid:
            raise ApiError(422, "STRUCTURE_INVALID", "wiring structure has errors", {"errors": errors})
        passed, results = wiring.run_functional_tests(panel, state)
        snapshot = json.dumps(state, ensure_ascii=False, sort_keys=True)
        snapshot_hash = hashlib.sha256(snapshot.encode()).hexdigest()
        now = stamp()
        db.execute(
            "UPDATE wiring_attempt SET status='submitted',snapshot_hash=?,submitted_at=?,completed=?,"
            "functional_results_json=?,updated_at=? WHERE id=?",
            (snapshot_hash, now, 1 if passed else 0,
             json.dumps(results, ensure_ascii=False), now, aid))
        row = _attempt_row(db, aid)
        audit("wiring_attempt.submit", "wiring_attempt", aid,
              after={"completed": passed, "snapshot_hash": snapshot_hash})
    item = _serialize_attempt(db, row)
    return result({
        "id": item["id"], "status": item["status"],
        "snapshot_hash": item["snapshot_hash"], "submitted_at": item["submitted_at"],
        "validation": {"valid": True, "errors": []},
        "completed": item["completed"], "functional_results": item["functional_results"],
    })


@bp.get("/wiring-attempts/<int:aid>/actions")
def list_actions(aid):
    user = require_user()
    page, size = page_args()
    after_seq = request.args.get("after_seq")
    db = get_db()
    row = _attempt_row(db, aid)
    if not row:
        raise ApiError(404, "NOT_FOUND", "Wiring attempt not found")
    if row["student_id"] != user["id"]:
        exp = db.execute(
            "SELECT e.course_id FROM experiment_version v JOIN experiment e ON e.id=v.experiment_id "
            "WHERE v.id=?", (row["experiment_version_id"],)).fetchone()
        _, role = course_access(exp["course_id"])
        if role != "teacher":
            raise ApiError(404, "NOT_FOUND", "Wiring attempt not found")
    where = ["attempt_id=?"]
    params = [aid]
    if after_seq is not None:
        where.append("seq>?")
        # 0 表示从头拉取（seq 从 1 开始），与前端 wiring-client 的默认参数一致。
        params.append(non_negative_int(after_seq, "after_seq"))
    where_sql = " WHERE " + " AND ".join(where)
    total = db.execute("SELECT COUNT(*) FROM wiring_action" + where_sql, params).fetchone()[0]
    rows = db.execute(
        "SELECT * FROM wiring_action" + where_sql + " ORDER BY seq LIMIT ? OFFSET ?",
        (*params, size, (page - 1) * size)).fetchall()
    items = [{"seq": r["seq"], "type": r["type"],
              "payload": _parse_json(r["payload_json"], "payload"), "client_at": r["client_at"]}
             for r in rows]
    latest = db.execute("SELECT MAX(seq) FROM wiring_action WHERE attempt_id=?", (aid,)).fetchone()[0] or 0
    next_after = items[-1]["seq"] if items else None
    return result({"items": items, "latest_seq": latest, "next_after_seq": next_after,
                   "page": page, "page_size": size, "total": total})


@bp.get("/courses/<int:course_id>/wiring-attempts")
def list_attempts(course_id):
    user = require_user()
    _, role = course_access(course_id)
    page, size = page_args()
    db = get_db()
    where = ("SELECT wa.* FROM wiring_attempt wa "
             "JOIN experiment_version v ON v.id=wa.experiment_version_id "
             "JOIN experiment e ON e.id=v.experiment_id WHERE e.course_id=?")
    params = [course_id]
    exp_ver = request.args.get("experiment_version_id")
    if exp_ver is not None:
        where += " AND wa.experiment_version_id=?"
        params.append(positive_int(exp_ver, "experiment_version_id"))
    if role == "student":
        where += " AND wa.student_id=?"
        params.append(user["id"])
    else:
        sid = request.args.get("student_id")
        if sid is not None:
            where += " AND wa.student_id=?"
            params.append(positive_int(sid, "student_id"))
    status = request.args.get("status")
    if status in ("draft", "submitted"):
        where += " AND wa.status=?"
        params.append(status)
    count_sql = where.replace("SELECT wa.*", "SELECT COUNT(*)")
    total = db.execute(count_sql, params).fetchone()[0]
    rows = db.execute(where + " ORDER BY wa.id DESC LIMIT ? OFFSET ?",
                      (*params, size, (page - 1) * size)).fetchall()
    counts = _action_counts(db, [r["id"] for r in rows])
    items = [_serialize_attempt(db, r, action_counts=counts) for r in rows]
    return paged(items, total, page, size)
