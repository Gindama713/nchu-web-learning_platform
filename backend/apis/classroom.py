"""SPEC-002 第10周：教师自定义教室规模与排座。

教室尺寸是**课程级**配置：同一门课的多个班共用一间教室，座位图按
（排, 座）二维坐标铺开。`class_seat` 里沿用 021 的列名 group_no / seat_no，
语义即「第几排 / 第几座」。

三档预设只是给教师的快捷入口，最终仍以 rows/cols 为准——阶梯教室里
120 人的课和 40 人的课都点「阶梯教室」，再自己调行列即可。
"""

from flask import Blueprint

from backend.shared.api import (
    ApiError,
    audit,
    body,
    non_negative_int,
    positive_int,
    result,
    stamp,
    text_field,
)
from backend.shared.auth import course_access
from backend.shared.db import get_db, write

bp = Blueprint("classroom", __name__)

MAX_ROWS = 40
MAX_COLS = 40
MAX_AISLE = 10

# 预设按容量从小到大排，pick_preset 依赖这个顺序挑「够用的最小一间」。
PRESETS = (
    {"template": "small", "label": "小教室", "rows": 6, "cols": 8, "aisle_every": 4},
    {"template": "large", "label": "大教室", "rows": 10, "cols": 12, "aisle_every": 4},
    {"template": "lecture", "label": "阶梯教室", "rows": 12, "cols": 14, "aisle_every": 2},
)
TEMPLATES = {preset["template"] for preset in PRESETS} | {"custom"}


def headcount(db, course_id):
    return db.execute(
        "SELECT COUNT(*) FROM course_member m JOIN user u ON u.id=m.user_id "
        "WHERE m.course_id=? AND m.member_role='student' AND m.active=1 AND u.active=1",
        (course_id,)).fetchone()[0]


