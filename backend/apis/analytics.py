"""SPEC-010A: immutable attendance/performance snapshots."""

import csv
import io
import json
import math
from datetime import timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from flask import Blueprint, make_response, request

from backend.apis import knowledge_analytics
from backend.shared.api import (
    ApiError,
    date_range,
    now,
    parse_time,
    positive_int,
    result,
    stamp,
)
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db, write

bp = Blueprint("analytics", __name__)
VERSION = "attendance-performance-v1"
METRIC_KEYS = ("expected_count", "present_count", "late_count", "leave_count", "absent_count",
               "attendance_rate", "performance_mean_percentage", "performance_correlation",
               "correlation_reason", "candidate_count", "paired_count", "missing_performance_count",
               "selected_paper_ids")


@bp.after_request
def no_store(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


def selected_ids():
    raw = request.args.getlist("performance_paper_ids")
    if not raw:
        return None
    if len(raw) > 100:
        raise ApiError(400, "VALIDATION_ERROR", "At most 100 performance_paper_ids")
    ids = [positive_int(value, "performance_paper_ids") for value in raw]
    if len(set(ids)) != len(ids):
        raise ApiError(400, "VALIDATION_ERROR", "Duplicate performance_paper_ids")
    return ids


def model_ready(db):
    names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"paper", "paper_item", "attempt"} <= names:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", "Assessment tables are not installed")


def facts(db, course_id, start, end, cutoff, papers_filter):
    """Read everything under one SQLite read transaction; returned facts are immutable inputs."""
    model_ready(db)
    db.execute("BEGIN")
    try:
        if papers_filter is not None:
            marks = ",".join("?" for _ in papers_filter)
            valid = db.execute(f"SELECT id FROM paper WHERE id IN ({marks}) AND course_id=? "
                               "AND status='published'", (*papers_filter, course_id)).fetchall()
            if len(valid) != len(papers_filter):
                raise ApiError(404, "NOT_FOUND", "Paper not found")
        tasks = [dict(row) for row in db.execute(
            "SELECT id,start_at FROM attendance_task WHERE course_id=? AND status='closed' "
            "AND start_at>=? AND start_at<? AND updated_at<=? ORDER BY id",
            (course_id, start, end, cutoff))]
        attendance = [dict(row) for row in db.execute(
            "SELECT t.id task_id,t.start_at,p.student_id,COALESCE(r.status,'absent') status "
            "FROM attendance_task t JOIN attendance_participant p ON p.task_id=t.id "
            "LEFT JOIN attendance_record r ON r.task_id=t.id AND r.student_id=p.student_id "
            "WHERE t.course_id=? AND t.status='closed' AND t.start_at>=? AND t.start_at<? "
            "AND t.updated_at<=? ORDER BY t.id,p.student_id", (course_id, start, end, cutoff))]
        paper_sql = ("SELECT p.id,p.start_at,p.kind,COALESCE(SUM(i.points_hundredths),0) total_points "
                     "FROM paper p JOIN paper_item i ON i.paper_id=p.id "
                     "WHERE p.course_id=? AND p.status='published' AND p.kind IN ('homework','exam','quiz') "
                     "AND p.start_at>=? AND p.start_at<? GROUP BY p.id ORDER BY p.id")
        papers = [dict(row) for row in db.execute(paper_sql, (course_id, start, end))]
        if papers_filter is not None:
            papers = [paper for paper in papers if paper["id"] in papers_filter]
        attempts = []
        if papers:
            marks = ",".join("?" for _ in papers)
            attempts = [dict(row) for row in db.execute(
                f"SELECT id,paper_id,student_id,status,score_hundredths FROM attempt "
                f"WHERE paper_id IN ({marks}) ORDER BY id", [paper["id"] for paper in papers])]
        db.execute("COMMIT")
        return {"tasks": tasks, "attendance": attendance, "papers": papers, "attempts": attempts}
    except BaseException:
        db.execute("ROLLBACK")
        raise


