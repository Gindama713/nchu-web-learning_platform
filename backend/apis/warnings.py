"""SPEC-014: evidence-based rules and reproducible KMeans warnings."""

import hashlib
import json

import numpy as np
import sklearn
from flask import Blueprint, request
from sklearn.cluster import KMeans

from backend.shared.api import (
    ApiError,
    audit,
    body,
    date_range,
    page_args,
    paged,
    result,
    stamp,
    text_field,
)
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db, write

bp = Blueprint("warnings", __name__)
VERSION = "warning-kmeans-v1"
PARAMS = {"n_clusters": 2, "random_state": 42, "n_init": 10, "max_iter": 300}


def analyze(rows):
    """Rows contain only recorded facts; absent denominators stay absent."""
    rows = sorted(rows, key=lambda item: item["student_id"])
    eligible = []
    reasons = {}
    for row in rows:
        student_id = row["student_id"]
        objective = row["correct"] / row["answers"] if row["answers"] else None
        experiment = row["completed"] / row["due"] if row["due"] else None
        attendance = row["attended"] / row["expected"] if row["expected"] else None
        evidence = []
        if row["answers"] >= 5 and objective < 0.6:
            evidence.append({"code": "LOW_OBJECTIVE_RATE", "value": round(objective, 6),
                             "sample_size": row["answers"]})
        if len(row["last_two"]) == 2 and all(status in ("late", "absent") for status in row["last_two"]):
            evidence.append({"code": "RECENT_ATTENDANCE", "statuses": row["last_two"], "sample_size": 2})
        reasons[student_id] = evidence
        if row["answers"] >= 5 and objective is not None and experiment is not None and attendance is not None:
            eligible.append({"student_id": student_id, "features": [objective, experiment, attendance],
                             "denominators": [row["answers"], row["due"], row["expected"]]})
    model_status = "insufficient_data"
    centers, labels = [], []
    if len(eligible) >= 10 and len({tuple(item["features"]) for item in eligible}) >= 2:
        model = KMeans(**PARAMS).fit(np.asarray([item["features"] for item in eligible], dtype=float))
        centers = model.cluster_centers_.tolist()
        labels = model.labels_.tolist()
        model_status = "clustered"
        means = [float(np.mean(center)) for center in centers]
        weak = None if abs(means[0] - means[1]) <= 1e-12 else int(np.argmin(means))
        if weak is not None and means[weak] < 0.6:
            for item, label in zip(eligible, labels, strict=True):
                if label == weak and min(item["features"]) < 0.6:
                    reasons[item["student_id"]].append({"code": "RELATIVE_WEAK_CLUSTER",
                                                        "cluster": int(label), "center": centers[weak],
                                                        "sample_size": len(eligible)})
    return {"model_status": model_status, "sample_size": len(eligible), "centers": centers,
            "labels": [{"student_id": item["student_id"], "label": int(label)}
                       for item, label in zip(eligible, labels, strict=False)],
            "inputs": rows, "eligible_inputs": eligible, "parameters": {**PARAMS, "sklearn_version": sklearn.__version__},
            "warnings": [{"student_id": key, "reasons": value} for key, value in reasons.items() if value]}


def required_tables(db):
    required = {"paper", "paper_item", "attempt", "answer", "question", "question_version", "practice_attempt",
                "experiment_version", "experiment_participant", "wiring_attempt", "submission", "grading_run"}
    names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not required <= names:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", "Assessment and experiment facts are not installed")


