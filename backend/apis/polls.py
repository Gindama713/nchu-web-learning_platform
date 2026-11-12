"""课堂即时投票接口。

老师在一节进行中的考勤任务里发起单选/多选/判断题，已签到的学生投票，老师看分布与对错。
权限：发起/结束/看详细结果 = 课程教师；投票 = 该任务里已签到的学生。
"""

from flask import Blueprint, request

from backend.models import poll as model
from backend.shared.api import ApiError, body, page_args, paged, positive_int, result, text_field
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db, write

bp = Blueprint("polls", __name__)


def teacher_course(course_id):
    """发起/结束/看结果都要求是这门课的教师。"""
    course_access(course_id, teacher=True)
    return require_user()


def load(poll_id, teacher=False):
    row = model.find(get_db(), poll_id)
    course_access(row["course_id"], teacher=teacher)
    return row


def is_teacher(poll):
    _course, role = course_access(poll["course_id"])
    return role == "teacher"


def render(poll, viewer_teacher, student_id=None):
    """学生视角：投票前不给分布，投完才给；老师视角：全都给。"""
    data = model.response(get_db(), poll)
    if viewer_teacher:
        data["can_vote"] = False
        data["reason"] = None
        return data
    can_vote, reason = model.eligibility(get_db(), poll, student_id)
    mine = model.my_choices(get_db(), poll["id"], student_id)
    data["my_option_ids"] = mine
    data["can_vote"] = can_vote and not mine and data["open"]
    if mine:
        data["reason"] = "ALREADY_VOTED"
    elif not data["open"]:
        data["reason"] = "POLL_CLOSED"
    elif not can_vote:
        data["reason"] = reason
    else:
        data["reason"] = None
    # 投完之后（或投票已结束）才把分布与正确选项放出来，避免从众
    if mine or not data["open"]:
        data["counts"] = model.results(get_db(), poll)["counts"]
        if data["has_correct"]:
            data["correct_option_ids"] = [option["id"] for option in model.option_rows(get_db(), poll["id"])
                                          if option["is_correct"]]
    return data


@bp.post("/courses/<int:course_id>/polls")
def create_poll(course_id):
    data = body(required=("task_id", "title", "type"),
                allowed=("options", "max_choices", "anonymous", "correct_ordinals"))
    teacher = teacher_course(course_id)
    task_id = positive_int(data["task_id"], "task_id")
    title = text_field(data["title"], "title", 1, 200)
    kind = data["type"]
    options = data.get("options") or []
    if not isinstance(options, list):
        raise ApiError(422, "VALIDATION_ERROR", "options 需要是数组")
    anonymous = data.get("anonymous", True)
    if not isinstance(anonymous, bool):
        raise ApiError(422, "VALIDATION_ERROR", "anonymous 需要是布尔值")
    max_choices = data.get("max_choices")
    if max_choices is not None:
        max_choices = positive_int(max_choices, "max_choices")
    correct = data.get("correct_ordinals") or []
    if not isinstance(correct, list):
        raise ApiError(422, "VALIDATION_ERROR", "correct_ordinals 需要是数组")
    correct = [positive_int(value, "correct_ordinals") for value in correct]

    with write() as db:
        task = db.execute("SELECT * FROM attendance_task WHERE id=? AND course_id=?",
                          (task_id, course_id)).fetchone()
        if not task:
            raise ApiError(404, "NOT_FOUND", "考勤任务不存在")
        if task["status"] != "open":
            raise ApiError(409, "STATE_CONFLICT", "只能在进行中的考勤任务里发起投票")
        poll_id = model.create(db, course_id, task_id, title, kind, options, max_choices,
                               anonymous, correct, teacher["id"])
        row = model.find(db, poll_id)
    return result(render(row, True), 201)


