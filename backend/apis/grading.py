"""SPEC-018 online grading API: submissions, runs, suites, profiles and admin ops.

身份与课程授权沿用公共协议；沙箱与租约在 engines/grading.py；
评分模板与 .circ 预检在 models/grading.py。连线过程（wiring）属于 SPEC-017。
"""

import hashlib
import json
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file

from backend.apis.experiments import load_json, version_row
from backend.engines import grading as engine
from backend.models import attempt as attempt_model
from backend.models.grading import (
    EFFECTIVE_STATUSES,
    ENGINE_VERSION,
    canonical_profile_sha256,
    invalid,
    preflight_basic,
    preflight_circ,
    run_json,
    scoring_groups_json,
    submission_json,
    suite_content_sha256,
    suite_json,
    template_for,
    validate_allowed_components,
    validate_cases,
    validate_limits,
    validate_port_schema,
)
from backend.shared.api import (
    ApiError,
    audit,
    body,
    now,
    page_args,
    paged,
    positive_int,
    rate_limit,
    request_id,
    result,
    stamp,
    text_field,
)
from backend.shared.auth import course_access, require_admin, require_user
from backend.shared.db import get_db, write

bp = Blueprint("grading", __name__)

MAX_QUEUE = 100
ACTIVE_RUN_LIMIT = 2
SUBMIT_PER_MINUTE = 3
OPERATION_SUBMIT = "circuit_submission"
OPERATION_REGRADE = "circuit_regrade"


def _bad(message):
    return ApiError(400, "VALIDATION_ERROR", message)


def _load_version(db, version_id, *, teacher=False):
    row = version_row(db, version_id)
    course_access(row["course_id"], teacher=teacher)
    return row


def _circuit_draft(db, version_id):
    row = _load_version(db, version_id, teacher=True)
    modes = load_json(row["submission_modes_json"], "submission_modes")
    if "circuit" not in modes:
        raise ApiError(409, "STATE_CONFLICT", "Judge profile applies only to circuit versions")
    if row["status"] != "draft":
        raise ApiError(409, "STATE_CONFLICT", "Published versions are frozen")
    return row


def _profile_of(db, version_id):
    return db.execute("SELECT * FROM judge_profile WHERE experiment_version_id=?",
                      (version_id,)).fetchone()


def _save_circ(file_storage):
    """读取 .circ 上传内容并做大小/扩展名/结构预检；返回 (content, sha256)。"""
    if not file_storage or not file_storage.filename:
        raise _bad("file required")
    if not file_storage.filename.lower().endswith(".circ"):
        raise _bad("only .circ files are accepted")
    content = file_storage.read()
    if not content:
        raise _bad("Empty file")
    if len(content) > 2 * 1024 * 1024:
        raise ApiError(413, "FILE_TOO_LARGE", ".circ exceeds the 2 MiB limit")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise invalid("circuit file must be UTF-8 XML") from exc
    return text, hashlib.sha256(content).hexdigest()


def _persist_file(content, owner_id, purpose, filename):
    """安全落盘（随机存储键，不使用上传文件名）；返回 file_object 字段。"""
    from uuid import uuid4
    root = Path(current_app.config["UPLOAD_ROOT"])
    root.mkdir(parents=True, exist_ok=True)
    storage_key = uuid4().hex
    target = root / storage_key
    target.write_bytes(content)
    return {"storage_key": storage_key, "original_name": filename or storage_key,
            "media_type": "application/xml", "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(), "purpose": purpose}, target


def _insert_file_object(db, fields, owner_id):
    cursor = db.execute(
        "INSERT INTO file_object(owner_id,storage_key,original_name,media_type,"
        "size_bytes,sha256,purpose,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (owner_id, fields["storage_key"], fields["original_name"], fields["media_type"],
         fields["size_bytes"], fields["sha256"], fields["purpose"], stamp()))
    return cursor.lastrowid


def _remove_file(storage_key):
    try:
        (Path(current_app.config["UPLOAD_ROOT"]) / storage_key).unlink(missing_ok=True)
    except OSError:
        pass


# ---------- 教师配置：judge profile ----------

