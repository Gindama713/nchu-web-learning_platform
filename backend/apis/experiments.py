"""SPEC-009 experiment guidance: experiments, immutable versions and publishing.

连线过程（wiring-attempts）属于 SPEC-017，测试集/判分配置管理属于 SPEC-018；
本模块只提供实验列表、指导内容、版本与发布，并为 circuit 版本派生 judge_profile_id。
"""

import hashlib
import json

from flask import Blueprint, request

from backend.shared.api import (
    ApiError,
    audit,
    body,
    notify,
    page_args,
    paged,
    parse_time,
    positive_int,
    result,
    stamp,
    text_field,
)
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db, write

bp = Blueprint("experiments", __name__)

CODES = ("EXP-01", "EXP-02", "EXP-03", "EXP-04")
MODES = ("wiring", "circuit")
# PRD 第5节：EXP-01/02 启用连线与 .circ，EXP-03 仅连线，EXP-04 仅 .circ。
CODE_MODES = {
    "EXP-01": frozenset(MODES),
    "EXP-02": frozenset(MODES),
    "EXP-03": frozenset({"wiring"}),
    "EXP-04": frozenset({"circuit"}),
}

# PRD 第6.1节固定面板元件：逻辑端口 -> (方向, 固定位宽或 params.width)。
# params.width 表示该端子位宽来自元件参数；禁止自定义脚本或表达式。
COMPONENT_PORTS = {
    "SWITCH": {"OUT": ("out", "params.width")},
    "CONST": {"OUT": ("out", "params.width")},
    "LED": {"IN": ("in", "params.width")},
    "ALU8": {"A": ("in", 8), "B": ("in", 8), "OP": ("in", 3),
             "Y": ("out", 8), "Z": ("out", 1), "C": ("out", 1)},
    "REG8": {"D": ("in", 8), "CLK": ("in", 1), "RESET": ("in", 1), "EN": ("in", 1), "Q": ("out", 8)},
    "PC4": {"D": ("in", 4), "INC": ("in", 1), "LOAD": ("in", 1), "CLK": ("in", 1),
            "RESET": ("in", 1), "EN": ("in", 1), "Q": ("out", 4)},
    "ROM16X8": {"ADDR": ("in", 4), "DATA": ("out", 8)},
    "SPLIT8": {"IN": ("in", 8), "HI": ("out", 4), "LO": ("out", 4)},
    "EXTEND4": {"IN": ("in", 4), "OUT": ("out", 8)},
    "MUX8": {"A": ("in", 8), "B": ("in", 8), "SEL": ("in", 1), "Y": ("out", 8)},
    "CONTROL": {"IR": ("in", 8), "ALU_Z": ("in", 1), "ALU_C": ("in", 1), "CLK": ("in", 1),
                "RESET": ("in", 1), "EN": ("in", 1),
                "IR_EN": ("out", 1), "PC_INC": ("out", 1), "PC_LOAD": ("out", 1), "ACC_EN": ("out", 1),
                "ACC_SEL": ("out", 1), "ALU_OP": ("out", 3), "PHASE": ("out", 2), "Z": ("out", 1),
                "C": ("out", 1), "HALTED": ("out", 1), "ERROR": ("out", 1)},
    "CLOCK": {"OUT": ("out", 1)},
    "RESET": {"OUT": ("out", 1)},
    "ENABLE": {"OUT": ("out", 1)},
}
# 无可写参数的元件：params 必须为空对象。
NO_PARAM_TYPES = frozenset(COMPONENT_PORTS) - {"SWITCH", "CONST", "LED", "ROM16X8"}

VERSION_COLUMNS = ("v.*, e.course_id, e.code AS experiment_code, e.title AS experiment_title, "
                   "e.description AS experiment_description, e.archived AS experiment_archived, "
                   "jp.id AS judge_profile_id")
VERSION_SOURCE = (" FROM experiment_version v JOIN experiment e ON e.id=v.experiment_id "
                  "LEFT JOIN judge_profile jp ON jp.experiment_version_id=v.id")


