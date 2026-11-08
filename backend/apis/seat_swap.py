"""第10周：学生自助换位。

学生在座位图上点一个位置：

- **空位** → `PUT /courses/<id>/me/seat` 直接坐过去；教室是空的、本人还没排座时，
  这一次点击就是首次选座（插 `class_seat` 并补点到快照），不需要谁批准；
- **有人** → `POST /courses/<id>/seat-swaps` 向对方发起申请，对方登录后弹窗答复，
  15 分钟不答复自动作废。

两条约束写在服务端，不只靠前端自觉：

1. 同一时刻一个人最多挂一条 pending 申请 —— 迁移 025 的部分唯一索引兜底，
   应用层先给一句人话错误，并发下索引再拦一次；
2. pending 过了 `expires_at` 自动转 `expired`，本模块每个端点入口都先扫一遍，
   不依赖后台定时任务（演示机上没有 scheduler 也能跑）。

换位成功后**两处一起改**：`class_seat`（课程级排座，后续点到按它生成快照）和该课程
所有 `attendance_seat`（已生成的点到座位图）。只改一处的话，学生下次开会发现座位又变回去了。
"""

from datetime import timedelta

from flask import Blueprint

from backend.apis.classroom import ensure_classroom
from backend.shared.api import (
    ApiError,
    audit,
    body,
    notify,
    now,
    positive_int,
    result,
    stamp,
)
from backend.shared.auth import course_access, require_user
from backend.shared.db import write

bp = Blueprint("seat_swap", __name__)

# 请求有效期：15 分钟。前端倒计时也用这个数，避免两边写死不同值。
SWAP_TTL_MINUTES = 15

SWAP_FIELDS = ("id", "course_id", "requester_id", "target_id", "from_group", "from_seat",
               "to_group", "to_seat", "status", "created_at", "expires_at", "responded_at")


def swap_json(row, **extra):
    data = {key: row[key] for key in SWAP_FIELDS}
    data.update(extra)
    return data


def expire_stale(db):
    """把超时还没答复的申请标成 expired，返回受影响条数。

    每个端点进来先调一次：读接口不能返回已经过期的申请，写接口不能让人去答复一条
    早就该失效的申请。

    扫到的过期是**既成事实**，单独提交掉。否则答复一条过期申请的请求会带着 409 回滚，
    连带把这次扫描也回滚，库里就留下一条永远 pending 的僵尸行（黑盒复验实测到过）。
    提交之后各端点自己的写操作仍然是一个整体，原子性不受影响。
    """
    affected = db.execute(
        "UPDATE seat_swap_request SET status='expired', responded_at=? "
        "WHERE status='pending' AND expires_at<=?", (stamp(), stamp()),
    ).rowcount
    if affected:
        db.commit()
    return affected


def member_seat(db, course_id, student_id):
    """某人在本课程的课程级座位；没排座返回 None。"""
    return db.execute(
        "SELECT s.student_id,s.class_name,s.group_no,s.seat_no,u.name,u.student_no "
        "FROM class_seat s JOIN user u ON u.id=s.student_id "
        "WHERE s.course_id=? AND s.student_id=?", (course_id, student_id)).fetchone()


def seat_holder(db, course_id, group_no, seat_no):
    """(排, 座) 上坐着谁；空位返回 None。位置按全教室唯一处理，不分班。"""
    return db.execute(
        "SELECT student_id FROM class_seat WHERE course_id=? AND group_no=? AND seat_no=?",
        (course_id, group_no, seat_no)).fetchone()


def sync_snapshots(db, course_id, student_id, group_no, seat_no):
    """把新坐标同步到该课程已生成的点到座位快照，否则座位图会停在旧位置。

    教室清空后由学生自助选座时，这个人在快照里还没有行，光 UPDATE 不会有任何效果，
    所以补一段 INSERT：只给「本人是该任务参与者、但还没有快照行」的任务补，
    不会把无关任务的人塞进座位图。
    """
    db.execute(
        "UPDATE attendance_seat SET group_no=?, seat_no=? WHERE student_id=? AND task_id IN "
        "(SELECT id FROM attendance_task WHERE course_id=?)",
        (group_no, seat_no, student_id, course_id),
    )
    db.execute(
        "INSERT INTO attendance_seat(task_id,student_id,group_no,seat_no) "
        "SELECT p.task_id,p.student_id,?,? FROM attendance_participant p "
        "JOIN attendance_task t ON t.id=p.task_id "
        "WHERE t.course_id=? AND p.student_id=? AND NOT EXISTS "
        "(SELECT 1 FROM attendance_seat s WHERE s.task_id=p.task_id AND s.student_id=p.student_id)",
        (group_no, seat_no, course_id, student_id),
    )


