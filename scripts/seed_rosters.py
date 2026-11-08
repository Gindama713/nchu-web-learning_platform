"""Idempotently import class rosters into the SQLite user table.

Real roster CSV files belong in the gitignored instance/rosters/ directory.
The script validates every row before writing, upserts by student_no, and can
reset existing student passwords to 学号/学号 for classroom demos.
"""

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.shared.db import connect

STUDENT_NO = re.compile(r"[A-Za-z0-9]{8,20}")
DEMO_STUDENT = ("24200000", "演示学生")
DEMO_TEACHER = ("teacher", "演示教师")
COLUMNS = {
    "student_no": ("student_no", "学号", "学生学号"),
    "name": ("name", "姓名", "学生姓名"),
    "class_name": ("class_name", "class", "班级", "班级名称"),
}


class RosterError(ValueError):
    pass


def _column_map(fieldnames, source):
    stripped = {name.strip(): name for name in fieldnames or () if name}
    mapping = {}
    for key, aliases in COLUMNS.items():
        mapping[key] = next((stripped[alias] for alias in aliases if alias in stripped), None)
    missing = [key for key in ("student_no", "name") if not mapping[key]]
    if missing:
        raise RosterError(f"{source} 缺少必要列：{', '.join(missing)}（支持中文或英文表头）")
    return mapping


def read_rosters(paths):
    files = []
    for item in paths:
        path = Path(item)
        if path.is_dir():
            files.extend(sorted(path.glob("*.csv")))
        elif path.is_file():
            files.append(path)
        else:
            raise RosterError(f"找不到名单文件或目录：{path}")
    if not files:
        raise RosterError("没有找到可导入的 CSV 名单")

    rows = {}
    sources = {}
    for path in files:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            mapping = _column_map(reader.fieldnames, path.name)
            for line, raw in enumerate(reader, start=2):
                number = (raw.get(mapping["student_no"]) or "").strip()
                name = (raw.get(mapping["name"]) or "").strip()
                class_name = (raw.get(mapping["class_name"]) or "").strip() if mapping["class_name"] else ""
                if not number and not name:
                    continue
                where = f"{path.name}:{line}"
                if not STUDENT_NO.fullmatch(number):
                    raise RosterError(f"{where} 学号必须是 8–20 位字母或数字：{number!r}")
                if not 1 <= len(name) <= 50:
                    raise RosterError(f"{where} 姓名长度必须是 1–50：{name!r}")
                existing = rows.get(number)
                if existing and existing["name"] != name:
                    raise RosterError(
                        f"{where} 学号 {number} 的姓名与 {sources[number]} 冲突：{existing['name']} / {name}")
                rows[number] = {"student_no": number, "name": name, "class_name": class_name}
                sources[number] = where
    if not rows:
        raise RosterError("名单中没有有效学生行")
    return list(rows.values())


def _stamp():
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _ensure_demo_teacher(db, now):
    row = db.execute("SELECT role FROM user WHERE student_no=?", (DEMO_TEACHER[0],)).fetchone()
    if row:
        return "exists"
    db.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
               "VALUES(?,?,?,'teacher',1,?,?)",
               (*DEMO_TEACHER, generate_password_hash(DEMO_TEACHER[0]), now, now))
    return "created"