@bp.put("/experiment-versions/<int:version_id>/judge-profile")
def put_judge_profile(version_id):
    data = body(("top_circuit", "port_schema", "allowed_components", "limits"), ("engine_version",))
    top = text_field(data["top_circuit"], "top_circuit", maximum=100)
    port_schema = validate_port_schema(data["port_schema"])
    components = validate_allowed_components(data["allowed_components"])
    limits = validate_limits(data["limits"])
    engine_version = data.get("engine_version", ENGINE_VERSION)
    if engine_version != ENGINE_VERSION:
        raise _bad(f"engine_version must be {ENGINE_VERSION}")
    jar = engine.jar_path()
    jar_sha = None
    if jar and Path(jar).is_file():
        jar_sha = hashlib.sha256(Path(jar).read_bytes()).hexdigest()
    canonical = canonical_profile_sha256(top, port_schema, components, engine_version, limits)
    with write() as db:
        _circuit_draft(db, version_id)
        existing = _profile_of(db, version_id)
        if existing:
            db.execute(
                "UPDATE judge_profile SET port_schema_json=?,allowed_components_json=?,"
                "engine_version=?,jar_sha256=?,limits_json=?,canonical_sha256=?,updated_at=? "
                "WHERE id=?",
                (json.dumps(port_schema, sort_keys=True), json.dumps(components),
                 engine_version, jar_sha, json.dumps(limits, sort_keys=True), canonical,
                 stamp(), existing["id"]))
            profile_id = existing["id"]
            audit("grading.profile_update", "judge_profile", profile_id,
                  before={"canonical_sha256": existing["canonical_sha256"]},
                  after={"canonical_sha256": canonical})
        else:
            profile_id = db.execute(
                "INSERT INTO judge_profile(experiment_version_id,top_circuit,port_schema_json,"
                "allowed_components_json,engine_version,jar_sha256,limits_json,canonical_sha256,"
                "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (version_id, top, json.dumps(port_schema, sort_keys=True),
                 json.dumps(components), engine_version, jar_sha,
                 json.dumps(limits, sort_keys=True), canonical, stamp(), stamp())).lastrowid
            audit("grading.profile_create", "judge_profile", profile_id,
                  after={"top_circuit": top, "canonical_sha256": canonical})
        row = db.execute("SELECT * FROM judge_profile WHERE id=?", (profile_id,)).fetchone()
    return result(_profile_json(row))


def _profile_json(row):
    return {"id": row["id"], "experiment_version_id": row["experiment_version_id"],
            "top_circuit": row["top_circuit"],
            "port_schema": json.loads(row["port_schema_json"]),
            "allowed_components": json.loads(row["allowed_components_json"]),
            "engine_version": row["engine_version"], "jar_sha256": row["jar_sha256"],
            "limits": json.loads(row["limits_json"]),
            "canonical_sha256": row["canonical_sha256"]}


# ---------- 教师配置：测试集 ----------

@bp.post("/experiment-versions/<int:version_id>/test-suites")
def create_test_suite(version_id):
    data = body(("cases",))
    with write() as db:
        row = _load_version(db, version_id, teacher=True)
        modes = load_json(row["submission_modes_json"], "submission_modes")
        if "circuit" not in modes:
            raise ApiError(409, "STATE_CONFLICT", "Test suites apply only to circuit versions")
        _groups, _template = template_for(row["experiment_code"])
        profile = _profile_of(db, version_id)
        port_schema = json.loads(profile["port_schema_json"]) if profile else None
        cases = validate_cases(data["cases"], _groups, port_schema)
        content_sha = suite_content_sha256(cases)
        version = db.execute("SELECT COALESCE(MAX(version),0)+1 FROM test_suite "
                             "WHERE experiment_version_id=?", (version_id,)).fetchone()[0]
        suite_id = db.execute(
            "INSERT INTO test_suite(experiment_version_id,version,status,content_sha256,"
            "scoring_groups_json,created_at) VALUES(?,?,'draft',?,?,?)",
            (version_id, version, content_sha,
             scoring_groups_json(row["experiment_code"]), stamp())).lastrowid
        db.executemany(
            "INSERT INTO test_case(suite_id,label,visibility,group_code,steps_json) "
            "VALUES(?,?,?,?,?)",
            [(suite_id, case["label"].strip(), case["visibility"], case["group_code"],
              json.dumps(case["steps"], ensure_ascii=False)) for case in cases])
        audit("grading.suite_create", "test_suite", suite_id,
              after={"version": version, "content_sha256": content_sha, "cases": len(cases)})
        suite = db.execute("SELECT * FROM test_suite WHERE id=?", (suite_id,)).fetchone()
        stored = db.execute("SELECT * FROM test_case WHERE suite_id=? ORDER BY id",
                            (suite_id,)).fetchall()
    return result(suite_json(suite, stored), 201)