def apply_seat(db, course_id, student_id, group_no, seat_no):
    timestamp = stamp()
    updated = db.execute("UPDATE class_seat SET group_no=?, seat_no=?, updated_at=? "
                         "WHERE course_id=? AND student_id=?",
                         (group_no, seat_no, timestamp, course_id, student_id))
    if not updated.rowcount:
        # 教室是空的、学生还没排过座：第一次点空位就是「选座」，插一行而不是报 404。
        class_name = db.execute(
            "SELECT COALESCE(class_name,'未分班') FROM user WHERE id=?", (student_id,)).fetchone()[0]
        db.execute(
            "INSERT INTO class_seat(course_id,student_id,class_name,group_no,seat_no,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (course_id, student_id, class_name, group_no, seat_no, timestamp, timestamp))
    sync_snapshots(db, course_id, student_id, group_no, seat_no)


def swap_positions(db, course_id, first_id, second_id):
    """两人对调座位。

    `class_seat` 上有 UNIQUE(course_id, class_name, group_no, seat_no)，两条 UPDATE
    在中间态会互相撞车，所以先一起删掉再按对调后的坐标插回去，created_at 沿用原值。
    """
    rows = {}
    for student_id in (first_id, second_id):
        row = db.execute("SELECT * FROM class_seat WHERE course_id=? AND student_id=?",
                         (course_id, student_id)).fetchone()
        if not row:
            raise ApiError(409, "SEAT_CHANGED", "其中一方已经不在座位表上了")
        rows[student_id] = row
    first, second = rows[first_id], rows[second_id]
    timestamp = stamp()
    db.execute("DELETE FROM class_seat WHERE course_id=? AND student_id IN (?,?)",
               (course_id, first_id, second_id))
    for student_id, source, target in ((first_id, first, second), (second_id, second, first)):
        db.execute(
            "INSERT INTO class_seat(course_id,student_id,class_name,group_no,seat_no,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (course_id, student_id, source["class_name"], target["group_no"], target["seat_no"],
             source["created_at"], timestamp),
        )
    sync_snapshots(db, course_id, first_id, second["group_no"], second["seat_no"])
    sync_snapshots(db, course_id, second_id, first["group_no"], first["seat_no"])
    return (second["group_no"], second["seat_no"]), (first["group_no"], first["seat_no"])


def cancel_pending_for(db, student_id, keep_id=None):
    """一个人换了座位之后，挂在他名下的 pending 申请坐标都作废了，直接撤掉。"""
    sql = ("UPDATE seat_swap_request SET status='cancelled', responded_at=? "
           "WHERE status='pending' AND (requester_id=? OR target_id=?)")
    params = [stamp(), student_id, student_id]
    if keep_id is not None:
        sql += " AND id<>?"
        params.append(keep_id)
    return db.execute(sql, params).rowcount


def require_student(course_id):
    """换位是学生之间的行为，教师和助教不做这件事。"""
    _course, member_role = course_access(course_id)
    if member_role != "student":
        raise ApiError(403, "FORBIDDEN", "只有学生可以自助换位")
    return require_user()


def load_request(db, course_id, swap_id):
    row = db.execute("SELECT * FROM seat_swap_request WHERE id=? AND course_id=?",
                     (swap_id, course_id)).fetchone()
    if not row:
        raise ApiError(404, "NOT_FOUND", "换位申请不存在")
    return row


@bp.put("/courses/<int:course_id>/me/seat")
def move_to_seat(course_id):
    """坐到空位上。目标位置有人时不要静默顶掉，让前端改走换位申请。

    教室还没排座时，本人第一次点空位算「选座」：插入 class_seat 并补齐点到快照，
    而不是要求先由教师一键排座。
    """
    data = body(required=("group_no", "seat_no"))
    group_no = positive_int(data["group_no"], "group_no")
    seat_no = positive_int(data["seat_no"], "seat_no")
    with write() as db:
        expire_stale(db)
        user = require_student(course_id)
        mine = member_seat(db, course_id, user["id"])
        room = ensure_classroom(db, course_id)
        if group_no > room["rows"] or seat_no > room["cols"]:
            raise ApiError(422, "OUT_OF_RANGE",
                           f"座位超出教室范围：最多 {room['rows']} 排、{room['cols']} 座")
        if mine and mine["group_no"] == group_no and mine["seat_no"] == seat_no:
            return result({"student_id": user["id"], "group_no": group_no, "seat_no": seat_no,
                           "moved": False, "cancelled": 0})
        holder = seat_holder(db, course_id, group_no, seat_no)
        if holder:
            raise ApiError(409, "SEAT_TAKEN", "这个位置已经有人了，点他申请换位")
        cancelled = cancel_pending_for(db, user["id"])
        apply_seat(db, course_id, user["id"], group_no, seat_no)
        audit("seat.move", "course_member", user["id"],
              # 首次选座时还没有旧座位，before 留空，别在这一步把请求打成 500
              before={"group_no": mine["group_no"], "seat_no": mine["seat_no"]} if mine else None,
              after={"course_id": course_id, "group_no": group_no, "seat_no": seat_no})
    return result({"student_id": user["id"], "group_no": group_no, "seat_no": seat_no,
                   "moved": True, "cancelled": cancelled})