def import_rosters(database, paths, reset_passwords="none", ensure_demo=True):
    if reset_passwords not in ("none", "roster", "all"):
        raise RosterError("reset_passwords 只能是 none、roster 或 all")
    rows = read_rosters(paths)
    roster_students = len(rows)
    demo_added = False
    if ensure_demo and all(row["student_no"] != DEMO_STUDENT[0] for row in rows):
        rows.append({"student_no": DEMO_STUDENT[0], "name": DEMO_STUDENT[1], "class_name": ""})
        demo_added = True

    counts = {"created": 0, "updated": 0, "unchanged": 0, "password_reset": 0}
    db = connect(database)
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='user'").fetchone():
            raise RosterError("数据库尚未初始化，请先运行 python -m flask --app backend.app db-upgrade")
        db.execute("BEGIN IMMEDIATE")
        now = _stamp()
        touched = set()
        for row in rows:
            existing = db.execute("SELECT id,name,role,class_name FROM user WHERE student_no=?",
                                  (row["student_no"],)).fetchone()
            if existing:
                if existing["role"] != "student":
                    raise RosterError(f"学号 {row['student_no']} 已被非学生账号占用")
                touched.add(existing["id"])
                class_name = row["class_name"] or existing["class_name"]
                if existing["name"] != row["name"] or existing["class_name"] != class_name:
                    db.execute("UPDATE user SET name=?,class_name=?,updated_at=? WHERE id=?",
                               (row["name"], class_name, now, existing["id"]))
                    counts["updated"] += 1
                else:
                    counts["unchanged"] += 1
                if reset_passwords in ("roster", "all"):
                    db.execute("UPDATE user SET password_hash=?,session_version=session_version+1,"
                               "updated_at=? WHERE id=?",
                               (generate_password_hash(row["student_no"]), now, existing["id"]))
                    counts["password_reset"] += 1
            else:
                cursor = db.execute(
                    "INSERT INTO user(student_no,name,class_name,password_hash,role,active,created_at,updated_at) "
                    "VALUES(?,?,?,?,'student',1,?,?)",
                    (row["student_no"], row["name"], row["class_name"] or None,
                     generate_password_hash(row["student_no"]), now, now))
                touched.add(cursor.lastrowid)
                counts["created"] += 1

        if reset_passwords == "all":
            for student in db.execute("SELECT id,student_no FROM user WHERE role='student'"):
                if student["id"] in touched:
                    continue
                db.execute("UPDATE user SET password_hash=?,session_version=session_version+1,"
                           "updated_at=? WHERE id=?",
                           (generate_password_hash(student["student_no"]), now, student["id"]))
                counts["password_reset"] += 1

        teacher_state = _ensure_demo_teacher(db, now) if ensure_demo else "skipped"
        classes = Counter(row["class_name"] for row in rows if row["class_name"])
        counts.update({"students": len(rows), "roster_students": roster_students,
                       "demo_student": demo_added, "reset_passwords": reset_passwords,
                       "demo_teacher": teacher_state, "classes": dict(sorted(classes.items()))})
        db.execute("INSERT INTO audit_event(actor_id,action,object_type,object_id,request_id,"
                   "before_summary,after_summary,created_at) "
                   "VALUES(NULL,'roster.import','user',NULL,'seed-rosters',NULL,?,?)",
                   (json.dumps(counts, ensure_ascii=False), now))
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description="幂等导入班级学生名单，默认密码为学号")
    parser.add_argument("--database", default=os.environ.get("DATABASE_PATH", str(ROOT / "instance/app.db")))
    parser.add_argument("--rosters", nargs="+", default=[str(ROOT / "instance/rosters")],
                        help="CSV 文件或目录（默认 instance/rosters）")
    parser.add_argument("--reset-passwords", choices=("none", "roster", "all"), default="none",
                        help="none 不改旧密码；roster 重置名单内学生；all 重置所有学生（含演示学生）")
    parser.add_argument("--no-demo-accounts", action="store_true",
                        help="不确保 24200000 学生和 teacher 教师演示账号存在")
    args = parser.parse_args(argv)
    try:
        result = import_rosters(args.database, args.rosters, args.reset_passwords,
                                ensure_demo=not args.no_demo_accounts)
    except (RosterError, sqlite3.Error) as exc:
        print(f"导入失败：{exc}", file=sys.stderr)
        return 1
    suffix = "（含演示学生）" if result["demo_student"] else ""
    print(f"名单导入完成：真实名单 {result['roster_students']} 人，账号共 {result['students']} 人{suffix}；"
          f"新增 {result['created']}，更新 {result['updated']}，未变 {result['unchanged']}，"
          f"重置密码 {result['password_reset']}。")
    if result["classes"]:
        print("班级分布：" + "，".join(f"{name} {count} 人" for name, count in result["classes"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