@bp.get("/experiment-versions/<int:version_id>/test-suites")
def list_test_suites(version_id):
    db = get_db()
    _load_version(db, version_id, teacher=True)
    status = request.args.get("status")
    if status and status not in ("draft", "published"):
        raise _bad("Invalid status")
    page, size = page_args()
    where, params = "WHERE experiment_version_id=?", [version_id]
    if status:
        where += " AND status=?"
        params.append(status)
    total = db.execute(f"SELECT COUNT(*) FROM test_suite {where}", params).fetchone()[0]
    rows = db.execute(f"SELECT * FROM test_suite {where} ORDER BY version DESC LIMIT ? OFFSET ?",
                      (*params, size, (page - 1) * size)).fetchall()
    items = []
    for suite in rows:
        count = db.execute("SELECT COUNT(*) FROM test_case WHERE suite_id=?",
                           (suite["id"],)).fetchone()[0]
        validation = db.execute(
            "SELECT id,status,created_at,finished_at FROM test_suite_validation "
            "WHERE suite_id=? ORDER BY id DESC LIMIT 1", (suite["id"],)).fetchone()
        item = suite_json(suite)
        item["total_count"] = count
        item["validation"] = dict(validation) if validation else None
        items.append(item)
    return paged(items, total, page, size)


@bp.get("/test-suites/<int:suite_id>")
def test_suite_detail(suite_id):
    db = get_db()
    suite = db.execute("SELECT * FROM test_suite WHERE id=?", (suite_id,)).fetchone()
    if not suite:
        raise ApiError(404, "NOT_FOUND", "Test suite not found")
    _load_version(db, suite["experiment_version_id"], teacher=True)
    cases = db.execute("SELECT * FROM test_case WHERE suite_id=? ORDER BY id",
                       (suite_id,)).fetchall()
    return result(suite_json(suite, cases))


# ---------- 教师配置：参考文件 ----------

@bp.post("/experiment-versions/<int:version_id>/reference-files")
def upload_reference_file(version_id):
    user = require_user()
    kind = request.form.get("kind", "")
    if kind not in ("correct", "known_wrong"):
        raise _bad("kind must be correct or known_wrong")
    text, _sha = _save_circ(request.files.get("file"))
    with write() as db:
        row = _load_version(db, version_id, teacher=True)
        modes = load_json(row["submission_modes_json"], "submission_modes")
        if "circuit" not in modes:
            raise ApiError(409, "STATE_CONFLICT", "Reference files apply only to circuit versions")
        profile = _profile_of(db, version_id)
        if profile:
            # 教师身份不绕过沙箱：与学生文件同样的结构预检。
            preflight_circ(text, profile)
        else:
            preflight_basic(text)
        fields, _target = _persist_file(text.encode("utf-8"), user["id"],
                                        f"grading_reference:{kind}", request.files["file"].filename)
        try:
            file_id = _insert_file_object(db, fields, user["id"])
            reference_id = db.execute(
                "INSERT INTO reference_file(experiment_version_id,file_id,kind,sha256,created_at) "
                "VALUES(?,?,?,?,?)", (version_id, file_id, kind, fields["sha256"], stamp())).lastrowid
            audit("grading.reference_upload", "reference_file", reference_id,
                  after={"kind": kind, "sha256": fields["sha256"]})
        except BaseException:
            _remove_file(fields["storage_key"])
            raise
    return result({"file_id": file_id, "reference_file_id": reference_id,
                   "sha256": fields["sha256"], "kind": kind}, 201)


@bp.get("/experiment-versions/<int:version_id>/reference-files")
def list_reference_files(version_id):
    db = get_db()
    _load_version(db, version_id, teacher=True)
    page, size = page_args()
    total = db.execute("SELECT COUNT(*) FROM reference_file WHERE experiment_version_id=?",
                       (version_id,)).fetchone()[0]
    rows = db.execute(
        "SELECT * FROM reference_file WHERE experiment_version_id=? ORDER BY id DESC "
        "LIMIT ? OFFSET ?", (version_id, size, (page - 1) * size)).fetchall()
    return paged([{"file_id": row["file_id"], "reference_file_id": row["id"],
                   "kind": row["kind"], "sha256": row["sha256"],
                   "created_at": row["created_at"]} for row in rows], total, page, size)


# ---------- 教师配置：验证与发布 ----------