def _bad(message):
    return ApiError(400, "VALIDATION_ERROR", message)


def _int_between(value, low, high, field):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise _bad(f"{field} must be an integer between {low} and {high}")
    return value


def validate_panel(panel):
    """按 PRD 第6.1节结构校验面板；语义仿真与成绩判定属于 SPEC-017。"""
    if not isinstance(panel, dict):
        raise _bad("panel must be a JSON object")
    if panel.get("schema_version") != 1:
        raise _bad("panel.schema_version must be 1")
    components, terminals = panel.get("components"), panel.get("terminals")
    if not isinstance(components, list) or not components:
        raise _bad("panel.components must be a non-empty array")
    if not isinstance(terminals, list) or not terminals:
        raise _bad("panel.terminals must be a non-empty array")
    if "layout" not in panel:
        raise _bad("panel.layout is required")
    component_ids, terminal_map = set(), {}
    for component in components:
        if not isinstance(component, dict):
            raise _bad("panel.components items must be objects")
        cid = component.get("id")
        if not isinstance(cid, str) or not cid or cid in component_ids:
            raise _bad("component id must be a unique non-empty string")
        ctype = component.get("type")
        if ctype not in COMPONENT_PORTS:
            raise _bad(f"unsupported component type: {ctype}")
        ports, params = component.get("ports"), component.get("params", {})
        if not isinstance(ports, dict) or set(ports) != set(COMPONENT_PORTS[ctype]):
            raise _bad(f"component {cid} ports must map exactly {sorted(COMPONENT_PORTS[ctype])}")
        if not isinstance(params, dict):
            raise _bad(f"component {cid} params must be an object")
        if ctype in NO_PARAM_TYPES and params:
            raise _bad(f"component {cid} accepts no params")
        if ctype in ("SWITCH", "CONST", "LED"):
            width = _int_between(params.get("width"), 1, 8, f"{cid} params.width")
            if ctype == "SWITCH" and width not in (1, 3, 4, 8):
                raise _bad("SWITCH params.width must be 1, 3, 4 or 8")
            if ctype in ("SWITCH", "CONST"):
                maximum = (1 << width) - 1
                field = "initial" if ctype == "SWITCH" else "value"
                _int_between(params.get(field), 0, maximum, f"{cid} params.{field}")
        if ctype == "ROM16X8":
            words = params.get("words")
            if not isinstance(words, list) or len(words) != 16:
                raise _bad("ROM16X8 params.words must contain exactly 16 values")
            for index, word in enumerate(words):
                _int_between(word, 0, 255, f"{cid} params.words[{index}]")
        component_ids.add(cid)
    for terminal in terminals:
        if not isinstance(terminal, dict):
            raise _bad("panel.terminals items must be objects")
        tid = terminal.get("id")
        if not isinstance(tid, str) or not tid or tid in terminal_map:
            raise _bad("terminal id must be a unique non-empty string")
        if terminal.get("component_id") not in component_ids:
            raise _bad(f"terminal {tid} references an unknown component")
        if terminal.get("direction") not in ("in", "out"):
            raise _bad(f"terminal {tid} direction must be in or out")
        _int_between(terminal.get("width"), 1, 8, f"terminal {tid} width")
        if not isinstance(terminal.get("required"), bool):
            raise _bad(f"terminal {tid} required must be a boolean")
        terminal_map[tid] = terminal
    for component in components:
        for port, terminal_id in component["ports"].items():
            terminal = terminal_map.get(terminal_id)
            if terminal is None:
                raise _bad(f"component {component['id']} port {port} references an unknown terminal")
            if terminal["component_id"] != component["id"]:
                raise _bad(f"terminal {terminal_id} does not belong to component {component['id']}")
            direction, width = COMPONENT_PORTS[component["type"]][port]
            if terminal["direction"] != direction:
                raise _bad(f"terminal {terminal_id} direction mismatches port {port}")
            expected = component["params"]["width"] if width == "params.width" else width
            if terminal["width"] != expected:
                raise _bad(f"terminal {terminal_id} width must be {expected} for port {port}")
    return panel