@bp.post("/courses/<int:course_id>/seat-swaps")
def create_swap(course_id):
    """向坐在目标位置的同学发起换位申请。"""
    data = body(required=("target_student_id",))
    target_id = positive_int(data["target_student_id"], "target_student_id")
    with write() as db:
        expire_stale(db)
        user = require_student(course_id)
        if target_id == user["id"]:
            raise ApiError(409, "CANNOT_SWAP_SELF", "不用和自己换座位")
        mine = member_seat(db, course_id, user["id"])
        if not mine:
            raise ApiError(404, "NOT_SEATED", "你还没有座位，先找老师排座")
        theirs = member_seat(db, course_id, target_id)
        if not theirs:
            raise ApiError(404, "TARGET_NOT_SEATED", "对方没有排座，换不了")
        pending = db.execute(
            "SELECT id FROM seat_swap_request WHERE requester_id=? AND status='pending'",
            (user["id"],)).fetchone()
        if pending:
            raise ApiError(409, "SWAP_PENDING_EXISTS",
                           "你还有一个换位申请没答复，先撤回或者等它过期")
        incoming = db.execute(
            "SELECT id FROM seat_swap_request WHERE status='pending' AND requester_id=? AND target_id=?",
            (target_id, user["id"])).fetchone()
        if incoming:
            raise ApiError(409, "SWAP_ALREADY_ASKED",
                           "对方正在申请和你换位，直接答复那条就行")

        timestamp = stamp()
        expires_at = stamp(now() + timedelta(minutes=SWAP_TTL_MINUTES))
        cursor = db.execute(
            "INSERT INTO seat_swap_request(course_id,requester_id,target_id,from_group,from_seat,"
            "to_group,to_seat,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,'pending',?,?)",
            (course_id, user["id"], target_id, mine["group_no"], mine["seat_no"],
             theirs["group_no"], theirs["seat_no"], timestamp, expires_at))
        swap_id = cursor.lastrowid
        notify(target_id, course_id, f"{user['name']} 想和你换座位",
               "seat_swap", swap_id, f"seat_swap:{swap_id}")
        audit("seat.swap_request", "seat_swap_request", swap_id,
              after={"course_id": course_id, "target_id": target_id,
                     "from": [mine["group_no"], mine["seat_no"]],
                     "to": [theirs["group_no"], theirs["seat_no"]]})
        row = db.execute("SELECT * FROM seat_swap_request WHERE id=?", (swap_id,)).fetchone()
    return result(swap_json(row, requester_name=user["name"], target_name=theirs["name"],
                            ttl_minutes=SWAP_TTL_MINUTES), status=201)


@bp.get("/courses/<int:course_id>/seat-swaps")
def list_swaps(course_id):
    """我发出的、以及发给我的换位申请（只留 pending 与最近 10 条已结束的）。"""
    with write() as db:
        expired = expire_stale(db)
        course_access(course_id)
        user = require_user()
        outgoing = db.execute(
            "SELECT r.*,u.name AS target_name,u.student_no AS target_no FROM seat_swap_request r "
            "JOIN user u ON u.id=r.target_id WHERE r.course_id=? AND r.requester_id=? "
            "ORDER BY r.id DESC LIMIT 10", (course_id, user["id"])).fetchall()
        incoming = db.execute(
            "SELECT r.*,u.name AS requester_name,u.student_no AS requester_no FROM seat_swap_request r "
            "JOIN user u ON u.id=r.requester_id WHERE r.course_id=? AND r.target_id=? "
            "ORDER BY r.id DESC LIMIT 10", (course_id, user["id"])).fetchall()
    return result({
        "outgoing": [dict(row) for row in outgoing],
        "incoming": [dict(row) for row in incoming],
        "pending_outgoing": sum(1 for row in outgoing if row["status"] == "pending"),
        "pending_incoming": sum(1 for row in incoming if row["status"] == "pending"),
        "expired": expired,
        "ttl_minutes": SWAP_TTL_MINUTES,
    })