@bp.post("/test-suites/<int:suite_id>/validations")
def create_validation(suite_id):
    data = body(("reference_file_id", "negative_file_id"))
    with write() as db:
        suite = db.execute("SELECT * FROM test_suite WHERE id=?", (suite_id,)).fetchone()
        if not suite:
            raise ApiError(404, "NOT_FOUND", "Test suite not found")
        version = _load_version(db, suite["experiment_version_id"], teacher=True)
        profile = _profile_of(db, suite["experiment_version_id"])
        if not profile:
            # R04：circuit 草稿无配置时可建测试集/参考文件，但发起验证 409。
            raise ApiError(409, "STATE_CONFLICT",
                           "Judge profile is required before validating a test suite")
        # 每组至少一 case，所有必需评分组齐全才可验证发布（R13）。
        groups_max, _template = template_for(version["experiment_code"])
        found_groups = {row["group_code"] for row in db.execute(
            "SELECT DISTINCT group_code FROM test_case WHERE suite_id=?", (suite_id,))}
        if found_groups != set(groups_max):
            missing = sorted(set(groups_max) - found_groups)
            raise ApiError(409, "STATE_CONFLICT",
                           f"Test suite is missing required scoring groups: {missing}")
        reference = db.execute(
            "SELECT * FROM reference_file WHERE id=? AND experiment_version_id=? AND kind='correct'",
            (positive_int(data["reference_file_id"], "reference_file_id"),
             suite["experiment_version_id"])).fetchone()
        negative = db.execute(
            "SELECT * FROM reference_file WHERE id=? AND experiment_version_id=? "
            "AND kind='known_wrong'",
            (positive_int(data["negative_file_id"], "negative_file_id"),
             suite["experiment_version_id"])).fetchone()
        if not reference or not negative:
            raise _bad("reference and known_wrong files must belong to this experiment version")
        validation_id = db.execute(
            "INSERT INTO test_suite_validation(suite_id,profile_sha256,suite_sha256,jar_sha256,"
            "reference_file_id,reference_sha256,negative_file_id,negative_sha256,status,"
            "created_at) VALUES(?,?,?,?,?,?,?,?, 'queued',?)",
            (suite_id, profile["canonical_sha256"], suite["content_sha256"],
             profile["jar_sha256"], reference["id"], reference["sha256"],
             negative["id"], negative["sha256"], stamp())).lastrowid
        audit("grading.validation_create", "test_suite_validation", validation_id,
              after={"suite_id": suite_id})
    return result({"validation_id": validation_id, "status": "queued"}, 202)


@bp.get("/test-suite-validations/<int:validation_id>")
def validation_detail(validation_id):
    db = get_db()
    row = db.execute("SELECT * FROM test_suite_validation WHERE id=?",
                     (validation_id,)).fetchone()
    if not row:
        raise ApiError(404, "NOT_FOUND", "Validation not found")
    suite = db.execute("SELECT * FROM test_suite WHERE id=?", (row["suite_id"],)).fetchone()
    _load_version(db, suite["experiment_version_id"], teacher=True)
    return result({"id": row["id"], "suite_id": row["suite_id"], "status": row["status"],
                   "error_code": row["error_code"],
                   "result": json.loads(row["result_json"]) if row["result_json"] else None,
                   "profile_sha256": row["profile_sha256"],
                   "suite_sha256": row["suite_sha256"], "jar_sha256": row["jar_sha256"],
                   "reference_file_id": row["reference_file_id"],
                   "negative_file_id": row["negative_file_id"],
                   "started_at": row["started_at"], "finished_at": row["finished_at"]})


@bp.post("/test-suites/<int:suite_id>/publish")
def publish_test_suite(suite_id):
    data = body(("validation_id",))
    with write() as db:
        suite = db.execute("SELECT * FROM test_suite WHERE id=?", (suite_id,)).fetchone()
        if not suite:
            raise ApiError(404, "NOT_FOUND", "Test suite not found")
        _load_version(db, suite["experiment_version_id"], teacher=True)
        if suite["status"] != "draft":
            raise ApiError(409, "STATE_CONFLICT", "Test suite is already published")
        validation = db.execute("SELECT * FROM test_suite_validation WHERE id=? AND suite_id=?",
                                (positive_int(data["validation_id"], "validation_id"),
                                 suite_id)).fetchone()
        if not validation:
            raise _bad("validation must belong to this test suite")
        profile = _profile_of(db, suite["experiment_version_id"])
        # 只有与当前 suite/profile/JAR/标准及反例文件全部哈希一致且 passed 的验证可发布（R04）。
        if validation["status"] != "passed":
            raise ApiError(409, "STATE_CONFLICT", "Only a passed validation can publish")
        if not profile or validation["profile_sha256"] != profile["canonical_sha256"] \
                or validation["suite_sha256"] != suite["content_sha256"] \
                or validation["jar_sha256"] != profile["jar_sha256"]:
            raise ApiError(409, "STATE_CONFLICT",
                           "Validation certificate no longer matches the current configuration")
        reference = db.execute("SELECT * FROM reference_file WHERE id=?",
                               (validation["reference_file_id"],)).fetchone()
        negative = db.execute("SELECT * FROM reference_file WHERE id=?",
                              (validation["negative_file_id"],)).fetchone()
        if not reference or reference["sha256"] != validation["reference_sha256"] \
                or not negative or negative["sha256"] != validation["negative_sha256"]:
            raise ApiError(409, "STATE_CONFLICT",
                           "Reference files changed after validation")
        db.execute("UPDATE test_suite SET status='published',published_at=?,"
                   "published_validation_id=? WHERE id=? AND status='draft'",
                   (stamp(), validation["id"], suite_id))
        audit("grading.suite_publish", "test_suite", suite_id,
              after={"validation_id": validation["id"]})
        published = db.execute("SELECT * FROM test_suite WHERE id=?", (suite_id,)).fetchone()
    return result({"id": published["id"], "version": published["version"],
                   "status": published["status"], "published_at": published["published_at"]})