def validate_rules(rules):
    """rules 结构校验；隐藏答案仅教师可见，语义验证属于 SPEC-017。"""
    if not isinstance(rules, dict):
        raise _bad("rules must be a JSON object")
    if "hidden" in rules and not isinstance(rules["hidden"], dict):
        raise _bad("rules.hidden must be a JSON object")
    return rules


def load_json(raw, field):
    try:
        return json.loads(raw) if raw is not None else None
    except (TypeError, ValueError) as exc:
        raise _bad(f"{field} is not valid JSON") from exc


def parse_modes(value):
    if not isinstance(value, list) or not value or len(set(value)) != len(value):
        raise _bad("submission_modes must be a non-empty array without duplicates")
    for mode in value:
        if mode not in MODES:
            raise _bad(f"unsupported submission mode: {mode}")
    return value


def version_row(db, version_id):
    row = db.execute("SELECT " + VERSION_COLUMNS + VERSION_SOURCE + " WHERE v.id=?",
                     (version_id,)).fetchone()
    if not row:
        raise ApiError(404, "NOT_FOUND", "Experiment version not found")
    return row


def knowledge_ids_for(db, version_id):
    return [row["knowledge_id"] for row in db.execute(
        "SELECT knowledge_id FROM experiment_knowledge WHERE experiment_version_id=? ORDER BY knowledge_id",
        (version_id,))]


def participant_counts(db, version_ids):
    if not version_ids:
        return {}
    marks = ",".join("?" * len(version_ids))
    return {row["experiment_version_id"]: row["n"] for row in db.execute(
        f"SELECT experiment_version_id,COUNT(*) n FROM experiment_participant "
        f"WHERE experiment_version_id IN ({marks}) GROUP BY experiment_version_id", version_ids)}


def version_json(row, student=False, knowledge_ids=None, participant_count=None):
    modes = load_json(row["submission_modes_json"], "submission_modes")
    rules = load_json(row["rules_json"], "rules")
    if student and isinstance(rules, dict):
        rules = {key: value for key, value in rules.items() if key != "hidden"}
    data = {
        "id": row["id"],
        "experiment_id": row["experiment_id"],
        "version": row["version"],
        "title": row["title"],
        "objectives": row["objectives"],
        "knowledge_ids": knowledge_ids if knowledge_ids is not None else [],
        "instructions": row["instructions"],
        "submission_modes": modes,
        "panel": load_json(row["panel_json"], "panel"),
        "rules": rules,
        "judge_profile_id": row["judge_profile_id"],
        "status": row["status"],
        "published_at": row["published_at"],
        "start_at": row["start_at"],
        "end_at": row["end_at"],
        "experiment": {
            "id": row["experiment_id"],
            "code": row["experiment_code"],
            "title": row["experiment_title"],
            "description": row["experiment_description"],
            "archived": row["experiment_archived"],
        },
    }
    if participant_count is not None:
        data["participant_count"] = participant_count
    return data


def version_summary(row, participant_count=None):
    summary = {
        "id": row["id"],
        "version": row["version"],
        "title": row["title"],
        "status": row["status"],
        "submission_modes": load_json(row["submission_modes_json"], "submission_modes"),
        "start_at": row["start_at"],
        "end_at": row["end_at"],
        "published_at": row["published_at"],
    }
    if participant_count is not None:
        summary["participant_count"] = participant_count
    return summary


def visible_version(db, version_id, user):
    """学生仅可见本人参与名单内的已发布版本（R02/R16）；教师可见全部版本。"""
    row = version_row(db, version_id)
    _, role = course_access(row["course_id"])
    if role == "student":
        allowed = db.execute(
            "SELECT 1 FROM experiment_version v JOIN experiment_participant p "
            "ON p.experiment_version_id=v.id WHERE v.id=? AND v.status='published' AND p.student_id=?",
            (version_id, user["id"])).fetchone()
        if not allowed:
            raise ApiError(404, "NOT_FOUND", "Experiment version not found")
    return row, role


