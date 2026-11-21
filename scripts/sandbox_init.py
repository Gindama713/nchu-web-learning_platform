"""课堂/老师沙箱的一键初始化：建库、迁移、准备演示账号与课程。

非交互、可重复执行，不依赖 Flask CLI 的 prompt，也不需要 Logisim JAR。
只用到标准库 + werkzeug（已在 backend/requirements.lock 内）。

    python scripts/sandbox_init.py
    python scripts/sandbox_init.py --db instance/app.db --students 40
    python scripts/sandbox_init.py --dry-run
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.shared.db import migrate
from werkzeug.security import generate_password_hash

TEACHER_NO = "teacher"
TEACHER_PASSWORD = "teacher"
COURSE_TITLE = "计算机组成原理 · 课堂点到（沙箱）"


def stamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def columns(db: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def ensure_teacher(db: sqlite3.Connection, now: str) -> int | None:
    cols = columns(db, "user")
    if not cols or not {"student_no", "name", "password_hash", "role", "active"} <= cols:
        print("跳过教师账号：user 表结构不符")
        return None
    row = db.execute("SELECT id FROM user WHERE student_no=?", (TEACHER_NO,)).fetchone()
    hashed = generate_password_hash(TEACHER_PASSWORD)
    if row:
        db.execute("UPDATE user SET password_hash=?,role='teacher',active=1,updated_at=? WHERE id=?",
                   (hashed, now, row["id"]))
        teacher_id = row["id"]
        print(f"已确保教师账号 {TEACHER_NO}/{TEACHER_PASSWORD} 可用（id={teacher_id}）")
    else:
        fields = {"student_no": TEACHER_NO, "name": "任课教师", "password_hash": hashed,
                  "role": "teacher", "active": 1, "created_at": now, "updated_at": now}
        usable = {k: v for k, v in fields.items() if k in cols}
        placeholders = ",".join("?" for _ in usable)
        cursor = db.execute(
            f"INSERT INTO user({','.join(usable)}) VALUES({placeholders})",
            tuple(usable.values()))
        teacher_id = cursor.lastrowid
        print(f"已创建教师账号 {TEACHER_NO}/{TEACHER_PASSWORD}（id={teacher_id}）")
    return teacher_id


def ensure_course(db: sqlite3.Connection, teacher_id: int, now: str) -> int | None:
    cols = columns(db, "course")
    if not cols or "teacher_id" not in cols:
        print("跳过课程：course 表结构不符")
        return None
    row = db.execute("SELECT id FROM course WHERE teacher_id=? AND title=?",
                     (teacher_id, COURSE_TITLE)).fetchone()
    if row:
        course_id = row["id"]
        print(f"复用课程 #{course_id} {COURSE_TITLE}")
    else:
        fields = {"title": COURSE_TITLE, "description": "沙箱初始化课程，供课堂点到互测使用",
                  "teacher_id": teacher_id, "created_at": now, "updated_at": now}
        usable = {k: v for k, v in fields.items() if k in cols}
        cursor = db.execute(
            f"INSERT INTO course({','.join(usable)}) VALUES({','.join('?' for _ in usable)})",
            tuple(usable.values()))
        course_id = cursor.lastrowid
        print(f"已创建课程 #{course_id} {COURSE_TITLE}")
    # GET /api/v1/courses 按 course_member 取可见课程，教师本人也必须有成员记录
    db.execute(
        "INSERT INTO course_member(course_id,user_id,member_role,active,created_at,updated_at) "
        "VALUES(?,?,'teacher',1,?,?) ON CONFLICT(course_id,user_id) DO UPDATE SET active=1",
        (course_id, teacher_id, now, now))
    return course_id


def ensure_students(db: sqlite3.Connection, course_id: int, count: int, now: str) -> None:
    cols = columns(db, "user")
    member_cols = columns(db, "course_member")
    if not cols or not member_cols:
        print("跳过演示学生：缺少 user / course_member 表")
        return
    added = 0
    for index in range(1, count + 1):
        number = f"242017{index:02d}"
        row = db.execute("SELECT id FROM user WHERE student_no=?", (number,)).fetchone()
        if row:
            student_id = row["id"]
        else:
            fields = {"student_no": number, "name": f"演示学生{index:02d}",
                      "password_hash": generate_password_hash(number),
                      "role": "student", "active": 1, "created_at": now, "updated_at": now}
            usable = {k: v for k, v in fields.items() if k in cols}
            cursor = db.execute(
                f"INSERT INTO user({','.join(usable)}) VALUES({','.join('?' for _ in usable)})",
                tuple(usable.values()))
            student_id = cursor.lastrowid
        db.execute(
            "INSERT INTO course_member(course_id,user_id,member_role,active,created_at,updated_at) "
            "VALUES(?,?,'student',1,?,?) ON CONFLICT(course_id,user_id) DO UPDATE SET active=1",
            (course_id, student_id, now, now))
        added += 1
    print(f"演示学生 {added} 人已加入课程（密码 = 学号）")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="沙箱非交互初始化")
    parser.add_argument("--db", default="instance/app.db", help="数据库路径")
    parser.add_argument("--students", type=int, default=40, help="演示学生数量，默认 40")
    parser.add_argument("--dry-run", action="store_true", help="只演练，不写库")
    args = parser.parse_args(argv)

    path = Path(args.db)
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"数据库：{path.resolve()}")
    migrate(str(path))
    print("迁移完成")

    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        now = stamp()
        db.execute("BEGIN IMMEDIATE")
        teacher_id = ensure_teacher(db, now)
        course_id = ensure_course(db, teacher_id, now) if teacher_id else None
        if course_id:
            ensure_students(db, course_id, max(0, args.students), now)
        if args.dry_run:
            db.rollback()
            print("--dry-run：已回滚，未写库")
        else:
            db.commit()
            print("已写库。教师 teacher/teacher，学生密码等于学号。")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