@bp.put("/experiment-versions/<int:version_id>/active-test-suite")
def set_active_suite(version_id):
    data = body(("test_suite_id", "revision"))
    with write() as db:
        row = _load_version(db, version_id, teacher=True)
        modes = load_json(row["submission_modes_json"], "submission_modes")
        if "circuit" not in modes:
            raise ApiError(409, "STATE_CONFLICT", "Active suites apply only to circuit versions")
        suite = db.execute("SELECT * FROM test_suite WHERE id=? AND experiment_version_id=? "
                           "AND status='published'",
                           (positive_int(data["test_suite_id"], "test_suite_id"),
                            version_id)).fetchone()
        if not suite:
            raise _bad("test_suite_id must be a published suite of this experiment version")
        binding = db.execute("SELECT * FROM experiment_grading WHERE experiment_version_id=?",
                             (version_id,)).fetchone()
        # 首个绑定由实验发布事务建立；此端点仅做原子的后续切换。
        if not binding:
            raise ApiError(409, "STATE_CONFLICT",
                           "Publish the experiment version before switching suites")
        if not isinstance(data["revision"], int) or isinstance(data["revision"], bool) \
                or data["revision"] < 1:
            raise _bad("revision must be a positive integer")
        updated = db.execute(
            "UPDATE experiment_grading SET active_suite_id=?,revision=revision+1 "
            "WHERE experiment_version_id=? AND revision=?",
            (suite["id"], version_id, data["revision"])).rowcount
        if updated != 1:
            raise ApiError(409, "REVISION_CONFLICT", "Active suite binding changed")
        new_revision = data["revision"] + 1
        audit("grading.active_suite", "experiment_version", version_id,
              after={"test_suite_id": suite["id"], "revision": new_revision})
    return result({"test_suite_id": suite["id"], "revision": new_revision})


# ---------- 学生提交 ----------

