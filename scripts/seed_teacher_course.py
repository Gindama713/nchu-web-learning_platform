"""给任务书规定的公开教师账号 teacher/teacher 配一门可点到的课程。

课堂互测时别的组会直接用 teacher/teacher 登录、建点到任务、读统计。
如果这个账号名下没有课程，互测方一进 /api/v1/courses 就是空列表，被测环节直接失败。
本脚本可重复执行：存在就复用，不存在就创建，并把当前所有在职学生加进课程成员。

    python scripts/seed_teacher_course.py
    python scripts/seed_teacher_course.py --db instance/app.db --title "计算机组成原理 · 课堂点到"
"""

from __future__ import annotations

# ruff: noqa: UP031  — 报表行以 % 拼接更直观，无需转 f-string
import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

TEACHER_NO = "teacher"
TEACHER_PASSWORD = "teacher"


def stamp():
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def add_arguments(parser):
    parser.add_argument("--db", default="instance/app.db", help="数据库路径，默认 instance/app.db")
    parser.add_argument("--title", default="计算机组成原理 · 课堂点到（第10周）", help="要保证存在的课程名")
    parser.add_argument("--description", default="课堂互测专用课程：教师 teacher，学生用学号登录。")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要做的改动，不写库")


def main(argv=None):
    parser = argparse.ArgumentParser(description="准备 teacher/teacher 的课堂点到课程")
    add_arguments(parser)
    args = parser.parse_args(argv)

    path = Path(args.db)
    if not path.exists():
        print(f"数据库不存在：{path}", file=sys.stderr)
        return 2

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from werkzeug.security import generate_password_hash

    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        timestamp = stamp()
        teacher = db.execute("SELECT id,student_no,role FROM user WHERE student_no=?", (TEACHER_NO,)).fetchone()
        if teacher is None:
            cursor = db.execute(
                "INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                "VALUES(?,?,?,'teacher',1,?,?)",
                (TEACHER_NO, "任课教师", generate_password_hash(TEACHER_PASSWORD), timestamp, timestamp))
            teacher_id = cursor.lastrowid
            print(f"已创建教师账号 {TEACHER_NO} / {TEACHER_PASSWORD}")
        else:
            teacher_id = teacher["id"]
            db.execute("UPDATE user SET password_hash=?,role='teacher',active=1,updated_at=? WHERE id=?",
                       (generate_password_hash(TEACHER_PASSWORD), timestamp, teacher_id))
            print(f"已确保教师账号 {TEACHER_NO} 可用，密码为 {TEACHER_PASSWORD}，角色 teacher")

        course = db.execute("SELECT id,title FROM course WHERE teacher_id=? AND title=?",
                            (teacher_id, args.title)).fetchone()
        if course is None:
            cursor = db.execute(
                "INSERT INTO course(title,description,teacher_id,created_at,updated_at) VALUES(?,?,?,?,?)",
                (args.title, args.description, teacher_id, timestamp, timestamp))
            course_id = cursor.lastrowid
            print(f"已创建课程 #{course_id} {args.title}")
        else:
            course_id = course["id"]
            print(f"复用已有课程 #{course_id} {args.title}")

        db.execute("INSERT OR IGNORE INTO course_member(course_id,user_id,member_role,active,created_at,updated_at) "
                   "VALUES(?,?,'teacher',1,?,?)", (course_id, teacher_id, timestamp, timestamp))

        students = db.execute("SELECT id,student_no,name FROM user WHERE role='student' AND active=1 "
                              "ORDER BY id").fetchall()
        added = 0
        for student in students:
            existed = db.execute("SELECT 1 FROM course_member WHERE course_id=? AND user_id=?",
                                 (course_id, student["id"])).fetchone()
            if not existed:
                added += 1
            db.execute("INSERT INTO course_member(course_id,user_id,member_role,active,created_at,updated_at) "
                       "VALUES(?,?,'student',1,?,?) "
                       "ON CONFLICT(course_id,user_id) DO UPDATE SET active=1,updated_at=excluded.updated_at",
                       (course_id, student["id"], timestamp, timestamp))
        print("课程成员：学生 %d 人，本次新增 %d 人" % (len(students), added))

        if args.dry_run:
            db.rollback()
            print("--dry-run：已回滚，未写库")
        else:
            db.commit()
            print(f"已写库：{path}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