@bp.post("/courses/<int:course_id>/experiments")
def create_experiment(course_id):
    data = body(("code", "title", "description"))
    code, title = data["code"], text_field(data["title"], "title")
    description = text_field(data["description"], "description", maximum=500)
    if code not in CODES:
        raise _bad("code must be one of EXP-01..EXP-04")
    with write() as db:
        course_access(course_id, teacher=True)
        timestamp = stamp()
        cursor = db.execute(
            "INSERT INTO experiment(course_id,code,title,description,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?)", (course_id, code, title, description, timestamp, timestamp))
        experiment_id = cursor.lastrowid
        audit("experiment.create", "experiment", experiment_id,
              after={"course_id": course_id, "code": code})
    return result({"id": experiment_id, "title": title}, 201)


@bp.get("/courses/<int:course_id>/experiments")
def list_experiments(course_id):
    user = require_user()
    _, role = course_access(course_id)
    page, size = page_args()
    db = get_db()
    if role == "student":
        total = db.execute(
            "SELECT COUNT(DISTINCT e.id) FROM experiment e JOIN experiment_version v "
            "ON v.experiment_id=e.id JOIN experiment_participant p ON p.experiment_version_id=v.id "
            "WHERE e.course_id=? AND v.status='published' AND p.student_id=?", (course_id, user["id"]),
        ).fetchone()[0]
        experiments = db.execute(
            "SELECT DISTINCT e.* FROM experiment e JOIN experiment_version v "
            "ON v.experiment_id=e.id JOIN experiment_participant p ON p.experiment_version_id=v.id "
            "WHERE e.course_id=? AND v.status='published' AND p.student_id=? "
            "ORDER BY e.id DESC LIMIT ? OFFSET ?", (course_id, user["id"], size, (page - 1) * size),
        ).fetchall()
    else:
        total = db.execute("SELECT COUNT(*) FROM experiment WHERE course_id=?", (course_id,)).fetchone()[0]
        experiments = db.execute(
            "SELECT * FROM experiment WHERE course_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (course_id, size, (page - 1) * size)).fetchall()
    items = []
    for experiment in experiments:
        if role == "student":
            latest = db.execute(
                "SELECT v.*, jp.id AS judge_profile_id FROM experiment_version v "
                "JOIN experiment_participant p ON p.experiment_version_id=v.id "
                "LEFT JOIN judge_profile jp ON jp.experiment_version_id=v.id "
                "WHERE v.experiment_id=? AND v.status='published' AND p.student_id=? "
                "ORDER BY v.version DESC LIMIT 1", (experiment["id"], user["id"])).fetchone()
        else:
            latest = db.execute(
                "SELECT v.*, jp.id AS judge_profile_id FROM experiment_version v "
                "LEFT JOIN judge_profile jp ON jp.experiment_version_id=v.id "
                "WHERE v.experiment_id=? ORDER BY v.version DESC LIMIT 1", (experiment["id"],)).fetchone()
        count = None
        if latest and latest["status"] == "published":
            count = db.execute("SELECT COUNT(*) FROM experiment_participant WHERE experiment_version_id=?",
                               (latest["id"],)).fetchone()[0]
        items.append({
            "id": experiment["id"],
            "code": experiment["code"],
            "title": experiment["title"],
            "description": experiment["description"],
            "archived": experiment["archived"],
            "created_at": experiment["created_at"],
            "latest_version": version_summary(latest, count) if latest else None,
        })
    return paged(items, total, page, size)


@bp.post("/experiments/<int:experiment_id>/versions")
def create_version(experiment_id):
    data = body(("title", "objectives", "knowledge_ids", "instructions", "submission_modes", "rules"),
                ("panel",))
    title = text_field(data["title"], "title")
    objectives = text_field(data["objectives"], "objectives", maximum=2000)
    instructions = text_field(data["instructions"], "instructions", maximum=2000)
    modes = parse_modes(data["submission_modes"])
    knowledge_ids = data["knowledge_ids"]
    if not isinstance(knowledge_ids, list):
        raise _bad("knowledge_ids must be an array")
    for knowledge_id in knowledge_ids:
        positive_int(knowledge_id, "knowledge_ids")
    panel = data.get("panel")
    if "wiring" in modes and panel is None:
        raise _bad("panel is required for wiring submissions")
    if panel is not None:
        validate_panel(panel)
    rules = validate_rules(data["rules"])
    unique_knowledge = sorted(set(knowledge_ids))
    with write() as db:
        experiment = db.execute("SELECT * FROM experiment WHERE id=?", (experiment_id,)).fetchone()
        if not experiment:
            raise ApiError(404, "NOT_FOUND", "Experiment not found")
        course_access(experiment["course_id"], teacher=True)
        # 跨课程引用必须验证双方 course_id 一致（DBD 第1节）。
        if unique_knowledge:
            marks = ",".join("?" * len(unique_knowledge))
            found = {row["id"] for row in db.execute(
                f"SELECT k.id FROM knowledge_point k JOIN chapter c ON c.id=k.chapter_id "
                f"WHERE k.id IN ({marks}) AND c.course_id=?", (*unique_knowledge, experiment["course_id"]))}
            missing = sorted(set(unique_knowledge) - found)
            if missing:
                raise _bad(f"knowledge_ids not in this course: {missing}")
        version = db.execute("SELECT COALESCE(MAX(version),0)+1 FROM experiment_version "
                             "WHERE experiment_id=?", (experiment_id,)).fetchone()[0]
        definition = {"title": title, "objectives": objectives, "instructions": instructions,
                      "submission_modes": modes, "panel": panel, "rules": rules}
        digest = hashlib.sha256(
            json.dumps(definition, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        timestamp = stamp()
        cursor = db.execute(
            "INSERT INTO experiment_version(experiment_id,version,title,objectives,instructions,"
            "submission_modes_json,panel_json,rules_json,status,definition_sha256,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,'draft',?,?,?)",
            (experiment_id, version, title, objectives, instructions,
             json.dumps(modes), json.dumps(panel) if panel is not None else None,
             json.dumps(rules, ensure_ascii=False), digest, timestamp, timestamp))
        version_id = cursor.lastrowid
        db.executemany("INSERT INTO experiment_knowledge(experiment_version_id,knowledge_id) VALUES(?,?)",
                       [(version_id, knowledge_id) for knowledge_id in unique_knowledge])
        audit("experiment.version_create", "experiment_version", version_id,
              after={"experiment_id": experiment_id, "version": version, "submission_modes": modes})
        row = version_row(db, version_id)
    return result(version_json(row, knowledge_ids=unique_knowledge), 201)


@bp.post("/experiment-versions/<int:version_id>/publish")
def publish_version(version_id):
    data = body(("start_at", "end_at"), ("initial_test_suite_id",))
    start = parse_time(data["start_at"], "start_at")
    end = parse_time(data["end_at"], "end_at")
    if start >= end:
        raise _bad("start_at must be earlier than end_at")
    with write() as db:
        row = version_row(db, version_id)
        course_access(row["course_id"], teacher=True)
        if row["status"] != "draft":
            raise ApiError(409, "STATE_CONFLICT", "Version is already published")
        modes = load_json(row["submission_modes_json"], "submission_modes")
        if not set(modes) <= CODE_MODES[row["experiment_code"]]:
            raise ApiError(409, "STATE_CONFLICT",
                           "Submission modes are not supported by this experiment code")
        if "wiring" in modes:
            panel = load_json(row["panel_json"], "panel")
            rules = load_json(row["rules_json"], "rules")
            if panel is None or rules is None:
                raise ApiError(409, "STATE_CONFLICT", "Wiring version lacks panel or rules")
            validate_panel(panel)
            validate_rules(rules)
        if "circuit" in modes:
            # R04：缺判分配置发布 409 且保持 draft；配置与有效测试集齐全才可发布。
            profile = db.execute("SELECT id FROM judge_profile WHERE experiment_version_id=?",
                                 (version_id,)).fetchone()
            if not profile:
                raise ApiError(409, "STATE_CONFLICT",
                               "Circuit version requires a judge profile before publishing")
            if "initial_test_suite_id" not in data:
                raise _bad("initial_test_suite_id is required for circuit versions")
            positive_int(data["initial_test_suite_id"], "initial_test_suite_id")
            # SPEC-018 将在此复核测试集同版本、已发布且验证身份一致。
        students = db.execute(
            "SELECT m.user_id FROM course_member m JOIN user u ON u.id=m.user_id "
            "WHERE m.course_id=? AND m.member_role='student' AND m.active=1 "
            "AND u.role='student' AND u.active=1 ORDER BY m.user_id", (row["course_id"],)).fetchall()
        if not students:
            raise ApiError(422, "EMPTY_PARTICIPANTS", "Course has no active students")
        timestamp = stamp()
        db.execute("UPDATE experiment_version SET status='published',published_at=?,start_at=?,end_at=?,"
                   "updated_at=? WHERE id=?",
                   (timestamp, stamp(start), stamp(end), timestamp, version_id))
        db.executemany("INSERT INTO experiment_participant(experiment_version_id,student_id) VALUES(?,?)",
                       [(version_id, student["user_id"]) for student in students])
        for student in students:
            notify(student["user_id"], row["course_id"],
                   f"实验发布：{row['experiment_title']}", "experiment_version", version_id,
                   f"experiment.published:{version_id}")
        audit("experiment.publish", "experiment_version", version_id,
              after={"participants": len(students), "start_at": stamp(start), "end_at": stamp(end)})
        published = version_row(db, version_id)
    return result(version_json(published, participant_count=len(students)))


@bp.get("/experiment-versions/<int:version_id>")
def version_detail(version_id):
    db = get_db()
    row, role = visible_version(db, version_id, require_user())
    count = participant_counts(db, [version_id]).get(version_id) if row["status"] == "published" else None
    return result(version_json(row, student=(role == "student"),
                               knowledge_ids=knowledge_ids_for(db, version_id),
                               participant_count=count))


@bp.get("/courses/<int:course_id>/experiment-versions")
def list_versions(course_id):
    user = require_user()
    _, role = course_access(course_id)
    experiment_id = positive_int(request.args["experiment_id"], "experiment_id") \
        if request.args.get("experiment_id") else None
    status = request.args.get("status")
    if status and status not in ("draft", "published"):
        raise _bad("Invalid status")
    page, size = page_args()
    where, params = [], []
    if role == "student":
        where.append("e.course_id=? AND v.status='published' AND EXISTS("
                     "SELECT 1 FROM experiment_participant p WHERE p.experiment_version_id=v.id "
                     "AND p.student_id=?)")
        params.extend((course_id, user["id"]))
    else:
        where.append("e.course_id=?")
        params.append(course_id)
    if experiment_id:
        where.append("v.experiment_id=?")
        params.append(experiment_id)
    if status:
        where.append("v.status=?")
        params.append(status)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    db = get_db()
    total = db.execute("SELECT COUNT(*)" + VERSION_SOURCE + clause, params).fetchone()[0]
    rows = db.execute("SELECT " + VERSION_COLUMNS + VERSION_SOURCE + clause +
                      " ORDER BY v.id DESC LIMIT ? OFFSET ?", (*params, size, (page - 1) * size)).fetchall()
    counts = participant_counts(db, [row["id"] for row in rows])
    return paged([version_json(row, student=(role == "student"),
                               knowledge_ids=knowledge_ids_for(db, row["id"]),
                               participant_count=counts.get(row["id"]) if row["status"] == "published" else None)
                  for row in rows], total, page, size)