def interval_metrics(snapshot, start, end, subject=None):
    attendance = [row for row in snapshot["attendance"] if start <= row["start_at"] < end and
                  (subject is None or row["student_id"] == subject)]
    papers = {row["id"]: row for row in snapshot["papers"] if start <= row["start_at"] < end and
              row["total_points"] > 0}
    attempts = [row for row in snapshot["attempts"] if row["paper_id"] in papers and
                row["status"] == "graded" and row["score_hundredths"] is not None and
                (subject is None or row["student_id"] == subject)]
    frame = pd.DataFrame(attendance, columns=["student_id", "status"])
    counts = {status: int((frame["status"] == status).sum()) for status in
              ("present", "late", "leave", "absent")}
    expected = len(frame)
    by_student = frame.assign(attended=frame["status"].isin(("present", "late")).astype(int))
    grouped = by_student.groupby("student_id", sort=True)["attended"].agg(["sum", "count"])
    grades = pd.DataFrame(
        [{"student_id": row["student_id"], "percentage": 100 * row["score_hundredths"] /
          papers[row["paper_id"]]["total_points"]} for row in attempts],
        columns=["student_id", "percentage"],
    ).groupby("student_id", sort=True)["percentage"].mean()
    paired = [(float(grouped.loc[student_id, "sum"]) / float(grouped.loc[student_id, "count"]),
               float(grades.loc[student_id])) for student_id in grouped.index if student_id in grades.index]
    reason, correlation = "personal_scope" if subject is not None else "insufficient_pairs", None
    if subject is None and len(paired) >= 3:
        xs, ys = zip(*paired, strict=True)
        x_mean, y_mean = sum(xs) / len(xs), sum(ys) / len(ys)
        dx, dy = [x - x_mean for x in xs], [y - y_mean for y in ys]
        xx, yy = sum(x * x for x in dx), sum(y * y for y in dy)
        if xx <= 1e-12 or yy <= 1e-12:
            reason = "zero_variance"
        else:
            correlation = round(max(-1.0, min(1.0, sum(x * y for x, y in zip(dx, dy, strict=True)) /
                                                   math.sqrt(xx * yy))), 6)
            reason = "ok"
    return {
        **{f"{status}_count": count for status, count in counts.items()},
        "expected_count": expected,
        "attendance_rate": round((counts["present"] + counts["late"]) / expected, 6) if expected else None,
        "performance_mean_percentage": round(sum(y for _, y in paired) / len(paired), 2) if paired else None,
        "performance_correlation": correlation,
        "correlation_reason": reason,
        "candidate_count": len(grouped) if subject is None else None,
        "paired_count": len(paired) if subject is None else None,
        "missing_performance_count": len(grouped) - len(paired) if subject is None else None,
        "selected_paper_ids": sorted(papers),
    }