@bp.get("/seat-swaps/incoming")
def incoming_anywhere():
    """跨课程拉一次「等我答复的换位申请」，登录后弹窗用。"""
    with write() as db:
        expire_stale(db)
        user = require_user()
        rows = db.execute(
            "SELECT r.*,u.name AS requester_name,u.student_no AS requester_no,c.title AS course_title "
            "FROM seat_swap_request r JOIN user u ON u.id=r.requester_id "
            "JOIN course c ON c.id=r.course_id "
            "WHERE r.target_id=? AND r.status='pending' ORDER BY r.id", (user["id"],)).fetchall()
    return result({"items": [dict(row) for row in rows], "ttl_minutes": SWAP_TTL_MINUTES})


@bp.post("/courses/<int:course_id>/seat-swaps/<int:swap_id>/accept")
def accept_swap(course_id, swap_id):
    """接受换位。答复前再核一遍两边坐标，中途有人挪过就判失效。"""
    with write() as db:
        expire_stale(db)
        user = require_user()
        row = load_request(db, course_id, swap_id)
        if row["target_id"] != user["id"]:
            raise ApiError(403, "FORBIDDEN", "只有被申请的一方能答复")
        if row["status"] != "pending":
            raise ApiError(409, "SWAP_NOT_PENDING", "这条申请已经结束了")
        mine = member_seat(db, course_id, user["id"])
        theirs = member_seat(db, course_id, row["requester_id"])
        if (not mine or not theirs
                or mine["group_no"] != row["to_group"] or mine["seat_no"] != row["to_seat"]
                or theirs["group_no"] != row["from_group"] or theirs["seat_no"] != row["from_seat"]):
            db.execute("UPDATE seat_swap_request SET status='cancelled', responded_at=? WHERE id=?",
                       (stamp(), swap_id))
            # 这条申请必须判成 cancelled 落库，但紧接着要抛 409；write() 遇到异常会整体回滚，
            # 所以先把这次状态更新提交掉，再抛。回滚落在已提交的事务上是空操作。
            db.commit()
            raise ApiError(409, "SEAT_CHANGED", "两边座位已经变了，这条申请失效，请重新发起")
        my_new, their_new = swap_positions(db, course_id, row["requester_id"], user["id"])
        db.execute("UPDATE seat_swap_request SET status='accepted', responded_at=? WHERE id=?",
                   (stamp(), swap_id))
        cancelled = cancel_pending_for(db, user["id"], keep_id=swap_id)
        cancelled += cancel_pending_for(db, row["requester_id"], keep_id=swap_id)
        notify(row["requester_id"], course_id, f"{user['name']} 同意了和你换座位",
               "seat_swap", swap_id, f"seat_swap_result:{swap_id}:accepted")
        audit("seat.swap_accept", "seat_swap_request", swap_id,
              after={"requester": [their_new[0], their_new[1]], "target": [my_new[0], my_new[1]]})
    return result({"id": swap_id, "status": "accepted",
                   "requester_seat": {"group_no": their_new[0], "seat_no": their_new[1]},
                   "target_seat": {"group_no": my_new[0], "seat_no": my_new[1]},
                   "cancelled": cancelled})


@bp.post("/courses/<int:course_id>/seat-swaps/<int:swap_id>/decline")
def decline_swap(course_id, swap_id):
    with write() as db:
        expire_stale(db)
        user = require_user()
        row = load_request(db, course_id, swap_id)
        if row["target_id"] != user["id"]:
            raise ApiError(403, "FORBIDDEN", "只有被申请的一方能答复")
        if row["status"] != "pending":
            raise ApiError(409, "SWAP_NOT_PENDING", "这条申请已经结束了")
        db.execute("UPDATE seat_swap_request SET status='declined', responded_at=? WHERE id=?",
                   (stamp(), swap_id))
        notify(row["requester_id"], course_id, f"{user['name']} 没同意换座位",
               "seat_swap", swap_id, f"seat_swap_result:{swap_id}:declined")
        audit("seat.swap_decline", "seat_swap_request", swap_id, after={"course_id": course_id})
    return result({"id": swap_id, "status": "declined"})


@bp.delete("/courses/<int:course_id>/seat-swaps/<int:swap_id>")
def cancel_swap(course_id, swap_id):
    """发起人撤回想撤回的申请。"""
    with write() as db:
        expire_stale(db)
        user = require_user()
        row = load_request(db, course_id, swap_id)
        if row["requester_id"] != user["id"]:
            raise ApiError(403, "FORBIDDEN", "只有发起人能撤回")
        if row["status"] != "pending":
            raise ApiError(409, "SWAP_NOT_PENDING", "这条申请已经结束了")
        db.execute("UPDATE seat_swap_request SET status='cancelled', responded_at=? WHERE id=?",
                   (stamp(), swap_id))
        audit("seat.swap_cancel", "seat_swap_request", swap_id, after={"course_id": course_id})
    return result({"id": swap_id, "status": "cancelled"})