def read_facts(db, course_id, start, end, cutoff):
    required_tables(db)
    db.execute("BEGIN")
    try:
        members = [row[0] for row in db.execute(
            "SELECT m.user_id FROM course_member m JOIN user u ON u.id=m.user_id "
            "WHERE m.course_id=? AND m.member_role='student' AND m.active=1 "
            "AND u.active=1 AND u.role='student' ORDER BY m.user_id", (course_id,))]
        facts = {student_id: {"student_id": student_id, "answers": 0, "correct": 0,
                              "due": 0, "completed": 0, "expected": 0, "attended": 0,
                              "last_two": []} for student_id in members}
        paper_answers = [dict(row) for row in db.execute(
            "SELECT a.id,at.student_id,a.score_hundredths,pi.points_hundredths "
            "FROM answer a JOIN attempt at ON at.id=a.attempt_id "
            "JOIN paper p ON p.id=at.paper_id "
            "JOIN paper_item pi ON pi.paper_id=p.id AND pi.question_version_id=a.question_version_id "
            "JOIN question_version qv ON qv.id=a.question_version_id "
            "WHERE p.course_id=? AND p.status='published' AND p.start_at>=? AND p.start_at<? "
            "AND at.submitted_at<=? AND a.answered=1 AND qv.type<>'short' "
            "ORDER BY a.id", (course_id, start, end, cutoff))]
        for item in paper_answers:
            row = facts.get(item["student_id"])
            if row is not None and item["score_hundredths"] is not None:
                row["answers"] += 1
                row["correct"] += int(item["score_hundredths"] == item["points_hundredths"])
        practice = [dict(row) for row in db.execute(
            "SELECT pa.id,pa.student_id,pa.correct FROM practice_attempt pa "
            "JOIN question_version qv ON qv.id=pa.question_version_id "
            "JOIN question q ON q.id=qv.question_id WHERE q.course_id=? "
            "AND pa.created_at>=? AND pa.created_at<? AND pa.created_at<=? "
            "AND qv.type<>'short' ORDER BY pa.id", (course_id, start, end, cutoff))]
        for item in practice:
            row = facts.get(item["student_id"])
            if row is not None:
                row["answers"] += 1
                row["correct"] += int(item["correct"])
        attendance = [dict(row) for row in db.execute(
            "SELECT t.id,t.start_at,ap.student_id,COALESCE(ar.status,'absent') status "
            "FROM attendance_task t JOIN attendance_participant ap ON ap.task_id=t.id "
            "LEFT JOIN attendance_record ar ON ar.task_id=t.id AND ar.student_id=ap.student_id "
            "WHERE t.course_id=? AND t.status='closed' AND t.start_at>=? AND t.start_at<? "
            "AND t.updated_at<=? ORDER BY ap.student_id,t.start_at,t.id", (course_id, start, end, cutoff))]
        for item in attendance:
            row = facts.get(item["student_id"])
            if row is not None:
                row["expected"] += 1
                row["attended"] += int(item["status"] in ("present", "late"))
                row["last_two"].append(item["status"])
        for row in facts.values():
            row["last_two"] = row["last_two"][-2:]
        due = [dict(row) for row in db.execute(
            "SELECT ev.id,ev.submission_modes_json,ep.student_id FROM experiment_version ev "
            "JOIN experiment e ON e.id=ev.experiment_id "
            "JOIN experiment_participant ep ON ep.experiment_version_id=ev.id "
            "WHERE e.course_id=? AND ev.status='published' AND ev.end_at>=? AND ev.end_at<? "
            "AND ev.end_at<=? ORDER BY ev.id,ep.student_id", (course_id, start, end, cutoff))]
        wiring = {(row["experiment_version_id"], row["student_id"]) for row in db.execute(
            "SELECT experiment_version_id,student_id FROM wiring_attempt "
            "WHERE status='submitted' AND completed=1 AND submitted_at<=?", (cutoff,))}
        submissions = [dict(row) for row in db.execute(
            "SELECT id,experiment_version_id,student_id,created_at FROM submission WHERE created_at<=? "
            "ORDER BY created_at,id", (cutoff,))]
        runs = [dict(row) for row in db.execute(
            "SELECT id,submission_id,status FROM grading_run WHERE status IN "
            "('accepted','wrong_answer','timeout','resource_limit','invalid_circuit') "
            "AND finished_at<=? ORDER BY id", (cutoff,))]
        latest_run = {row["submission_id"]: row for row in runs}
        effective = {}
        for item in submissions:
            run = latest_run.get(item["id"])
            if run:
                effective[item["experiment_version_id"], item["student_id"]] = run["status"] == "accepted"
        for item in due:
            row = facts.get(item["student_id"])
            if row is None:
                continue
            modes = json.loads(item["submission_modes_json"])
            key = (item["id"], item["student_id"])
            row["due"] += 1
            row["completed"] += int(bool(modes) and all((mode == "wiring" and key in wiring) or
                                                        (mode == "circuit" and effective.get(key, False)) for mode in modes))
        db.execute("COMMIT")
        return list(facts.values())
    except BaseException:
        db.execute("ROLLBACK")
        raise