@bp.post("/experiment-versions/<int:version_id>/submissions")
def create_submission(version_id):
    user = require_user()
    if user["role"] != "student":
        raise ApiError(403, "FORBIDDEN", "Only students submit circuits")
    key = attempt_model.idempotency_key(request.headers.get("Idempotency-Key"))
    text, file_sha = _save_circ(request.files.get("file"))
    with write() as db:
        row = version_row(db, version_id)
        # 幂等执行顺序：身份及对象授权→基础语法→查键比对指纹→重放→限额→事务（APIC 第11节）。
        course_access(row["course_id"])
        modes = load_json(row["submission_modes_json"], "submission_modes")
        if "circuit" not in modes:
            raise ApiError(409, "STATE_CONFLICT", "This version does not accept circuit files")
        if row["status"] != "published":
            raise ApiError(404, "NOT_FOUND", "Experiment version not found")
        from backend.shared.api import now
        current = now()
        if not (row["start_at"] and row["end_at"]
                and row["start_at"] <= stamp(current) < row["end_at"]):
            raise ApiError(409, "WINDOW_CLOSED", "Submission window is closed")
        allowed = db.execute(
            "SELECT 1 FROM experiment_participant WHERE experiment_version_id=? AND student_id=?",
            (version_id, user["id"])).fetchone()
        if not allowed:
            raise ApiError(403, "FORBIDDEN", "Not on the frozen participant list")
        binding = db.execute("SELECT * FROM experiment_grading WHERE experiment_version_id=?",
                             (version_id,)).fetchone()
        if not binding:
            raise ApiError(409, "STATE_CONFLICT", "Version has no active test suite")
        request_hash = hashlib.sha256(
            f"{version_id}:{file_sha}".encode()).hexdigest()
        replayed = attempt_model.replay(db, user["id"], key, request_hash, stamp(current),
                                        operation=OPERATION_SUBMIT)
        if replayed:
            from flask import Response
            return Response(replayed["response_json"], status=replayed["response_status"],
                            mimetype="application/json")
        profile = _profile_of(db, version_id)
        # 权限、大小、内容、端口预检先于入队（AC-03）；失败不创建任务。
        preflight_circ(text, profile)
        suite = db.execute("SELECT * FROM test_suite WHERE id=?",
                           (binding["active_suite_id"],)).fetchone()
        active = db.execute(
            "SELECT COUNT(*) FROM grading_run r JOIN submission s ON s.id=r.submission_id "
            "WHERE s.student_id=? AND s.experiment_version_id=? "
            "AND r.status IN ('queued','running')", (user["id"], version_id)).fetchone()[0]
        if active >= ACTIVE_RUN_LIMIT:
            raise ApiError(429, "RATE_LIMITED", "Too many active tasks for this experiment")
        queued = db.execute("SELECT COUNT(*) FROM grading_run WHERE status='queued'").fetchone()[0]
        if queued >= MAX_QUEUE:
            raise ApiError(503, "QUEUE_FULL", "Grading queue is full, retry later")
        rate_limit(f"grading-submit:{user['id']}:{version_id}", SUBMIT_PER_MINUTE)
        fields, _target = _persist_file(text.encode("utf-8"), user["id"],
                                        "grading_submission", request.files["file"].filename)
        try:
            file_id = _insert_file_object(db, fields, user["id"])
            submission_id = db.execute(
                "INSERT INTO submission(experiment_version_id,student_id,file_id,file_sha256,"
                "size_bytes,filename,created_at) VALUES(?,?,?,?,?,?,?)",
                (version_id, user["id"], file_id, file_sha, fields["size_bytes"],
                 fields["original_name"], stamp(current))).lastrowid
            run_id = db.execute(
                "INSERT INTO grading_run(submission_id,suite_id,engine_version,jar_sha256,status,"
                "total_count,profile_snapshot_json,profile_sha256,suite_sha256,created_at) "
                "VALUES(?,?,?,?, 'queued',?,?,?,?,?)",
                (submission_id, suite["id"], profile["engine_version"], profile["jar_sha256"],
                 db.execute("SELECT COUNT(*) FROM test_case WHERE suite_id=?",
                            (suite["id"],)).fetchone()[0],
                 json.dumps(_profile_json(profile), sort_keys=True),
                 profile["canonical_sha256"], suite["content_sha256"], stamp(current))).lastrowid
            audit("grading.submit", "submission", submission_id,
                  after={"run_id": run_id, "file_sha256": file_sha, "suite_id": suite["id"]})
        except BaseException:
            _remove_file(fields["storage_key"])
            raise
        payload = {"submission_id": submission_id, "run_id": run_id, "status": "queued",
                   "status_url": f"/api/v1/grading-runs/{run_id}"}
        response = jsonify(data=payload, request_id=request_id())
        attempt_model.save_response(db, user["id"], key, request_hash, submission_id,
                                    response, 202, operation=OPERATION_SUBMIT,
                                    resource_type="submission")
    return response, 202


def _load_submission(db, submission_id, *, teacher=False):
    row = db.execute("SELECT * FROM submission WHERE id=?", (submission_id,)).fetchone()
    if not row:
        raise ApiError(404, "NOT_FOUND", "Submission not found")
    version = version_row(db, row["experiment_version_id"])
    user = require_user()
    if teacher:
        course_access(version["course_id"], teacher=True)
        return row, version
    course_access(version["course_id"])
    if user["role"] == "student" and row["student_id"] != user["id"]:
        raise ApiError(404, "NOT_FOUND", "Submission not found")
    return row, version


def _run_detail(db, run):
    suite = db.execute("SELECT * FROM test_suite WHERE id=?", (run["suite_id"],)).fetchone()
    cases = db.execute("SELECT * FROM test_case WHERE suite_id=? ORDER BY id",
                       (run["suite_id"],)).fetchall()
    results = db.execute("SELECT * FROM case_result WHERE run_id=? ORDER BY case_id",
                         (run["id"],)).fetchall()
    return run_json(run, cases, results, suite["version"])


def _submission_payload(db, row):
    latest = db.execute("SELECT * FROM grading_run WHERE submission_id=? ORDER BY id DESC LIMIT 1",
                        (row["id"],)).fetchone()
    effective = db.execute(
        "SELECT * FROM grading_run WHERE submission_id=? AND status IN "
        f"({','.join('?' * len(EFFECTIVE_STATUSES))}) ORDER BY id DESC LIMIT 1",
        (row["id"], *EFFECTIVE_STATUSES)).fetchone()
    return submission_json(row,
                           _run_detail(db, latest) if latest else None,
                           _run_detail(db, effective) if effective else None)


@bp.get("/submissions/<int:submission_id>")
def submission_detail(submission_id):
    db = get_db()
    row, _version = _load_submission(db, submission_id)
    return result(_submission_payload(db, row))


