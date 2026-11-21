# -*- coding: utf-8 -*-
"""把课程 #16 扩成「四班同堂」：教室扩容 + 四个班全体学生 + 全量业务数据。

用法（在仓库根目录执行）：
    python scripts/expand_demo_week11.py

特性：
* 幂等，可重复执行；已存在的成员/记录不会重复写入。
* 只动课程 #16，旧课 #15 完全不动。
* 座位按后端 auto-seat 的「按班整排起排」算法重排，四个班各占 4 整排。
* 教室 18 排 × 10 座 = 180 座，容纳 242015/16/17/18 四班共 160 人。
"""
from __future__ import annotations

import math
import os
import sqlite3
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "instance", "app.db")
COURSE_ID = 16
CLASSES = ("242015", "242016", "242017", "242018")
ROWS, COLS = 18, 10
ROOM_NAME = "教学楼 A-305 · 阶梯教室（四班同堂）"


def stamp(moment: datetime | None = None) -> str:
    moment = moment or datetime.now(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> None:
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("BEGIN IMMEDIATE")
    now = datetime.now(timezone.utc)
    ts = stamp(now)

    # 原始名单：种子脚本一次性写入的那批成员（created_at 相同），重跑时用它识别「新增的人」
    first = db.execute("SELECT MIN(created_at) FROM course_member WHERE course_id=? AND member_role='student'",
                       (COURSE_ID,)).fetchone()[0]
    before = {r[0] for r in db.execute(
        "SELECT user_id FROM course_member WHERE course_id=? AND member_role='student' AND created_at=?",
        (COURSE_ID, first))}
    print(f"扩容前课程成员：{len(before)} 名学生")

    # 1. 四个班全体学生激活、补齐班级名（名单外被停用的 28 人也一并纳入演示）
    marks = ",".join("?" * len(CLASSES))
    activated = db.execute(
        "UPDATE user SET active=1, class_name=substr(student_no,1,6), updated_at=? "
        "WHERE role='student' AND substr(student_no,1,6) IN (" + marks + ") "
        "AND (active<>1 OR class_name IS NULL OR class_name<>substr(student_no,1,6))",
        (ts, *CLASSES)).rowcount
    students = [dict(r) for r in db.execute(
        "SELECT id,student_no,class_name FROM user "
        "WHERE role='student' AND active=1 AND substr(student_no,1,6) IN (" + marks + ") "
        "ORDER BY class_name,student_no", CLASSES)]
    print(f"激活/补班级名 {activated} 人；四班共 {len(students)} 人")

    # 2. 全部加入课程 #16
    db.executemany(
        "INSERT OR IGNORE INTO course_member(course_id,user_id,member_role,active,created_at,updated_at) "
        "VALUES(?,?,'student',1,?,?)",
        [(COURSE_ID, s["id"], ts, ts) for s in students])
    added = len(students) - len(before)
    print(f"新增课程成员 {added} 人，现共 {len(students)} 名学生")

    # 3. 教室扩容
    db.execute("UPDATE classroom SET name=?,template='custom',rows=?,cols=?,aisle_every=2,updated_at=? "
               "WHERE course_id=?", (ROOM_NAME, ROWS, COLS, ts, COURSE_ID))
    print(f"教室改为 {ROWS} 排 × {COLS} 座 = {ROWS * COLS} 座")

    # 4. 按班整排起排（与 backend/apis/classroom.py auto-seat 完全一致）
    by_class: dict[str, list[dict]] = {}
    for s in students:
        by_class.setdefault(s["class_name"], []).append(s)
    db.execute("DELETE FROM class_seat WHERE course_id=?", (COURSE_ID,))
    seats = []
    row = 1
    for class_name in sorted(by_class):
        members = by_class[class_name]
        for offset, s in enumerate(members):
            seats.append((COURSE_ID, s["id"], class_name,
                          row + offset // COLS, offset % COLS + 1, ts, ts))
        row += math.ceil(len(members) / COLS)
    needed_rows = row - 1
    if needed_rows > ROWS:
        raise SystemExit(f"教室排数不够：需要 {needed_rows} 排，只有 {ROWS} 排")
    db.executemany(
        "INSERT INTO class_seat(course_id,student_id,class_name,group_no,seat_no,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?)", seats)
    print(f"排座完成：{len(seats)} 个座位，占用 {needed_rows} 排（余 {ROWS - needed_rows} 排）")

    # 5. 三个签到任务的座位快照 + 参与者
    tasks = [dict(r) for r in db.execute(
        "SELECT id,title,status,start_at,late_at,end_at FROM attendance_task WHERE course_id=? ORDER BY id",
        (COURSE_ID,))]
    for task in tasks:
        tid = task["id"]
        db.execute("DELETE FROM attendance_seat WHERE task_id=?", (tid,))
        db.executemany(
            "INSERT INTO attendance_seat(task_id,student_id,group_no,seat_no) VALUES(?,?,?,?)",
            [(tid, seat[1], seat[3], seat[4]) for seat in seats])
        db.executemany(
            "INSERT OR IGNORE INTO attendance_participant(task_id,student_id) VALUES(?,?)",
            [(tid, s["id"]) for s in students])
    print(f"三个签到任务：每个 {len(seats)} 个座位 / {len(students)} 名参与者")

    papers = [r[0] for r in db.execute("SELECT id FROM paper WHERE course_id=?", (COURSE_ID,))]
    versions = [r[0] for r in db.execute(
        "SELECT id FROM experiment_version WHERE experiment_id IN "
        "(SELECT id FROM experiment WHERE course_id=?)", (COURSE_ID,))]
    # 已发布试卷被 paper_published_frozen 冻结，无法回退到 draft 再补参与者。
    # 事务内临时摘掉插入守卫，补完原样重建；失败回滚时触发器也会恢复。
    guard = db.execute("SELECT sql FROM sqlite_master WHERE type='trigger' "
                       "AND name='paper_participant_insert_guard'").fetchone()
    if guard:
        db.execute("DROP TRIGGER paper_participant_insert_guard")
    db.executemany("INSERT OR IGNORE INTO paper_participant(paper_id,student_id) VALUES(?,?)",
                   [(p, s["id"]) for p in papers for s in students])
    if guard:
        db.execute(guard[0])
    db.executemany("INSERT OR IGNORE INTO experiment_participant(experiment_version_id,student_id) VALUES(?,?)",
                   [(v, s["id"]) for v in versions for s in students])
    print(f"试卷参与者 {len(papers)}×{len(students)}，实验参与者 {len(versions)}×{len(students)}")

    fresh = [s for s in students if s["id"] not in before]
    if not fresh:
        print("没有新增学生，跳过记录补齐")
    else:
        # 6. 已结束那次课：present / late / leave / absent 混合，到勤率约 85%
        past = next(t for t in tasks if t["status"] == "closed")
        past_start = parse(past["start_at"])
        past_late = parse(past["late_at"])
        for index, s in enumerate(fresh):
            bucket = index % 20
            if bucket < 15:
                status, source, checked = "present", "checkin", stamp(past_start + timedelta(minutes=5))
            elif bucket < 17:
                status, source, checked = "late", "checkin", stamp(past_late + timedelta(minutes=2))
            elif bucket < 19:
                status, source, checked = "leave", "approval", None
            else:
                status, source, checked = "absent", "close", None
            db.execute("INSERT OR IGNORE INTO attendance_record(task_id,student_id,status,checked_at,"
                       "source,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                       (past["id"], s["id"], status, checked, source, ts, ts))

        # 7. 两个进行中任务：新学生一半手势、一半签到码，剩下留白给课堂现场签
        live = [t for t in tasks if t["status"] != "closed"]
        gesture = next((t for t in live if "手势" in t["title"]), None)
        code = next((t for t in live if "签到码" in t["title"]), None)
        checked = stamp(now - timedelta(minutes=6))
        for index, s in enumerate(fresh):
            # source 只允许 checkin/gesture/approval/close/correction，签到码也记 checkin
            task, source = (gesture, "gesture") if index % 2 == 0 else (code, "checkin")
            if task is None:
                continue
            db.execute("INSERT OR IGNORE INTO attendance_record(task_id,student_id,status,checked_at,"
                       "source,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                       (task["id"], s["id"], "present", checked, source, ts, ts))
        print(f"新增签到记录：已结束 {len(fresh)} 条 + 进行中 {len(fresh)} 条")

        # 8. 练习 / 错题 / 学习进度
        # 触发器要求练习只能落在「公开且客观」的版本上，保密卷/简答题不能造练习
        qversions = [dict(r) for r in db.execute(
            "SELECT v.id,v.question_id FROM question_version v JOIN question q ON q.id=v.question_id "
            "WHERE q.course_id=? AND v.practice_available=1 AND v.type<>'short' ORDER BY v.id",
            (COURSE_ID,))]
        kps = [r[0] for r in db.execute(
            "SELECT id FROM knowledge_point WHERE chapter_id IN "
            "(SELECT id FROM chapter WHERE course_id=?) ORDER BY id", (COURSE_ID,))]
        practice = wrong = progress = 0
        for index, s in enumerate(fresh):
            for k in range(2):
                item = qversions[(index * 2 + k) % len(qversions)]
                vid, qid = item["id"], item["question_id"]
                correct = 1 if (index + k) % 3 else 0
                cur = db.execute(
                    "INSERT INTO practice_attempt(student_id,question_version_id,answer_json,answered,"
                    "correct,score_hundredths,created_at) SELECT ?,?,?,1,?,?,? "
                    "WHERE NOT EXISTS (SELECT 1 FROM practice_attempt WHERE student_id=? AND question_version_id=?)",
                    (s["id"], vid, '"A"', correct, 10000 if correct else 0, ts,
                     s["id"], vid))
                practice += cur.rowcount
                if not correct:
                    # 触发器要求 last_attempt_id 指向本人同题、correct=0 的真实练习记录
                    attempt = db.execute(
                        "SELECT id FROM practice_attempt WHERE student_id=? AND question_version_id=?",
                        (s["id"], vid)).fetchone()
                    if attempt:
                        cur = db.execute(
                            "INSERT OR IGNORE INTO wrong_question(student_id,question_id,last_attempt_type,"
                            "last_attempt_id,resolved) VALUES(?,?,'practice',?,0)", (s["id"], qid, attempt[0]))
                        wrong += cur.rowcount
            for k in range(2):
                kid = kps[(index * 2 + k) % len(kps)]
                cur = db.execute(
                    "INSERT OR IGNORE INTO learning_progress(user_id,knowledge_id,completed,completed_at) "
                    "VALUES(?,?,1,?)", (s["id"], kid, ts))
                progress += cur.rowcount
        print(f"新增练习 {practice} 条 / 错题 {wrong} 条 / 学习进度 {progress} 条")

        # 9. 复制评测提交，让四个班都有评测成绩（按现有 24 条 run 的状态分布复制）
        runs = [dict(r) for r in db.execute(
            "SELECT * FROM grading_run WHERE suite_id IN "
            "(SELECT id FROM test_suite WHERE experiment_version_id IN (" +
            ",".join("?" * len(versions)) + ")) ORDER BY id", versions)]
        # 只用原始名单学生的提交当模板，避免把上一轮复制出来的 run 再当模板
        runs = [r for r in runs
                if db.execute("SELECT student_id FROM submission WHERE id=?",
                              (r["submission_id"],)).fetchone()[0] in before]
        run_cols = [r[1] for r in db.execute("PRAGMA table_info(grading_run)")]
        new_runs = new_cases = new_subs = 0
        for index, run in enumerate(runs[:len(fresh)]):
            s = fresh[index]
            sub = db.execute("SELECT * FROM submission WHERE id=?", (run["submission_id"],)).fetchone()
            if sub is None:
                continue
            if db.execute("SELECT 1 FROM submission WHERE student_id=? AND experiment_version_id=?",
                          (s["id"], sub["experiment_version_id"])).fetchone():
                continue
            cur = db.execute(
                "INSERT INTO submission(experiment_version_id,student_id,file_id,file_sha256,size_bytes,"
                "filename,created_at) VALUES(?,?,?,?,?,?,?)",
                (sub["experiment_version_id"], s["id"], sub["file_id"], sub["file_sha256"],
                 sub["size_bytes"], f"EXP-0{sub['experiment_version_id']}-{s['student_no']}.circ", ts))
            new_subs += 1
            values = dict(run)
            values["submission_id"] = cur.lastrowid
            values["worker_token"] = None
            values["lease_until"] = None
            values["retry_of"] = None
            values["created_at"] = ts
            values["started_at"] = stamp(now - timedelta(minutes=4))
            values["finished_at"] = stamp(now - timedelta(minutes=3))
            values.pop("id", None)
            cols = [c for c in run_cols if c != "id"]
            cur2 = db.execute(
                "INSERT INTO grading_run(" + ",".join(cols) + ") VALUES(" +
                ",".join("?" * len(cols)) + ")", [values[c] for c in cols])
            new_runs += 1
            old_cases = db.execute(
                "SELECT case_id,passed,actual_json,elapsed_ms,error_code FROM case_result WHERE run_id=?",
                (run["id"],)).fetchall()
            db.executemany(
                "INSERT INTO case_result(run_id,case_id,passed,actual_json,elapsed_ms,error_code) "
                "VALUES(?,?,?,?,?,?)",
                [(cur2.lastrowid, c[0], c[1], c[2], c[3], c[4]) for c in old_cases])
            new_cases += len(old_cases)
        print(f"新增提交 {new_subs} 条 / 评测 {new_runs} 条 / 用例结果 {new_cases} 条")

    db.commit()
    print("\n=== 扩容后核对 ===")
    for label, sql in [
        ("学生成员", "SELECT COUNT(*) FROM course_member WHERE course_id=16 AND member_role='student'"),
        ("教室座位", "SELECT rows*cols FROM classroom WHERE course_id=16"),
        ("已排座位", "SELECT COUNT(*) FROM class_seat WHERE course_id=16"),
        ("任务座位快照", "SELECT COUNT(*) FROM attendance_seat WHERE task_id=52"),
        ("签到记录", "SELECT COUNT(*) FROM attendance_record WHERE task_id IN (SELECT id FROM attendance_task WHERE course_id=16)"),
        ("评测运行", "SELECT COUNT(*) FROM grading_run WHERE suite_id IN (SELECT id FROM test_suite WHERE experiment_version_id IN (SELECT id FROM experiment_version WHERE experiment_id IN (SELECT id FROM experiment WHERE course_id=16)))"),
    ]:
        print(f"  {label}: {db.execute(sql).fetchone()[0]}")
    classes = db.execute(
        "SELECT substr(u.student_no,1,6) cls, COUNT(*) n FROM course_member m JOIN user u ON u.id=m.user_id "
        "WHERE m.course_id=16 AND m.member_role='student' AND m.active=1 GROUP BY cls ORDER BY cls").fetchall()
    print("  班级分布:", [(r[0], r[1]) for r in classes])
    db.close()


if __name__ == "__main__":
    main()
