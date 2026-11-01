"""第10周互测：生成 4 个班的课程名单，并分配课堂座位。

名单是**课程演示用的合成数据**，不是学校真实名册。学号沿用本组格式
（2420 + 班级两位 + 班内序号两位），姓名取常见中文姓名随机组合；
本组四人（姜苏豪、黄俊诚、罗浩铭、石佰合）保留真实学号与姓名。

生成结果：
    4 个班 × 40 人 = 160 个学生账号，密码统一等于学号；
    全部加入 teacher/teacher 名下的课堂点到课程；
    每班分 10 组、每组 4 个座位，写入 class_seat。

脚本可重复执行：已存在的学号就地更新班级与密码，不会重复插入。

    python scripts/seed_real_roster.py --dry-run    # 只看将要做什么
    python scripts/seed_real_roster.py              # 真写库
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

CLASSES = ["242015", "242016", "242017", "242018"]
PER_CLASS = 40
GROUPS = 10
SEATS_PER_GROUP = PER_CLASS // GROUPS

# 本组四人：学号 -> 姓名，固定在第 10 组
OURS = {
    "24201718": "姜苏豪",
    "24201716": "黄俊诚",
    "24201723": "罗浩铭",
    "24201737": "石佰合",
}
OUR_GROUP = 10

SURNAMES = (
    "王李张刘陈杨黄赵周吴徐孙马朱胡林郭何高罗郑梁谢宋唐许韩冯邓曹彭曾萧田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢"
    "姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛段雷侯龙史陶黎贺顾毛郝龚邵万钱严武戴莫孔向汤"
)
GIVEN = (
    "伟芳娜敏静丽强磊军洋勇艳杰娟涛明超秀霞平刚华玉萍红玲芬燕斌宇浩凯鹏飞龙鑫晨阳雨泽佳怡若彤子涵思远嘉豪"
    "文卓然雅欣瑞哲皓天弘毅书瑶梦琪铭宇诗涵博文晨曦子轩心怡雨欣一鸣振宇晓峰建国志强海燕春梅冬雪秋菊"
)
RARE = ("煊烨骏骁珂璇璟尧禹淳澄潇若薇瑄璟",)


def stamp():
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_roster():
    """返回 [(class_name, student_no, name)]，同一班内姓名不重复。"""
    rng = random.Random(20261101)
    used = set(OURS.values())
    roster = []
    for class_name in CLASSES:
        taken = set()
        for index in range(1, PER_CLASS + 1):
            number = "%s%02d" % (class_name, index)
            if number in OURS:
                roster.append((class_name, number, OURS[number]))
                continue
            while True:
                name = rng.choice(SURNAMES)
                for _ in range(rng.choice((1, 2, 2))):
                    name += rng.choice(GIVEN + RARE[0])
                if name not in used and name not in taken:
                    break
            taken.add(name)
            used.add(name)
            roster.append((class_name, number, name))
    return roster


def assign_seats(roster):
    """每班 10 组 × 4 座；本组四人固定在第 10 组。"""
    by_class = {}
    for class_name, number, _name in roster:
        by_class.setdefault(class_name, []).append(number)

    seats = {}
    for class_name, numbers in by_class.items():
        ours = [number for number in numbers if number in OURS]
        rest = [number for number in numbers if number not in OURS]
        filled = []
        if ours:
            for offset, number in enumerate(sorted(ours)):
                filled.append((number, OUR_GROUP, offset + 1))
        cursor = 0
        for group in range(1, GROUPS + 1):
            if ours and group == OUR_GROUP:
                continue
            for seat in range(1, SEATS_PER_GROUP + 1):
                if cursor >= len(rest):
                    break
                filled.append((rest[cursor], group, seat))
                cursor += 1
        seats[class_name] = filled
    return seats


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成 4 个班的演示名单与课堂座位")
    parser.add_argument("--db", default="instance/app.db")
    parser.add_argument("--course-title", default="计算机组成原理 · 课堂点到（第10周）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    from werkzeug.security import generate_password_hash

    from backend.shared.db import migrate

    path = Path(args.db)
    migrate(path)

    roster = build_roster()
    seats = assign_seats(roster)
    print("名单 %d 人，%d 个班，每班 %d 组 × %d 座"
          % (len(roster), len(CLASSES), GROUPS, SEATS_PER_GROUP))
    if args.dry_run:
        for class_name in CLASSES[:1]:
            sample = [row for row in roster if row[0] == class_name][:6]
            for row in sample:
                print("   ", row)
        print("--dry-run：未写库")
        return 0

    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        timestamp = stamp()
        teacher = db.execute("SELECT id FROM user WHERE student_no='teacher'").fetchone()
        if teacher is None:
            print("找不到 teacher 账号，先跑 scripts/seed_teacher_course.py", file=sys.stderr)
            return 2
        course = db.execute("SELECT id FROM course WHERE teacher_id=? AND title=?",
                            (teacher["id"], args.course_title)).fetchone()
        if course is None:
            print("找不到课堂点到课程，先跑 scripts/seed_teacher_course.py", file=sys.stderr)
            return 2
        course_id = course["id"]

        created = updated = 0
        for class_name, number, name in roster:
            existing = db.execute("SELECT id FROM user WHERE student_no=?", (number,)).fetchone()
            if existing:
                db.execute("UPDATE user SET name=?,class_name=?,role='student',active=1,"
                           "password_hash=?,updated_at=? WHERE id=?",
                           (name, class_name, generate_password_hash(number), timestamp, existing["id"]))
                updated += 1
            else:
                db.execute("INSERT INTO user(student_no,name,class_name,password_hash,role,active,"
                           "created_at,updated_at) VALUES(?,?,?,?,'student',1,?,?)",
                           (number, name, class_name, generate_password_hash(number), timestamp, timestamp))
                created += 1
        print("学生账号：新建 %d，更新 %d" % (created, updated))

        # 课程成员只保留本名单，之前用于演示的账号置为非活动，避免座位图里混进无关的人
        keep = {number for _class, number, _name in roster}
        extra = db.execute(
            "SELECT m.id,u.student_no FROM course_member m JOIN user u ON u.id=m.user_id "
            "WHERE m.course_id=? AND m.member_role='student'", (course_id,)).fetchall()
        retired = 0
        for row in extra:
            if row["student_no"] not in keep:
                db.execute("UPDATE course_member SET active=0,updated_at=? WHERE id=?", (timestamp, row["id"]))
                retired += 1
        print("课程里清理掉非名单成员 %d 人" % retired)

        for class_name, number, _name in roster:
            student = db.execute("SELECT id FROM user WHERE student_no=?", (number,)).fetchone()
            db.execute("INSERT INTO course_member(course_id,user_id,member_role,active,created_at,updated_at) "
                       "VALUES(?,?,'student',1,?,?) "
                       "ON CONFLICT(course_id,user_id) DO UPDATE SET active=1,updated_at=excluded.updated_at",
                       (course_id, student["id"], timestamp, timestamp))

        db.execute("DELETE FROM class_seat WHERE course_id=?", (course_id,))
        placed = 0
        for class_name, rows in seats.items():
            for number, group, seat in rows:
                student = db.execute("SELECT id FROM user WHERE student_no=?", (number,)).fetchone()
                db.execute("INSERT INTO class_seat(course_id,student_id,class_name,group_no,seat_no,"
                           "created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                           (course_id, student["id"], class_name, group, seat, timestamp, timestamp))
                placed += 1
        print("座位：%d 个（课程 #%s）" % (placed, course_id))
        db.commit()
        print("已写库：%s" % path)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