def run_json(row):
    return {"analysis_run_id": row["id"], "status": "completed", "source_until": row["source_until"],
            "sample_size": row["sample_size"], "model_status": row["model_status"],
            "warning_count": get_db().execute("SELECT COUNT(*) FROM warning WHERE analysis_run_id=?",
                                              (row["id"],)).fetchone()[0]}


@bp.post("/courses/<int:course_id>/warning-runs")
def create_run(course_id):
    actor = require_user()
    course_access(course_id, teacher=True)
    key = request.headers.get("Idempotency-Key", "")
    if not 1 <= len(key) <= 128:
        raise ApiError(400, "VALIDATION_ERROR", "Idempotency-Key required")
    if set(request.args) - {"from", "to"}:
        raise ApiError(400, "VALIDATION_ERROR", "Invalid warning-run filters")
    start, end = date_range()
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    parameters = {"from": start, "to": end, "requested_from": request.args.get("from"),
                  "requested_to": request.args.get("to"), "idempotency_key_hash": key_hash}
    db = get_db()
    for previous in db.execute("SELECT * FROM analysis_run WHERE course_id=? AND creator_id=? AND kind='warning'",
                               (course_id, actor["id"])):
        old = json.loads(previous["parameters_json"])
        if old.get("idempotency_key_hash") == key_hash:
            if old.get("requested_from") != parameters["requested_from"] or old.get("requested_to") != parameters["requested_to"]:
                raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Key used for another request")
            return result(run_json(previous), 201)
    cutoff = stamp()
    facts = read_facts(db, course_id, start, end, cutoff)
    output = analyze(facts)
    generated = stamp()
    with write() as db:
        course_access(course_id, teacher=True)
        for previous in db.execute("SELECT * FROM analysis_run WHERE course_id=? AND creator_id=? AND kind='warning'",
                                   (course_id, actor["id"])):
            old = json.loads(previous["parameters_json"])
            if old.get("idempotency_key_hash") == key_hash:
                if old.get("requested_from") != parameters["requested_from"] or old.get("requested_to") != parameters["requested_to"]:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Key used for another request")
                return result(run_json(previous), 201)
        cursor = db.execute("INSERT INTO analysis_run(course_id,creator_id,scope,kind,algorithm_version,"
                            "parameters_json,source_until,generated_at,sample_size,result_json,input_snapshot_json,"
                            "model_status,model_parameters_json,created_at) VALUES(?,?,'class','warning',?,?,?,?,?,?,?,?,?,?)",
                            (course_id, actor["id"], VERSION, json.dumps(parameters), cutoff, generated,
                             output["sample_size"], json.dumps(output, ensure_ascii=False),
                             json.dumps(facts, ensure_ascii=False), output["model_status"],
                             json.dumps(output["parameters"]), generated))
        for item in output["warnings"]:
            db.execute("INSERT INTO warning(analysis_run_id,student_id,reasons_json,status,created_at,updated_at) "
                       "VALUES(?,?,?,'open',?,?)", (cursor.lastrowid, item["student_id"],
                                                    json.dumps(item["reasons"], ensure_ascii=False), generated, generated))
        audit("warning.run", "analysis_run", cursor.lastrowid, after={"warnings": len(output["warnings"])})
        saved = db.execute("SELECT * FROM analysis_run WHERE id=?", (cursor.lastrowid,)).fetchone()
    return result(run_json(saved), 201)