@bp.get("/courses/<int:course_id>/polls")
def list_polls(course_id):
    user = require_user()
    course_access(course_id)
    page, size = page_args()
    want = request.args.get("status", "all")
    if want not in ("all", "open", "closed"):
        raise ApiError(400, "VALIDATION_ERROR", "status 取值无效")
    db = get_db()
    sql = "SELECT p.* FROM poll p WHERE p.course_id=?"
    params = [course_id]
    if want != "all":
        sql += " AND p.status=?"
        params.append(want)
    total = db.execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()[0]
    rows = db.execute(sql + " ORDER BY p.id DESC LIMIT ? OFFSET ?",
                      [*params, size, (page - 1) * size]).fetchall()
    items = []
    for row in rows:
        item = model.response(db, row)
        if user["role"] == "student":
            mine = model.my_choices(db, row["id"], user["id"])
            can_vote, reason = model.eligibility(db, row, user["id"])
            item["my_option_ids"] = mine
            item["can_vote"] = can_vote and not mine and item["open"]
            if mine:
                item["reason"] = "ALREADY_VOTED"
            elif not item["open"]:
                item["reason"] = "POLL_CLOSED"
            elif not can_vote:
                item["reason"] = reason
            else:
                item["reason"] = None
        items.append(item)
    return paged(items, total, page, size)


@bp.get("/polls/<int:poll_id>")
def get_poll(poll_id):
    user = require_user()
    row = load(poll_id)
    return result(render(row, user["role"] == "teacher", user["id"]))


@bp.post("/polls/<int:poll_id>/ballots")
def vote(poll_id):
    data = body(required=("option_ids",))
    user = require_user()
    row = model.find(get_db(), poll_id)
    _course, role = course_access(row["course_id"])
    if role != "student":
        raise ApiError(403, "FORBIDDEN", "教师不能投票")
    option_ids = data["option_ids"]
    if not isinstance(option_ids, list) or not option_ids:
        raise ApiError(422, "EMPTY_CHOICE", "至少选一项")
    option_ids = [positive_int(value, "option_ids") for value in option_ids]
    with write() as db:
        model.submit(db, row, user["id"], option_ids)
        fresh = model.find(db, poll_id)
    return result(render(fresh, False, user["id"]), 201)


@bp.get("/polls/<int:poll_id>/results")
def poll_results(poll_id):
    user = require_user()
    row = model.find(get_db(), poll_id)
    teacher = is_teacher(row)
    if not teacher:
        # 学生必须先投过：未投就能看分布，等于让后面的人跟着前面的选
        if not model.my_choices(get_db(), poll_id, user["id"]):
            raise ApiError(403, "FORBIDDEN", "投票之后才能看结果")
    data = model.results(get_db(), row)
    data["poll"] = model.response(get_db(), row)
    if teacher:
        data["unvoted"] = model.unvoted(get_db(), row)
        data["details"] = detail_rows(row) if not row["anonymous"] else []
    return result(data)


def detail_rows(poll):
    """逐人明细：实名投票时才给老师，匿名投票只给聚合与未投名单。"""
    rows = get_db().execute(
        "SELECT u.id AS student_id,u.name,u.student_no,b.submitted_at FROM poll_ballot b "
        "JOIN user u ON u.id=b.student_id WHERE b.poll_id=? ORDER BY b.submitted_at",
        (poll["id"],)).fetchall()
    labels = {option["id"]: option["label"] for option in model.option_rows(get_db(), poll["id"])}
    correct = {option["id"] for option in model.option_rows(get_db(), poll["id"]) if option["is_correct"]}
    items = []
    for row in rows:
        picked = [choice["option_id"] for choice in get_db().execute(
            "SELECT option_id FROM poll_choice c JOIN poll_ballot b ON b.id=c.ballot_id "
            "WHERE b.poll_id=? AND b.student_id=?", (poll["id"], row["student_id"]))]
        items.append({
            "student_id": row["student_id"], "name": row["name"], "student_no": row["student_no"],
            "submitted_at": row["submitted_at"],
            "labels": [labels[option_id] for option_id in picked if option_id in labels],
            "correct": (set(picked) == correct) if correct else None,
        })
    return items


@bp.post("/polls/<int:poll_id>/close")
def close_poll(poll_id):
    require_user()
    row = load(poll_id, teacher=True)
    with write() as db:
        model.close(db, row)
        fresh = model.find(db, poll_id)
    return result(render(fresh, True))