@bp.get("/submissions/<int:submission_id>/runs")
def submission_runs(submission_id):
    db = get_db()
    row, _version = _load_submission(db, submission_id)
    page, size = page_args()
    total = db.execute("SELECT COUNT(*) FROM grading_run WHERE submission_id=?",
                       (row["id"],)).fetchone()[0]
    runs = db.execute("SELECT * FROM grading_run WHERE submission_id=? ORDER BY id DESC "
                      "LIMIT ? OFFSET ?", (row["id"], size, (page - 1) * size)).fetchall()
    return paged([_run_detail(db, run) for run in runs], total, page, size)


@bp.get("/submissions/<int:submission_id>/file")
def submission_file(submission_id):
    db = get_db()
    row, _version = _load_submission(db, submission_id)
    file_row = db.execute("SELECT * FROM file_object WHERE id=?", (row["file_id"],)).fetchone()
    path = Path(current_app.config["UPLOAD_ROOT"]) / file_row["storage_key"]
    if not path.is_file():
        raise ApiError(404, "NOT_FOUND", "Submission file is missing")
    # 强制附件下载，不内联 XML。
    return send_file(path, as_attachment=True, download_name=row["filename"] or "submission.circ",
                     mimetype="application/octet-stream")


@bp.get("/grading-runs/<int:run_id>")
def grading_run_detail(run_id):
    db = get_db()
    run = db.execute("SELECT * FROM grading_run WHERE id=?", (run_id,)).fetchone()
    if not run:
        raise ApiError(404, "NOT_FOUND", "Grading run not found")
    submission = db.execute("SELECT * FROM submission WHERE id=?",
                            (run["submission_id"],)).fetchone()
    version = version_row(db, submission["experiment_version_id"])
    user = require_user()
    course_access(version["course_id"])
    if user["role"] == "student" and submission["student_id"] != user["id"]:
        raise ApiError(404, "NOT_FOUND", "Grading run not found")
    return result(_run_detail(db, run))


@bp.get("/courses/<int:course_id>/submissions")
def course_submissions(course_id):
    user = require_user()
    _, role = course_access(course_id)
    page, size = page_args()
    where, params = ["s.experiment_version_id=v.id", "e.id=v.experiment_id", "e.course_id=?"], [course_id]
    if role == "student":
        where.append("s.student_id=?")
        params.append(user["id"])
    for argument, column in (("experiment_id", "v.experiment_id"), ("student_id", "s.student_id")):
        if request.args.get(argument):
            if role == "student" and argument == "student_id":
                raise ApiError(403, "FORBIDDEN", "Students cannot filter by student")
            where.append(f"{column}=?")
            params.append(positive_int(request.args[argument], argument))
    if request.args.get("status"):
        where.append("s.id IN (SELECT submission_id FROM grading_run WHERE status=?)")
        params.append(request.args["status"])
    clause = "WHERE " + " AND ".join(where)
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM submission s, experiment_version v, experiment e "
                       f"{clause}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT s.* FROM submission s, experiment_version v, experiment e {clause} "
        "ORDER BY s.id DESC LIMIT ? OFFSET ?", (*params, size, (page - 1) * size)).fetchall()
    return paged([_submission_payload(db, row) for row in rows], total, page, size)


# ---------- 教师重评 / 管理员重试 ----------