def week_series(snapshot, start, end, subject):
    shanghai = ZoneInfo("Asia/Shanghai")
    cursor = parse_time(start, "from")
    stop = parse_time(end, "to")
    rows = []
    while cursor < stop:
        local = cursor.astimezone(shanghai)
        next_monday = (local - timedelta(days=local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0) + timedelta(days=7)
        boundary = min(stop, next_monday.astimezone(cursor.tzinfo))
        rows.append({"period_start": stamp(cursor), "period_end": stamp(boundary),
                     "metrics": interval_metrics(snapshot, stamp(cursor), stamp(boundary), subject)})
        cursor = boundary
    return rows


def permitted_run(course_id, run_id):
    user = require_user()
    course_access(course_id)
    row = get_db().execute("SELECT * FROM analysis_run WHERE id=? AND course_id=? AND creator_id=? "
                           "AND kind IN ('attendance','knowledge')", (run_id, course_id, user["id"])).fetchone()
    if not row:
        raise ApiError(404, "NOT_FOUND", "Analysis snapshot not found")
    if user["role"] == "student" and (row["scope"] != "self" or row["subject_student_id"] != user["id"]):
        raise ApiError(404, "NOT_FOUND", "Analysis snapshot not found")
    if user["role"] == "teacher" and row["scope"] == "self":
        raise ApiError(404, "NOT_FOUND", "Analysis snapshot not found")
    if row['kind'] == 'knowledge':
        knowledge_analytics.authorize(course_id, row['subject_student_id'])
    return row


@bp.get("/courses/<int:course_id>/analytics")
def analytics(course_id):
    if 'analysis_run_id' in request.args:
        if set(request.args) != {"analysis_run_id"}:
            raise ApiError(400, "VALIDATION_ERROR", "Snapshot read cannot mix filters")
        if len(request.args.getlist('analysis_run_id')) != 1:
            raise ApiError(400, 'VALIDATION_ERROR', 'Duplicate snapshot ID')
        row = permitted_run(course_id, knowledge_analytics.identifier(request.args["analysis_run_id"], "analysis_run_id"))
        return result(json.loads(row["result_json"]))
    if request.args.get('dimension') == 'knowledge':
        return knowledge_analytics.create(course_id, request.args)
    if request.args.get("dimension") != "attendance":
        raise ApiError(400, "VALIDATION_ERROR", "Only attendance dimension is available")
    if set(request.args) - {"dimension", "from", "to", "student_id", "performance_paper_ids"}:
        raise ApiError(400, "VALIDATION_ERROR", "Invalid attendance filters")
    user = require_user()
    _, role = course_access(course_id)
    requested = positive_int(request.args["student_id"], "student_id") if request.args.get("student_id") else None
    if role == "student" and requested not in (None, user["id"]):
        raise ApiError(403, "FORBIDDEN", "Only own analytics are visible")
    subject = user["id"] if role == "student" else requested
    if requested and role == "teacher" and not get_db().execute(
        "SELECT 1 FROM course_member WHERE course_id=? AND user_id=? AND member_role='student'",
        (course_id, requested)).fetchone():
        raise ApiError(404, "NOT_FOUND", "Student not found")
    start, end = date_range()
    if start == end:
        raise ApiError(400, "VALIDATION_ERROR", "Empty date range")
    paper_ids = selected_ids()
    cutoff = stamp(now())
    snapshot = facts(get_db(), course_id, start, end, cutoff, paper_ids)
    metrics = interval_metrics(snapshot, start, end, subject)
    generated = stamp()
    data = {"dimension": "attendance", "sample_size": metrics["candidate_count"] if subject is None else
            int(metrics["expected_count"] > 0), "metrics": metrics,
            "series": week_series(snapshot, start, end, subject), "source_until": cutoff,
            "population_basis": "closed_task_frozen_participants", "unit": {"attendance_rate": "ratio",
            "performance_mean_percentage": "percent", "performance_correlation": "unitless"},
            "warnings": ["相关性不代表因果，不自动扣分"], "algorithm_version": VERSION,
            "generated_at": generated}
    scope = "class" if subject is None else "self" if role == "student" else "student"
    with write() as db:
        course_access(course_id, teacher=role == "teacher")
        cursor = db.execute("INSERT INTO analysis_run(course_id,creator_id,scope,subject_student_id,kind,"
                            "algorithm_version,parameters_json,source_until,generated_at,sample_size,result_json,"
                            "input_snapshot_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (course_id, user["id"], scope, subject, "attendance", VERSION,
                             json.dumps({"from": start, "to": end, "selected_paper_ids": metrics["selected_paper_ids"]}),
                             cutoff, generated, data["sample_size"], json.dumps(data, ensure_ascii=False),
                             json.dumps(snapshot, ensure_ascii=False), generated))
        data["analysis_run_id"] = cursor.lastrowid
        db.execute("UPDATE analysis_run SET result_json=? WHERE id=?",
                   (json.dumps(data, ensure_ascii=False), cursor.lastrowid))
    return result(data)


@bp.get("/courses/<int:course_id>/analytics/export")
def export(course_id):
    if set(request.args) != {"analysis_run_id", "format"} or request.args["format"] != "csv":
        raise ApiError(400, "VALIDATION_ERROR", "Expected analysis_run_id and format=csv")
    _, role = course_access(course_id)
    if role != "teacher":
        raise ApiError(403, "FORBIDDEN", "Course teacher required")
    row = permitted_run(course_id, positive_int(request.args["analysis_run_id"], "analysis_run_id"))
    if row['kind'] != 'attendance':
        raise ApiError(503, 'DEPENDENCY_UNAVAILABLE', 'Knowledge CSV is not available yet')
    data = json.loads(row["result_json"])
    stream = io.StringIO()
    writer = csv.writer(stream)
    for key in ("analysis_run_id", "source_until", "generated_at", "algorithm_version"):
        writer.writerow([key, data[key]])
    writer.writerow(["period_start", "period_end", *METRIC_KEYS])
    for item in data["series"]:
        writer.writerow([item["period_start"], item["period_end"],
                         *(json.dumps(item["metrics"][key], ensure_ascii=False) if isinstance(item["metrics"][key], list)
                           else item["metrics"][key] for key in METRIC_KEYS)])
    response = make_response("\ufeff" + stream.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="attendance-{row["id"]}.csv"'
    return response