@bp.get("/courses/<int:course_id>/warning-runs")
def list_runs(course_id):
    course_access(course_id, teacher=True)
    page, size = page_args()
    db = get_db()
    where = (course_id,)
    total = db.execute("SELECT COUNT(*) FROM analysis_run WHERE course_id=? AND kind='warning'", where).fetchone()[0]
    rows = db.execute("SELECT * FROM analysis_run WHERE course_id=? AND kind='warning' "
                      "ORDER BY id DESC LIMIT ? OFFSET ?", (*where, size, (page - 1) * size))
    return paged([run_json(row) for row in rows], total, page, size)


@bp.get("/courses/<int:course_id>/warnings")
def list_warnings(course_id):
    course_access(course_id, teacher=True)
    page, size = page_args()
    status = request.args.get("status")
    if status not in (None, "open", "handled"):
        raise ApiError(400, "VALIDATION_ERROR", "Invalid status")
    start, end = date_range()
    db = get_db()
    latest = db.execute("SELECT id,model_status FROM analysis_run WHERE course_id=? AND kind='warning' "
                        "AND generated_at>=? AND generated_at<=? ORDER BY id DESC LIMIT 1",
                        (course_id, start, end)).fetchone()
    if latest is None:
        return paged([], 0, page, size, analysis_run_id=None, model_status="no_run")
    clause = "WHERE w.analysis_run_id=?" + (" AND w.status=?" if status else "")
    params = (latest["id"], status) if status else (latest["id"],)
    total = db.execute("SELECT COUNT(*) FROM warning w " + clause, params).fetchone()[0]
    rows = db.execute("SELECT w.*,a.algorithm_version FROM warning w "
                      "JOIN analysis_run a ON a.id=w.analysis_run_id " + clause +
                      " ORDER BY w.id LIMIT ? OFFSET ?", (*params, size, (page - 1) * size))
    items = []
    for row in rows:
        reasons = json.loads(row["reasons_json"])
        items.append({"id": row["id"], "student_id": row["student_id"], "reasons": reasons,
                      "sample_size": max((reason.get("sample_size", 0) for reason in reasons), default=0),
                      "status": row["status"], "algorithm_version": row["algorithm_version"]})
    return paged(items, total, page, size, analysis_run_id=latest["id"], model_status=latest["model_status"])


@bp.patch("/warnings/<int:warning_id>")
def handle(warning_id):
    actor = require_user()
    data = body(("status", "note"))
    if data["status"] != "handled":
        raise ApiError(400, "VALIDATION_ERROR", "status must be handled")
    note = text_field(data["note"], "note", maximum=500)
    with write() as db:
        row = db.execute("SELECT w.*,a.course_id FROM warning w JOIN analysis_run a "
                         "ON a.id=w.analysis_run_id WHERE w.id=?", (warning_id,)).fetchone()
        if not row:
            raise ApiError(404, "NOT_FOUND", "Warning not found")
        course_access(row["course_id"], teacher=True)
        if row["status"] != "handled":
            db.execute("UPDATE warning SET status='handled',handled_by=?,note=?,updated_at=? WHERE id=?",
                       (actor["id"], note, stamp(), warning_id))
            audit("warning.handle", "warning", warning_id)
        saved = db.execute("SELECT * FROM warning WHERE id=?", (warning_id,)).fetchone()
    return result({"id": warning_id, "student_id": saved["student_id"], "status": saved["status"],
                   "reasons": json.loads(saved["reasons_json"]), "note": saved["note"]})