@bp.post("/submissions/<int:submission_id>/regrades")
def regrade_submission(submission_id):
    user = require_user()
    key = attempt_model.idempotency_key(request.headers.get("Idempotency-Key"))
    data = body(("reason",), ("test_suite_id",))
    reason = text_field(data["reason"], "reason", maximum=500)
    with write() as db:
        row, version = _load_submission(db, submission_id, teacher=True)
        course_access(version["course_id"], teacher=True)
        binding = db.execute("SELECT * FROM experiment_grading WHERE experiment_version_id=?",
                             (row["experiment_version_id"],)).fetchone()
        if data.get("test_suite_id"):
            suite = db.execute(
                "SELECT * FROM test_suite WHERE id=? AND experiment_version_id=? AND status='published'",
                (positive_int(data["test_suite_id"], "test_suite_id"),
                 row["experiment_version_id"])).fetchone()
            if not suite:
                raise _bad("test_suite_id must be a published suite of this experiment version")
        else:
            if not binding:
                raise ApiError(409, "STATE_CONFLICT", "No active test suite for regrade")
            suite = db.execute("SELECT * FROM test_suite WHERE id=?",
                               (binding["active_suite_id"],)).fetchone()
        # 重评目标必须同 experiment_version_id，跨实验拒绝（R03）。
        if suite["experiment_version_id"] != row["experiment_version_id"]:
            raise _bad("regrade suite must belong to the same experiment version")
        request_hash = hashlib.sha256(
            f"{submission_id}:{suite['id']}".encode()).hexdigest()
        replayed = attempt_model.replay(db, user["id"], key, request_hash, stamp(now()),
                                        operation=OPERATION_REGRADE)
        if replayed:
            from flask import Response
            return Response(replayed["response_json"], status=replayed["response_status"],
                            mimetype="application/json")
        active = db.execute(
            "SELECT COUNT(*) FROM grading_run WHERE submission_id=? AND status IN "
            "('queued','running')", (submission_id,)).fetchone()[0]
        if active:
            raise ApiError(409, "STATE_CONFLICT", "A run is already active for this submission")
        profile = _profile_of(db, row["experiment_version_id"])
        run_id = db.execute(
            "INSERT INTO grading_run(submission_id,suite_id,engine_version,jar_sha256,status,"
            "total_count,reason,profile_snapshot_json,profile_sha256,suite_sha256,created_at) "
            "VALUES(?,?,?,?, 'queued',?,?,?,?,?,?)",
            (submission_id, suite["id"], profile["engine_version"], profile["jar_sha256"],
             db.execute("SELECT COUNT(*) FROM test_case WHERE suite_id=?",
                        (suite["id"],)).fetchone()[0], reason,
             json.dumps(_profile_json(profile), sort_keys=True),
             profile["canonical_sha256"], suite["content_sha256"], stamp())).lastrowid
        audit("grading.regrade", "grading_run", run_id,
              after={"submission_id": submission_id, "suite_id": suite["id"], "reason": reason})
        payload = {"submission_id": submission_id, "run_id": run_id, "status": "queued"}
        response = jsonify(data=payload, request_id=request_id())
        attempt_model.save_response(db, user["id"], key, request_hash, run_id,
                                    response, 202, operation=OPERATION_REGRADE,
                                    resource_type="grading_run")
    return response, 202


@bp.get("/admin/grading-runs")
def admin_runs():
    require_admin()
    page, size = page_args()
    status = request.args.get("status")
    where, params = ("WHERE status=?", [status]) if status else ("", [])
    if status and status not in ("queued", "running", "accepted", "wrong_answer", "timeout",
                                 "resource_limit", "invalid_circuit", "system_error"):
        raise _bad("Invalid status")
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM grading_run {where}", params).fetchone()[0]
    runs = db.execute(f"SELECT * FROM grading_run {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                      (*params, size, (page - 1) * size)).fetchall()
    return paged([dict(run) for run in runs], total, page, size)


@bp.post("/admin/grading-runs/<int:run_id>/retry")
def admin_retry(run_id):
    user = require_admin()
    data = body(("reason",))
    reason = text_field(data["reason"], "reason", maximum=500)
    with write() as db:
        run = db.execute("SELECT * FROM grading_run WHERE id=?", (run_id,)).fetchone()
        if not run:
            raise ApiError(404, "NOT_FOUND", "Grading run not found")
        if run["status"] != "system_error":
            raise ApiError(409, "STATE_CONFLICT", "Only system_error runs can be retried")
        # retry_of 形成有界链：根任务算 0 次重试，最多 2 次。
        depth, cursor = 0, run
        while cursor["retry_of"]:
            cursor = db.execute("SELECT * FROM grading_run WHERE id=?",
                                (cursor["retry_of"],)).fetchone()
            depth += 1
            if depth >= 2:
                raise ApiError(409, "STATE_CONFLICT", "Retry chain limit reached")
        active = db.execute(
            "SELECT COUNT(*) FROM grading_run WHERE submission_id=? AND status IN "
            "('queued','running')", (run["submission_id"],)).fetchone()[0]
        if active:
            raise ApiError(409, "STATE_CONFLICT", "A run is already active for this submission")
        new_run = db.execute(
            "INSERT INTO grading_run(submission_id,suite_id,engine_version,jar_sha256,status,"
            "total_count,reason,retry_of,profile_snapshot_json,profile_sha256,suite_sha256,"
            "created_at) VALUES(?,?,?,?, 'queued',?,?,?,?,?,?,?)",
            (run["submission_id"], run["suite_id"], run["engine_version"], run["jar_sha256"],
             run["total_count"], reason, run["id"], run["profile_snapshot_json"],
             run["profile_sha256"], run["suite_sha256"], stamp())).lastrowid
        audit("grading.admin_retry", "grading_run", new_run,
              after={"retry_of": run_id, "reason": reason}, actor_id=user["id"])
        payload = {"run_id": new_run, "status": "queued", "retry_of": run_id}
    return result(payload, 202)