def pick_preset(students):
    """按人数挑一间够用的最小教室；三档都不够时按最大一档横向加座。"""
    for preset in PRESETS:
        if preset["rows"] * preset["cols"] >= students:
            return dict(preset)
    grown = dict(PRESETS[-1])
    grown["cols"] = min(MAX_COLS, max(grown["cols"], -(-students // grown["rows"])))
    grown["template"] = "custom"
    grown["label"] = "自定义教室"
    return grown


def ensure_classroom(db, course_id):
    """取教室配置，没有就按人数建一间默认的。只在写操作里调用。"""
    row = db.execute("SELECT * FROM classroom WHERE course_id=?", (course_id,)).fetchone()
    if row:
        return row
    preset = pick_preset(headcount(db, course_id))
    timestamp = stamp()
    db.execute("INSERT INTO classroom(course_id,name,template,rows,cols,aisle_every,created_at,updated_at) "
               "VALUES(?,?,?,?,?,?,?,?)",
               (course_id, preset["label"], preset["template"], preset["rows"], preset["cols"],
                preset["aisle_every"], timestamp, timestamp))
    return db.execute("SELECT * FROM classroom WHERE course_id=?", (course_id,)).fetchone()


def classroom_state(db, course_id):
    """读接口不落库：还没配置过的课程按人数给出建议尺寸，教师点保存才写。"""
    row = db.execute("SELECT * FROM classroom WHERE course_id=?", (course_id,)).fetchone()
    if row:
        state = {key: row[key] for key in ("name", "template", "rows", "cols", "aisle_every", "updated_at")}
    else:
        preset = pick_preset(headcount(db, course_id))
        state = {key: preset[key] for key in ("template", "rows", "cols", "aisle_every")}
        state["name"] = preset["label"]
        state["updated_at"] = None
    students = headcount(db, course_id)
    seated = db.execute("SELECT COUNT(*) FROM class_seat WHERE course_id=?", (course_id,)).fetchone()[0]
    state.update({
        "capacity": state["rows"] * state["cols"],
        "students": students,
        "seated": seated,
        "unseated": max(students - seated, 0),
        "presets": [dict(preset) for preset in PRESETS],
        "limits": {"rows": MAX_ROWS, "cols": MAX_COLS, "aisle_every": MAX_AISLE},
    })
    return state


@bp.get("/courses/<int:course_id>/classroom")
def get_classroom(course_id):
    course_access(course_id)
    return result(classroom_state(get_db(), course_id))


@bp.put("/courses/<int:course_id>/classroom")
def put_classroom(course_id):
    data = body(("rows", "cols"), allowed=("name", "template", "rows", "cols", "aisle_every"))
    rows = positive_int(data["rows"], "rows")
    cols = positive_int(data["cols"], "cols")
    if rows > MAX_ROWS or cols > MAX_COLS:
        raise ApiError(422, "VALIDATION_ERROR", f"rows/cols 不能超过 {MAX_ROWS}")
    aisle = non_negative_int(data.get("aisle_every", 0), "aisle_every")
    if aisle > MAX_AISLE:
        raise ApiError(422, "VALIDATION_ERROR", f"aisle_every 不能超过 {MAX_AISLE}")
    template = data.get("template", "custom")
    if template not in TEMPLATES:
        raise ApiError(422, "VALIDATION_ERROR", "template 取值无效")
    with write() as db:
        course_access(course_id, teacher=True)
        current = ensure_classroom(db, course_id)
        name = text_field(data["name"], "name", 1, 40) if "name" in data else current["name"]
        timestamp = stamp()
        db.execute("UPDATE classroom SET name=?,template=?,rows=?,cols=?,aisle_every=?,updated_at=? "
                   "WHERE course_id=?",
                   (name, template, rows, cols, aisle, timestamp, course_id))
        # 教室改小以后越界的座位必须清掉，否则座位图会画出教室外面。
        removed = db.execute("DELETE FROM class_seat WHERE course_id=? AND (group_no>? OR seat_no>?)",
                             (course_id, rows, cols)).rowcount
        audit("classroom.update", "course", course_id,
              after={"rows": rows, "cols": cols, "aisle_every": aisle, "removed": removed})
        state = classroom_state(db, course_id)
    return result({**state, "removed": removed})


@bp.get("/courses/<int:course_id>/seats")
def list_seats(course_id):
    """课程当前座位表。教室还没排座时返回空数组，前端据此提示去排座。"""
    course_access(course_id)
    db = get_db()
    rows = db.execute(
        "SELECT cs.student_id,cs.group_no,cs.seat_no,cs.class_name,u.student_no,u.name "
        "FROM class_seat cs JOIN user u ON u.id=cs.student_id WHERE cs.course_id=? "
        "ORDER BY cs.group_no,cs.seat_no", (course_id,)).fetchall()
    return result({
        "classroom": classroom_state(db, course_id),
        "seats": [{key: row[key] for key in
                   ("student_id", "student_no", "name", "class_name", "group_no", "seat_no")}
                  for row in rows],
    })


@bp.post("/courses/<int:course_id>/classroom/auto-seat")
def auto_seat(course_id):
    """按班分段、班内按学号，把学生按行优先填进教室。

    每个班都从**整排**开始排，不跨排和上一个班拼座——座位图上四个班
    同处一张平面网格，但各自占一段连续排，教师一眼能看出哪个班在哪片。
    代价是每班末尾可能留下半排空位，所以要求整排起排后能放下才允许排座。
    """
    with write() as db:
        course_access(course_id, teacher=True)
        room = ensure_classroom(db, course_id)
        students = db.execute(
            "SELECT m.user_id,u.student_no,COALESCE(u.class_name,'未分班') AS class_name "
            "FROM course_member m JOIN user u ON u.id=m.user_id "
            "WHERE m.course_id=? AND m.member_role='student' AND m.active=1 AND u.active=1 "
            "ORDER BY class_name,u.student_no", (course_id,)).fetchall()
        by_class = {}
        for student in students:
            by_class.setdefault(student["class_name"], []).append(student)

        seats, row = [], 1
        for class_name in sorted(by_class):
            members = by_class[class_name]
            for offset, student in enumerate(members):
                seats.append((student["user_id"], class_name, row + offset // room["cols"],
                              offset % room["cols"] + 1))
            row += -(-len(members) // room["cols"])
        if row - 1 > room["rows"]:
            raise ApiError(422, "CAPACITY_EXCEEDED",
                           f"教室只有 {room['rows']} 排 × {room['cols']} 座，"
                           f"每个班整排起排需要 {row - 1} 排",
                           {"rows": room["rows"], "cols": room["cols"], "needed_rows": row - 1,
                            "students": len(students)})

        db.execute("DELETE FROM class_seat WHERE course_id=?", (course_id,))
        timestamp = stamp()
        db.executemany(
            "INSERT INTO class_seat(course_id,student_id,class_name,group_no,seat_no,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?)",
            [(course_id, student_id, class_name, group_no, seat_no, timestamp, timestamp)
             for student_id, class_name, group_no, seat_no in seats])
        audit("classroom.auto_seat", "course", course_id,
              after={"placed": len(seats), "rows": room["rows"], "cols": room["cols"]})
        state = classroom_state(db, course_id)
    return result({**state, "placed": len(seats)})


@bp.patch("/courses/<int:course_id>/seats/<int:student_id>")
def move_seat(course_id, student_id):
    """手动调整某个学生的座位，或把他从座位表里撤下来（clear）。"""
    data = body(allowed=("group_no", "seat_no", "clear"))
    with write() as db:
        course_access(course_id, teacher=True)
        member = db.execute(
            "SELECT u.id,u.class_name FROM course_member m JOIN user u ON u.id=m.user_id "
            "WHERE m.course_id=? AND m.user_id=? AND m.member_role='student' AND m.active=1",
            (course_id, student_id)).fetchone()
        if not member:
            raise ApiError(404, "NOT_FOUND", "Course student not found")
        if data.get("clear"):
            db.execute("DELETE FROM class_seat WHERE course_id=? AND student_id=?", (course_id, student_id))
            audit("classroom.unseat", "course_member", student_id, after={"course_id": course_id})
            return result({"student_id": student_id, "group_no": None, "seat_no": None, "class_name": None})
        if "group_no" not in data or "seat_no" not in data:
            raise ApiError(400, "VALIDATION_ERROR", "group_no 与 seat_no 必填")
        group_no = positive_int(data["group_no"], "group_no")
        seat_no = positive_int(data["seat_no"], "seat_no")
        room = ensure_classroom(db, course_id)
        if group_no > room["rows"] or seat_no > room["cols"]:
            raise ApiError(422, "OUT_OF_RANGE",
                           f"座位超出教室范围：最多 {room['rows']} 排、{room['cols']} 座")
        taken = db.execute("SELECT student_id FROM class_seat WHERE course_id=? AND group_no=? AND seat_no=?",
                           (course_id, group_no, seat_no)).fetchone()
        if taken and taken["student_id"] != student_id:
            raise ApiError(409, "SEAT_TAKEN", "该座位已有其他学生")
        class_name = member["class_name"] or "未分班"
        timestamp = stamp()
        existing = db.execute("SELECT id FROM class_seat WHERE course_id=? AND student_id=?",
                              (course_id, student_id)).fetchone()
        if existing:
            db.execute("UPDATE class_seat SET group_no=?,seat_no=?,class_name=?,updated_at=? WHERE id=?",
                       (group_no, seat_no, class_name, timestamp, existing["id"]))
        else:
            db.execute("INSERT INTO class_seat(course_id,student_id,class_name,group_no,seat_no,"
                       "created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                       (course_id, student_id, class_name, group_no, seat_no, timestamp, timestamp))
        audit("classroom.move_seat", "course_member", student_id,
              after={"course_id": course_id, "group_no": group_no, "seat_no": seat_no})
    return result({"student_id": student_id, "group_no": group_no, "seat_no": seat_no,
                   "class_name": class_name})
