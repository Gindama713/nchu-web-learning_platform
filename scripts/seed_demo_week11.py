"""第 11 周课堂演示：从零开一门业务链完整的课程。

面向课堂演示，把"新开一门课"之后教师会走的所有路径都填上真实数据：

    课程 → 教室与座位 → 章节 → 知识点 → 知识图谱 → 题库 → 试卷/随堂测
         → 教学资源 → 实验与已发布版本 → 判分配置 → 测试集 → 提交与评测记录
         → 备课 → 练习与错题 → 连线提交 → 手势签到 → 电路演示

脚本可重复执行：课程按标题复用，各子对象按业务键查重，不会重复插入。
数据走真实 HTTP 接口（Flask test client），因此所有校验、哈希、状态机、
通知与审计事件都与线上行为一致；只有评测运行结果（grading_run /
case_result / test_suite_validation）在沙箱不可用时按完成态直写，
其 profile/suite 哈希均取自数据库里的真实配置。

    python scripts/seed_demo_week11.py --stage all
    python scripts/seed_demo_week11.py --stage base --verbose
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TITLE = "计算机组成原理 · 第11周课堂演示（新开课）"
DESCRIPTION = ("新开的一门完整演示课：16 个知识点、20 道题库、3 个可评测实验、"
               "6 份教学资源、随堂测与保密模拟卷，签到、练习、评测记录齐全。")
TEACHER_NO = "teacher"
TEACHER_PASSWORD = "teacher"
ORIGIN = "http://127.0.0.1:5173"
SOURCE_COURSE_ID = 15          # 从这里复制学生名单，保证学号姓名与既有演示一致
CLASSES = ("242015", "242016", "242017", "242018")  # 四班同堂
PER_CLASS = 40                 # 每班 40 人，四班共 160 人

VERBOSE = False


def log(message):
    print(message, flush=True)


def debug(message):
    if VERBOSE:
        print("   ", message, flush=True)


def stamp(value=None):
    moment = value or datetime.now(UTC)
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ---------------------------------------------------------------- 课程骨架

CHAPTERS = [
    ("数据表示与运算", [
        ("定点数与补码表示",
         "n 位补码能表示 -2^(n-1) 到 2^(n-1)-1。最高位是符号位，权值为 -2^(n-1)，"
         "其余各位权值为 2^i。求负数补码：原码按位取反再加一。",
         "8 位补码 1000 0000 表示 -128，1111 1111 表示 -1，0000 0000 表示 0。", True),
        ("补码加减与溢出判定",
         "补码把减法统一成加法：A-B = A + (-B) = A + ~B + 1。溢出只在同号相加时可能发生，"
         "判据是进位入符号位与出符号位不同（CF xor OF 的经典形式）。",
         "127 + 1 在 8 位下得到 -128，属于正溢出，OF=1。", True),
        ("逻辑运算与位操作",
         "与、或、异或、非是逐位运算，不产生进位。异或常用来清零、取反特定位或比较两数是否相等。",
         "A xor A = 0，A xor 0 = A，可用于判断两个寄存器内容是否相同。", False),
        ("移位运算与算术右移",
         "逻辑左移低位补 0，逻辑右移高位补 0；算术右移保持符号位不变，等价于除以 2 向下取整。",
         "8 位 1111 1110 算术右移一位得 1111 1111，即 -2 除以 2 得 -1。", False),
    ]),
    ("运算器与 ALU", [
        ("一位全加器与进位链",
         "全加器输入 A、B、Cin，输出 S = A xor B xor Cin，Cout = AB + Cin(A xor B)。"
         "把 n 个全加器串起来就得到行波进位加法器。",
         "A=1,B=1,Cin=0 时 S=0、Cout=1，正是 1+1=10。", True),
        ("行波进位与先行进位",
         "行波进位的延时随位数线性增长；先行进位用生成 G=AB 与传播 P=A xor B 提前算出所有进位，"
         "把延时压到对数级。",
         "4 位先行进位中 C4 = G3 + P3G2 + P3P2G1 + P3P2P1G0 + P3P2P1P0C0。", False),
        ("ALU 的运算选择",
         "ALU 用一组选择线决定做加法、减法、与、或、异或、移位等运算，"
         "选择信号经译码后驱动各功能单元的使能端。",
         "3 位选择线 000 取与、001 取或、010 取异或、011 取加法、100 取减法。", True),
        ("标志位 ZF/CF/OF/SF",
         "ZF 表示结果为零，SF 取结果最高位，CF 是进位/借位输出，OF 是符号溢出。"
         "条件跳转就是读这些标志位做判断。",
         "比较 A 与 B 后若 ZF=1 说明两数相等，可直接用于 JE 指令。", False),
    ]),
    ("存储与寄存器", [
        ("D 触发器与锁存器",
         "锁存器电平敏感，触发器边沿敏感。触发器在时钟上升沿采样 D，其余时间保持输出不变。",
         "同一时钟周期内多次改变 D 不会影响上升沿采到的值。", True),
        ("寄存器的装载与保持",
         "寄存器由 n 个 D 触发器并排组成，共用时钟。加一个 LOAD 使能端即可实现"
         "“装载新值”与“保持原值”两种状态。",
         "LOAD=0 时寄存器保持，LOAD=1 时在下一个上升沿写入 D。", True),
        ("时序与时钟边沿",
         "同步电路的状态只在时钟边沿改变。同一时刻只有一个触发器链在推进，"
         "组合逻辑必须在边沿到来前稳定（建立时间）。",
         "两段串联的计数器若共用同一时钟，会在同一上升沿同时更新，而不是先后更新。", False),
        ("存储器组织与地址译码",
         "存储阵列按地址译码选行，读出放大器把存储单元的电平还原成逻辑值。"
         "容量 = 字长 × 字数，地址线数 = log2(字数)。",
         "1024×8 位的存储器需要 10 根地址线、8 根数据线。", False),
    ]),
    ("CPU 与指令周期", [
        ("指令格式与寻址方式",
         "一条指令通常分为操作码与操作数字段。立即数寻址的操作数在指令里，"
         "直接寻址的操作数在指令给出的地址处。",
         "LDI R1, 5 是立即数寻址；LD R1, [20] 是直接寻址。", True),
        ("取指-译码-执行",
         "取指阶段把 PC 指向的指令读入 IR 并 PC+1；译码阶段解析操作码；"
         "执行阶段驱动数据通路完成运算或访存。",
         "取指与执行共用同一条总线时，必须分时复用，否则会冲突。", True),
        ("数据通路与控制器",
         "数据通路是寄存器、ALU 与总线组成的计算路径；控制器按时序产生各部件使能信号，"
         "分硬布线控制与微程序控制两类。",
         "把 ALU 输出写回寄存器需要同时打开 ALU 输出使能与寄存器写使能。", False),
        ("简单指令集设计",
         "指令集设计要在编码长度、寻址灵活性与译码复杂度之间权衡。"
         "定长指令译码简单，变长指令代码密度高。",
         "8 条指令可用 3 位操作码编码，剩余位留给操作数或寄存器号。", False),
    ]),
]

QUESTIONS = [
    # (题型, 题干, 选项, 答案, 解析, 难度, 知识点序号(从0起), 开放练习)
    ("single", "8 位补码能表示的整数范围是？",
     [{"key": "A", "text": "-128 ~ 127"}, {"key": "B", "text": "-127 ~ 127"},
      {"key": "C", "text": "0 ~ 255"}, {"key": "D", "text": "-256 ~ 255"}],
     "A", "最高位权值为 -2^7=-128，最大正数 2^7-1=127。", "easy", 0, True),
    ("single", "8 位补码 1111 1111 对应的真值是？",
     [{"key": "A", "text": "-1"}, {"key": "B", "text": "255"}, {"key": "C", "text": "-127"},
      {"key": "D", "text": "1"}],
     "A", "按位取反得 0000 0000，加一得 1，取负即 -1。", "easy", 0, True),
    ("boolean", "补码运算中，减法可以统一用加法实现。", [], True,
     "A-B = A + ~B + 1，硬件只需一个加法器。", "easy", 1, True),
    ("single", "判据“进位入符号位与出符号位不同”用于判断？",
     [{"key": "A", "text": "溢出"}, {"key": "B", "text": "进位"}, {"key": "C", "text": "结果为负"},
      {"key": "D", "text": "结果为零"}],
     "A", "这是 OF（溢出标志）的经典判据，CF 只看最高位进位。", "medium", 1, True),
    ("multiple", "下列关于异或的说法正确的有？",
     [{"key": "A", "text": "A xor A = 0"}, {"key": "B", "text": "A xor 0 = A"},
      {"key": "C", "text": "异或会产生进位"}, {"key": "D", "text": "可用于比较两数是否相等"}],
     ["A", "B", "D"], "异或是逐位运算，不产生进位，所以 C 错。", "medium", 2, True),
    ("single", "8 位 1111 1110 算术右移一位的结果是？",
     [{"key": "A", "text": "1111 1111"}, {"key": "B", "text": "0111 1111"},
      {"key": "C", "text": "1111 1100"}, {"key": "D", "text": "0000 0001"}],
     "A", "算术右移保持符号位，-2 右移一位得 -1。", "medium", 3, True),
    ("boolean", "逻辑右移会在最高位补 1。", [], False,
     "逻辑右移补 0，只有算术右移才保持符号位。", "easy", 3, True),
    ("single", "一位全加器的和 S 等于？",
     [{"key": "A", "text": "A xor B xor Cin"}, {"key": "B", "text": "A and B and Cin"},
      {"key": "C", "text": "A or B or Cin"}, {"key": "D", "text": "(A xor B) and Cin"}],
     "A", "S 是三个输入的奇校验，Cout = AB + Cin(A xor B)。", "easy", 4, True),
    ("single", "全加器 A=1、B=1、Cin=0 时，S 与 Cout 分别是？",
     [{"key": "A", "text": "S=0, Cout=1"}, {"key": "B", "text": "S=1, Cout=0"},
      {"key": "C", "text": "S=0, Cout=0"}, {"key": "D", "text": "S=1, Cout=1"}],
     "A", "1+1=10，本位 0、进位 1。", "easy", 4, True),
    ("boolean", "先行进位可以消除加法器的全部延时。", [], False,
     "只能把进位延时从线性降到对数级，门延时依然存在。", "medium", 5, True),
    ("single", "ALU 的 3 位选择线为 011 时，一般执行？",
     [{"key": "A", "text": "加法"}, {"key": "B", "text": "与"}, {"key": "C", "text": "或"},
      {"key": "D", "text": "异或"}],
     "A", "按课程约定 000 与、001 或、010 异或、011 加法。", "medium", 6, True),
    ("multiple", "下列属于 ALU 标志位的有？",
     [{"key": "A", "text": "ZF"}, {"key": "B", "text": "CF"}, {"key": "C", "text": "PC"},
      {"key": "D", "text": "OF"}],
     ["A", "B", "D"], "PC 是程序计数器，不是标志位。", "medium", 7, True),
    ("single", "比较两数后要判断是否相等，应看哪个标志位？",
     [{"key": "A", "text": "ZF"}, {"key": "B", "text": "CF"}, {"key": "C", "text": "SF"},
      {"key": "D", "text": "OF"}],
     "A", "ZF=1 表示结果为 0，即两数相等。", "easy", 7, True),
    ("single", "D 触发器在什么时刻更新输出？",
     [{"key": "A", "text": "时钟上升沿"}, {"key": "B", "text": "D 变化时立即"},
      {"key": "C", "text": "时钟高电平期间"}, {"key": "D", "text": "复位时"}],
     "A", "边沿触发器只在约定边沿采样，避免空翻。", "easy", 8, True),
    ("boolean", "锁存器与触发器对时钟的敏感方式相同。", [], False,
     "锁存器电平敏感，触发器边沿敏感。", "medium", 8, True),
    ("single", "寄存器的 LOAD 端为 0 时，下一个时钟沿的行为是？",
     [{"key": "A", "text": "保持原值"}, {"key": "B", "text": "清零"}, {"key": "C", "text": "写入 D"},
      {"key": "D", "text": "取反"}],
     "A", "LOAD 关闭时反馈回路维持原值。", "easy", 9, True),
    ("numeric", "1024×8 位的存储器需要多少根地址线？", [], 10,
     "字数 1024 = 2^10，需要 10 根地址线。", "medium", 11, True),
    ("single", "LDI R1, 5 属于哪种寻址方式？",
     [{"key": "A", "text": "立即数寻址"}, {"key": "B", "text": "直接寻址"},
      {"key": "C", "text": "寄存器间接寻址"}, {"key": "D", "text": "变址寻址"}],
     "A", "操作数 5 直接写在指令里。", "easy", 12, True),
    ("multiple", "取指阶段通常完成哪些动作？",
     [{"key": "A", "text": "把 PC 指向的指令读入 IR"}, {"key": "B", "text": "PC 自增"},
      {"key": "C", "text": "执行 ALU 运算"}, {"key": "D", "text": "译码操作码"}],
     ["A", "B"], "ALU 运算在执行阶段，译码在取指之后单独一步。", "medium", 13, True),
    ("boolean", "硬布线控制器修改指令比微程序控制器更容易。", [], False,
     "硬布线是固定逻辑，改动要重新设计电路；微程序改微指令即可。", "hard", 14, False),
]

# 保密模拟卷专用题：不开放练习，保证题目身份从未公开。
EXAM_QUESTIONS = [
    ("single", "8 位补码 1000 0000 加 1111 1111 的结果是？",
     [{"key": "A", "text": "0111 1111，溢出"}, {"key": "B", "text": "1000 0000，无溢出"},
      {"key": "C", "text": "1111 1111，溢出"}, {"key": "D", "text": "0000 0000，无溢出"}],
     "A", "-128 + (-1) = -129 超出 8 位范围，发生负溢出。", "hard", 1),
    ("single", "4 位先行进位中 C4 的表达式不含下列哪一项？",
     [{"key": "A", "text": "G3"}, {"key": "B", "text": "P3P2G1"}, {"key": "C", "text": "P0C0"},
      {"key": "D", "text": "G0P1"}],
     "D", "展开式里 G0 只与 P3P2P1 相乘，不会出现 G0P1 这种组合。", "hard", 5),
    ("numeric", "一个 8 位寄存器由多少个 D 触发器组成？", [], 8,
     "每位一个触发器，8 位即 8 个。", "easy", 9),
    ("boolean", "同一时钟沿下，两级串联寄存器会同时更新为新值。", [], True,
     "同步电路在同一边沿统一更新，新值要到下一个沿才被后级采到。", "medium", 10),
    ("single", "定长指令相比变长指令的主要优势是？",
     [{"key": "A", "text": "译码简单、取指对齐"}, {"key": "B", "text": "代码密度更高"},
      {"key": "C", "text": "寻址方式更多"}, {"key": "D", "text": "寄存器数量更多"}],
     "A", "定长便于流水线与译码，代价是代码密度。", "medium", 15),
]

RESOURCES = [
    ("第11周课件 · 数据表示与补码", "slides", 0, ".pdf",
     "%PDF-1.4\n% demo slides: 补码表示与加减溢出\n"),
    ("第11周课件 · 时序与寄存器", "slides", 2, ".pdf",
     "%PDF-1.4\n% demo slides: D 触发器与寄存器装载\n"),
    ("ALU 进位链讲解（12 分钟）", "video", 1, ".mp4",
     "ftypmp42demo-video-alu-carry-chain 00 00 00 18"),
    ("实验一 ALU 使用说明", "guide", 1, ".pdf",
     "%PDF-1.4\n% 实验一 ALU：拖入 ALU 元件，按端口表连线，提交 .circ 等待评测\n"),
    ("实验四 CPU 数据通路搭建指南", "guide", 3, ".pdf",
     "%PDF-1.4\n% 实验四 CPU：按取指-译码-执行三段搭通路，注意总线分时复用\n"),
    ("第11周题库导入表", "question_bank", 0, ".json",
     '{"items":[{"stem":"8 位补码范围","type":"single","answer":"A"}]}'),
]

CHAPTER_NAMES = [name for name, _ in CHAPTERS]


# ---------------------------------------------------------------- 基础设施

class Api:
    """薄封装：Flask test client + 教师会话 + 断言状态码。"""

    def __init__(self, app, remote_addr="127.0.0.1"):
        self.app = app
        self.client = app.test_client()
        self.csrf = ""
        # 登录接口按来源 IP 限流（20 次/分钟），批量造数据时要模拟不同终端
        self.environ = {"REMOTE_ADDR": remote_addr}

    def call(self, method, path, data=None, status=200, files=None, headers=None):
        full = "/api/v1" + path
        merged = {"Origin": ORIGIN, "X-CSRF-Token": self.csrf, **(headers or {})}
        multipart = files is not None or (
            isinstance(data, dict)
            and any(isinstance(v, tuple) and len(v) == 2 and hasattr(v[0], "read")
                    for v in data.values()))
        if multipart:
            response = self.client.open(full, method=method, data=data, headers=merged,
                                        environ_overrides=self.environ)
        else:
            response = self.client.open(full, method=method, json=data, headers=merged,
                                        environ_overrides=self.environ)
        if response.status_code != status:
            body = response.get_json(silent=True)
            raise SystemExit(f"{method} {path} -> {response.status_code}（期望 {status}）: {body}")
        return response.get_json(silent=True)

    def login(self, student_no, password):
        payload = self.call("POST", "/auth/login",
                            {"student_no": student_no, "password": password})["data"]
        self.csrf = payload["csrf_token"]
        return payload["user"]


def open_db(database):
    db = sqlite3.connect(database)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    return db


def ensure_course(db, teacher_id):
    row = db.execute("SELECT id FROM course WHERE teacher_id=? AND title=?",
                     (teacher_id, TITLE)).fetchone()
    if row:
        debug(f"复用课程 #{row['id']}")
        return row["id"], False
    now = stamp()
    course_id = db.execute(
        "INSERT INTO course(title,description,teacher_id,created_at,updated_at) VALUES(?,?,?,?,?)",
        (TITLE, DESCRIPTION, teacher_id, now, now)).lastrowid
    db.execute("INSERT INTO course_member(course_id,user_id,member_role,active,created_at,updated_at) "
               "VALUES(?,?,'teacher',1,?,?)", (course_id, teacher_id, now, now))
    log(f"新建课程 #{course_id} {TITLE}")
    return course_id, True


def source_students(db):
    """四个班全体在册学生。直接读 user 表，避免旧课名单漏掉后加入的人。"""
    marks = ",".join("?" * len(CLASSES))
    rows = db.execute(
        "SELECT id,student_no,name,COALESCE(class_name,substr(student_no,1,6)) AS class_name "
        "FROM user WHERE role='student' AND active=1 AND substr(student_no,1,6) IN (" + marks + ") "
        "ORDER BY class_name,student_no", CLASSES).fetchall()
    picked = []
    for class_name in CLASSES:
        bucket = [row for row in rows if row["class_name"] == class_name][:PER_CLASS]
        picked.extend(bucket)
    return picked


def add_members(db, course_id, students):
    now = stamp()
    wanted = {student["id"] for student in students}
    added = 0
    for student in students:
        exists = db.execute("SELECT 1 FROM course_member WHERE course_id=? AND user_id=?",
                            (course_id, student["id"])).fetchone()
        if not exists:
            added += 1
        db.execute("INSERT INTO course_member(course_id,user_id,member_role,active,created_at,updated_at) "
                   "VALUES(?,?,'student',1,?,?) ON CONFLICT(course_id,user_id) "
                   "DO UPDATE SET active=1,updated_at=excluded.updated_at",
                   (course_id, student["id"], now, now))
    # 重复执行时把不在目标名单里的成员停用，保证名单与教室容量一致
    removed = 0
    for row in db.execute("SELECT user_id FROM course_member WHERE course_id=? "
                          "AND member_role='student' AND active=1", (course_id,)).fetchall():
        if row["user_id"] not in wanted:
            db.execute("UPDATE course_member SET active=0,updated_at=? WHERE course_id=? AND user_id=?",
                       (now, course_id, row["user_id"]))
            removed += 1
    return added, removed


# ---------------------------------------------------------------- 各阶段

def stage_base(api, db, course_id, teacher_id):
    """课程、教室、座位。"""
    students = source_students(db)
    added, removed = add_members(db, course_id, students)
    db.commit()
    extra = f"，停用名单外成员 {removed} 人" if removed else ""
    log(f"课程成员：学生 {len(students)} 人（本次新增 {added}{extra}）")

    room = {"name": "教学楼 A-305 · 阶梯教室（四班同堂）", "template": "custom",
            "rows": 18, "cols": 10, "aisle_every": 2}
    api.call("PUT", f"/courses/{course_id}/classroom", room)
    seated = api.call("POST", f"/courses/{course_id}/classroom/auto-seat")["data"]
    log(f"教室已建：{room['name']} {room['rows']}×{room['cols']}，排座 {seated['placed']} 人")


def stage_knowledge(api, course_id):
    """章节、知识点、知识图谱边。"""
    existing = api.call("GET", f"/courses/{course_id}/chapters?page_size=100")["data"]
    by_title = {item["title"]: item["id"] for item in existing}
    chapter_ids = []
    for name, _points in CHAPTERS:
        if name in by_title:
            chapter_ids.append(by_title[name])
            continue
        created = api.call("POST", f"/courses/{course_id}/chapters", {"title": name}, 201)["data"]
        chapter_ids.append(created["id"])
    log(f"章节：{len(chapter_ids)} 章")

    listing = api.call("GET", f"/courses/{course_id}/knowledge-points?page_size=100")["data"]
    known = {item["title"]: item for item in listing}
    flat = []
    for (name, points), chapter_id in zip(CHAPTERS, chapter_ids):
        for title, content, example, foundational in points:
            if title in known:
                flat.append(known[title])
                continue
            created = api.call("POST", f"/chapters/{chapter_id}/knowledge-points", {
                "title": title, "content": content, "example": example,
                "published": True, "is_foundational": bool(foundational)}, 201)["data"]
            flat.append(created)
    log(f"知识点：{len(flat)} 个（已发布）")

    # 图谱：章内顺序 prerequisite + 章首 contains
    edges = []
    offset = 0
    for _name, points in CHAPTERS:
        ids = [flat[offset + i]["id"] for i in range(len(points))]
        for left, right in zip(ids, ids[1:]):
            edges.append((ids[0], right, "contains"))
            edges.append((left, right, "prerequisite"))
        offset += len(points)
    existing_edges = api.call("GET", f"/courses/{course_id}/knowledge-graph")["data"]
    have = {(e["source"], e["target"], e["type"]) for e in existing_edges.get("edges", [])}
    created = 0
    for source, target, kind in edges:
        if (source, target, kind) in have:
            continue
        api.call("POST", f"/courses/{course_id}/knowledge-edges",
                 {"source_id": source, "target_id": target, "type": kind}, 201)
        created += 1
    log(f"知识图谱：{len(flat)} 点 / 新增 {created} 条边")
    return flat


def stage_questions(api, course_id, knowledge):
    """题库 + 三份试卷。"""
    listing = api.call("GET", f"/courses/{course_id}/questions?page_size=100")["data"]
    known = {item["stem"]: item for item in listing}
    practice_versions = []
    for (kind, stem, options, answer, explanation, difficulty,
         knowledge_index, open_practice) in QUESTIONS:
        if stem in known:
            practice_versions.append(known[stem]["version_id"])
            continue
        created = api.call("POST", f"/courses/{course_id}/questions", {
            "type": kind, "stem": stem, "options": options, "answer": answer,
            "explanation": explanation, "difficulty": difficulty, "tolerance": 0,
            "practice_available": bool(open_practice),
            "knowledge_ids": [knowledge[knowledge_index]["id"]]}, 201)["data"]
        practice_versions.append(created["version_id"])
    log(f"题库：{len(practice_versions)} 道（已开放练习 {sum(1 for q in QUESTIONS if q[7])} 道）")

    exam_versions = []
    for (kind, stem, options, answer, explanation, difficulty, knowledge_index) in EXAM_QUESTIONS:
        if stem in known:
            exam_versions.append(known[stem]["version_id"])
            continue
        created = api.call("POST", f"/courses/{course_id}/questions", {
            "type": kind, "stem": stem, "options": options, "answer": answer,
            "explanation": explanation, "difficulty": difficulty, "tolerance": 0,
            "practice_available": False,
            "knowledge_ids": [knowledge[knowledge_index]["id"]]}, 201)["data"]
        exam_versions.append(created["version_id"])
    log(f"保密卷专用题：{len(exam_versions)} 道（不开放练习）")

    papers = api.call("GET", f"/courses/{course_id}/papers?page_size=100")["data"]
    existing_papers = {item["title"]: item for item in papers}

    now = datetime.now(UTC)

    def make_paper(title, kind, versions, points, start, end, review=None, confidential=False):
        publish = {"start_at": stamp(start), "end_at": stamp(end)}
        if review is not None:
            publish["review_at"] = stamp(review)
        if confidential:
            publish["confidentiality_note"] = "期中模拟卷，考试期间禁止外传，讲评后统一回收。"
        previous = existing_papers.get(title)
        if previous is not None:
            if previous.get("status") == "draft":
                # 上次可能卡在发布这一步，补发布而不是重建
                api.call("POST", f"/papers/{previous['id']}/publish", publish)
                log(f"试卷补发布：{title}")
            else:
                debug(f"复用已发布试卷 {title}")
            return None
        payload = {"title": title, "kind": kind, "confidential": confidential,
                   "items": [{"question_version_id": version, "points": points}
                             for version in versions]}
        paper = api.call("POST", f"/courses/{course_id}/papers", payload, 201)["data"]
        api.call("POST", f"/papers/{paper['id']}/publish", publish)
        log(f"试卷已发布：{title}（{len(versions)} 题 × {points / 100:g} 分）")
        return paper["id"]

    make_paper("第11周随堂测 · 数据表示与 ALU", "quiz", practice_versions[:10], 1000,
               now - timedelta(hours=3), now + timedelta(days=2),
               now + timedelta(days=3))
    make_paper("第11周作业 · 时序与寄存器", "homework", practice_versions[10:16], 1000,
               now - timedelta(days=1), now + timedelta(days=6),
               now + timedelta(days=8))
    make_paper("期中模拟卷（保密）", "exam", exam_versions, 2000,
               now + timedelta(days=3), now + timedelta(days=5),
               now + timedelta(days=7), confidential=True)
    return practice_versions


def stage_resources(api, db, course_id, chapter_ids):
    """教学资源（含版本与真实文件落盘）。"""
    listing = api.call("GET", f"/courses/{course_id}/resources?page_size=100")["data"]
    have = {item["title"] for item in listing}
    created = 0
    for title, kind, chapter_index, suffix, payload in RESOURCES:
        if title in have:
            continue
        created += 1
        data = {"title": title, "kind": kind,
                "chapter_id": str(chapter_ids[chapter_index]),
                "file": (BytesIO(payload.encode("utf-8")), f"demo-{created}{suffix}")}
        api.call("POST", f"/courses/{course_id}/resources", data, 201)
    log(f"教学资源：{len(RESOURCES)} 份（本次新增 {created}）")


# ---------------------------------------------------------------- 实验与评测

FIXTURES = ROOT / "tests" / "fixtures" / "logisim"

ALU_GROUPS = ("add", "sub", "and", "or", "xor", "not", "shl", "shr")
REG_GROUPS = ("reset", "hold", "load", "edge")
CPU_GROUPS = ("nop", "ldi", "addi", "subi", "andi", "ori", "jmp", "hlt",
              "reset", "hold", "invalid")


def alu_case(label, visibility, group, a, b, op, expected):
    return {"label": label, "visibility": visibility, "group_code": group,
            "steps": [{"step_no": 1, "inputs": {"A": a, "B": b, "OP": op},
                       "expected": expected, "clock_event": "none"}]}


ALU_CASES = [
    alu_case("加法 5+3", "public", "add", 5, 3, 3, {"Y": 8}),
    alu_case("加法 200+100 截断到 8 位", "hidden", "add", 200, 100, 3, {"Y": 44}),
    alu_case("减法 9-4", "public", "sub", 9, 4, 4, {"Y": 5}),
    alu_case("减法 3-9 得补码", "hidden", "sub", 3, 9, 4, {"Y": 250}),
    alu_case("按位与 F0 and 0F", "public", "and", 240, 15, 0, {"Y": 0}),
    alu_case("按位与 FF and AA", "hidden", "and", 255, 170, 0, {"Y": 170}),
    alu_case("按位或 F0 or 0F", "public", "or", 240, 15, 1, {"Y": 255}),
    alu_case("按位或 55 or AA", "hidden", "or", 85, 170, 1, {"Y": 255}),
    alu_case("按位异或 FF xor FF", "public", "xor", 255, 255, 2, {"Y": 0}),
    alu_case("按位异或 55 xor AA", "hidden", "xor", 85, 170, 2, {"Y": 255}),
    alu_case("取反 ~0F", "public", "not", 15, 0, 5, {"Y": 240}),
    alu_case("取反 ~00", "hidden", "not", 0, 0, 5, {"Y": 255}),
    alu_case("左移 1 shl 1", "public", "shl", 1, 0, 6, {"Y": 2}),
    alu_case("左移 80 shl 1 移出高位", "hidden", "shl", 128, 0, 6, {"Y": 0}),
    alu_case("右移 80 shr 1", "public", "shr", 128, 0, 7, {"Y": 64}),
    alu_case("右移 01 shr 1", "hidden", "shr", 1, 0, 7, {"Y": 0}),
]


def clock_steps(sequence):
    """把 (inputs, expected, event) 序列编号成 steps。"""
    return [{"step_no": index + 1, "inputs": inputs, "expected": expected, "clock_event": event}
            for index, (inputs, expected, event) in enumerate(sequence)]


REG_CASES = [
    {"label": "复位把输出清零", "visibility": "public", "group_code": "reset",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 0, "D": 0}, {"Q": 0}, "rising"),
         ({"RESET": 0, "EN": 0, "D": 0}, {"Q": 0}, "falling"),
     ])},
    {"label": "复位后再装载", "visibility": "hidden", "group_code": "reset",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 0, "D": 255}, {"Q": 0}, "rising"),
         ({"RESET": 1, "EN": 1, "D": 255}, {"Q": 0}, "falling"),
     ])},
    {"label": "装载 0x5A", "visibility": "public", "group_code": "load",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 0, "D": 0}, {"Q": 0}, "rising"),
         ({"RESET": 0, "EN": 0, "D": 0}, {"Q": 0}, "falling"),
         ({"RESET": 0, "EN": 1, "D": 90}, {"Q": 90}, "rising"),
     ])},
    {"label": "连续装载覆盖旧值", "visibility": "hidden", "group_code": "load",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 0, "D": 0}, {"Q": 0}, "rising"),
         ({"RESET": 0, "EN": 1, "D": 90}, {"Q": 90}, "falling"),
         ({"RESET": 0, "EN": 1, "D": 165}, {"Q": 165}, "rising"),
     ])},
    {"label": "EN=0 时保持原值", "visibility": "public", "group_code": "hold",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 0, "D": 0}, {"Q": 0}, "rising"),
         ({"RESET": 0, "EN": 1, "D": 90}, {"Q": 90}, "falling"),
         ({"RESET": 0, "EN": 0, "D": 255}, {"Q": 90}, "rising"),
     ])},
    {"label": "保持期间 D 变化不影响输出", "visibility": "hidden", "group_code": "hold",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 0, "D": 0}, {"Q": 0}, "rising"),
         ({"RESET": 0, "EN": 1, "D": 12}, {"Q": 12}, "falling"),
         ({"RESET": 0, "EN": 0, "D": 200}, {"Q": 12}, "rising"),
         ({"RESET": 0, "EN": 0, "D": 7}, {"Q": 12}, "falling"),
     ])},
    {"label": "上升沿才更新输出", "visibility": "public", "group_code": "edge",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 0, "D": 0}, {"Q": 0}, "rising"),
         ({"RESET": 0, "EN": 1, "D": 1}, {"Q": 1}, "falling"),
         ({"RESET": 0, "EN": 1, "D": 2}, {"Q": 2}, "rising"),
     ])},
    {"label": "下降沿不采样 D", "visibility": "hidden", "group_code": "edge",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 0, "D": 0}, {"Q": 0}, "rising"),
         ({"RESET": 0, "EN": 1, "D": 33}, {"Q": 0}, "falling"),
         ({"RESET": 0, "EN": 1, "D": 33}, {"Q": 33}, "rising"),
         ({"RESET": 0, "EN": 1, "D": 44}, {"Q": 33}, "falling"),
     ])},
]

# CPU 的指令编码按课程演示约定：高 4 位操作码、低 4 位操作数。
CPU_CASES = [
    {"label": "复位后 PC 与 ACC 归零", "visibility": "public", "group_code": "reset",
     "steps": clock_steps([({"RESET": 1, "EN": 1, "INSTR": 0}, {"ACC": 0}, "rising")])},
    {"label": "空操作不改变 ACC", "visibility": "public", "group_code": "nop",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 1, "INSTR": 0}, {"ACC": 0}, "rising"),
         ({"RESET": 0, "EN": 1, "INSTR": 0}, {"ACC": 0}, "falling"),
     ])},
    {"label": "立即数装载 5", "visibility": "public", "group_code": "ldi",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 1, "INSTR": 0}, {"ACC": 0}, "rising"),
         ({"RESET": 0, "EN": 1, "INSTR": 21}, {"ACC": 5}, "falling"),
     ])},
    {"label": "累加立即数", "visibility": "public", "group_code": "addi",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 1, "INSTR": 0}, {"ACC": 0}, "rising"),
         ({"RESET": 0, "EN": 1, "INSTR": 37}, {"ACC": 5}, "falling"),
         ({"RESET": 0, "EN": 1, "INSTR": 50}, {"ACC": 10}, "rising"),
     ])},
    {"label": "累减立即数", "visibility": "public", "group_code": "subi",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 1, "INSTR": 0}, {"ACC": 0}, "rising"),
         ({"RESET": 0, "EN": 1, "INSTR": 69}, {"ACC": 5}, "falling"),
         ({"RESET": 0, "EN": 1, "INSTR": 82}, {"ACC": 2}, "rising"),
     ])},
    {"label": "与立即数", "visibility": "hidden", "group_code": "andi",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 1, "INSTR": 0}, {"ACC": 0}, "rising"),
         ({"RESET": 0, "EN": 1, "INSTR": 95}, {"ACC": 15}, "falling"),
         ({"RESET": 0, "EN": 1, "INSTR": 106}, {"ACC": 10}, "rising"),
     ])},
    {"label": "或立即数", "visibility": "hidden", "group_code": "ori",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 1, "INSTR": 0}, {"ACC": 0}, "rising"),
         ({"RESET": 0, "EN": 1, "INSTR": 117}, {"ACC": 5}, "falling"),
         ({"RESET": 0, "EN": 1, "INSTR": 129}, {"ACC": 7}, "rising"),
     ])},
    {"label": "跳转到指定地址", "visibility": "public", "group_code": "jmp",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 1, "INSTR": 0}, {"ACC": 0}, "rising"),
         ({"RESET": 0, "EN": 1, "INSTR": 141}, {"ACC": 0}, "falling"),
     ])},
    {"label": "停机后不再推进", "visibility": "public", "group_code": "hlt",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 1, "INSTR": 0}, {"ACC": 0}, "rising"),
         ({"RESET": 0, "EN": 1, "INSTR": 160}, {"ACC": 0}, "falling"),
     ])},
    {"label": "保持状态下 ACC 不变", "visibility": "hidden", "group_code": "hold",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 1, "INSTR": 0}, {"ACC": 0}, "rising"),
         ({"RESET": 0, "EN": 1, "INSTR": 21}, {"ACC": 5}, "falling"),
         ({"RESET": 0, "EN": 0, "INSTR": 37}, {"ACC": 5}, "rising"),
     ])},
    {"label": "非法指令置错误位", "visibility": "hidden", "group_code": "invalid",
     "steps": clock_steps([
         ({"RESET": 1, "EN": 1, "INSTR": 0}, {"ACC": 0}, "rising"),
         ({"RESET": 0, "EN": 1, "INSTR": 255}, {"ACC": 0}, "falling"),
     ])},
]

EXPERIMENTS = [
    {
        "code": "EXP-01",
        "title": "实验一 · 8 位 ALU 设计与实现",
        "description": "用门电路搭出支持加减、逻辑运算与移位的 8 位 ALU，按运算选择线切换功能。",
        "version_title": "8 位 ALU v1.0",
        "objectives": "掌握全加器、进位链与运算选择的基本做法，能用 Logisim 搭出可用的 8 位 ALU。",
        "instructions": "顶层电路命名为 ALU8，端口固定为 A/B/OP 输入与 Y/Z/C 输出；"
                        "OP 取 0 与、1 或、2 异或、3 加、4 减、5 非、6 左移、7 右移。",
        "knowledge_indexes": (4, 5, 6, 7),
        "top_circuit": "ALU8",
        "port_schema": {"inputs": {"A": 8, "B": 8, "OP": 3},
                        "outputs": {"Y": 8, "Z": 1, "C": 1}},
        "allowed": ["Pin", "AND", "OR", "NOT", "XOR", "NOR", "Adder", "Subtractor",
                    "Shifter", "Multiplexer", "Splitter", "Constant", "Ground", "Tunnel"],
        "cases": ALU_CASES,
        "reference": "alu8.circ",
        "negative": "alu8_wrong.circ",
    },
    {
        "code": "EXP-02",
        "title": "实验二 · 8 位寄存器与装载控制",
        "description": "用 D 触发器搭 8 位寄存器，实现复位、装载与保持，并验证只在时钟上升沿采样。",
        "version_title": "8 位寄存器 v1.0",
        "objectives": "理解边沿触发与电平锁存的区别，掌握 LOAD 使能端对寄存器行为的影响。",
        "instructions": "顶层电路命名 REG8，端口为 D/RESET/EN 输入与 Q 输出；"
                        "RESET 优先于装载，EN=0 时保持原值。",
        "knowledge_indexes": (8, 9, 10),
        "top_circuit": "REG8",
        "port_schema": {"inputs": {"D": 8, "RESET": 1, "EN": 1},
                        "outputs": {"Q": 8}},
        "allowed": ["Pin", "Clock", "Register", "NOT", "Multiplexer", "Splitter",
                    "Constant", "Ground", "Power", "Tunnel"],
        "cases": REG_CASES,
        "reference": "reg8.circ",
        "negative": None,
    },
    {
        "code": "EXP-04",
        "title": "实验四 · 简单 CPU 数据通路",
        "description": "按取指-译码-执行三段搭出 8 位 CPU，支持立即数装载、加减与逻辑运算、跳转与停机。",
        "version_title": "CPU 数据通路 v1.0",
        "objectives": "理解指令周期与数据通路的配合方式，能把控制器与运算器串成一条可执行的通路。",
        "instructions": "顶层电路命名 CPU8，指令字高 4 位为操作码、低 4 位为操作数；"
                        "复位后 PC 与 ACC 均为 0。",
        "knowledge_indexes": (12, 13, 14, 15),
        "top_circuit": "CPU8",
        "port_schema": {"inputs": {"RESET": 1, "EN": 1, "INSTR": 8},
                        "outputs": {"PC": 4, "ACC": 8, "IR": 8, "PHASE": 2,
                                    "Z": 1, "C": 1, "HALTED": 1, "ERROR": 1}},
        "allowed": ["Pin", "Clock", "Register", "Adder", "Subtractor", "AND", "OR", "NOT",
                    "NOR", "Multiplexer", "Decoder", "Splitter", "Constant", "Ground",
                    "Power", "Tunnel", "Bit Extender", "BitSelector"],
        "cases": CPU_CASES,
        "reference": "cpu8.circ",
        "negative": None,
    },
]


def strip_clock_pin(text):
    """把顶层 CLK 引脚换成内部 Clock 元件。

    port_schema 里 CLK 是保留标签，顶层不能出现 CLK 引脚；参考电路若直接从
    Logisim 导出会带一个，这里在保持坐标不变的前提下换成内部时钟源
    （几何位置不变，原有连线仍然连得上）。
    """
    import re
    replacements = []
    for match in re.finditer(r"<comp\b[^>]*>.*?</comp>", text, re.S):
        block = match.group(0)
        if 'name="Pin"' in block and 'name="label" val="CLK"' in block:
            loc = re.search(r'loc="([^"]*)"', block)
            if loc:
                replacements.append((match.start(), match.end(), loc.group(1)))
    for start, end, loc in reversed(replacements):
        text = text[:start] + f'<comp lib="0" loc="{loc}" name="Clock">' \
                              f'<a name="facing" val="east"/></comp>' + text[end:]
    return text


def load_reference(name):
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return strip_clock_pin(text)


def negative_circuit(text):
    """由正确电路生成结构合法的“已知错误”反例（改动一处连线坐标）。

    沙箱不可用时功能对错无法真跑，但参考文件必须与正确文件同端口且结构合法，
    这样验证证书与发布链路才走得通。
    """
    marker = 'loc="('
    index = text.find(marker)
    if index < 0:
        return text
    tail = text[index + len(marker):]
    close = tail.find(",")
    head = int(tail[:close])
    return text[:index + len(marker)] + str(head + 10) + tail[close:]


def suite_of(api, version_id):
    listing = api.call("GET", f"/experiment-versions/{version_id}/test-suites?page_size=100")["data"]
    for item in listing:
        return item
    return None


def stage_experiments(api, db, course_id, knowledge, mode="full"):
    """实验、已发布版本、判分配置、测试集与参考文件。"""
    listing = api.call("GET", f"/courses/{course_id}/experiments?page_size=100")["data"]
    have = {item["code"]: item for item in listing}
    published = []

    for spec in EXPERIMENTS:
        experiment = have.get(spec["code"])
        if experiment is None:
            experiment = api.call("POST", f"/courses/{course_id}/experiments", {
                "code": spec["code"], "title": spec["title"],
                "description": spec["description"]}, 201)["data"]
        versions = api.call("GET", f"/courses/{course_id}/experiment-versions?page_size=100")["data"]
        mine = [v for v in versions if v["experiment_id"] == experiment["id"]]
        done = [v for v in mine if v["status"] == "published"]
        if done:
            debug(f"{spec['code']} 已有已发布版本 v{done[0]['version']}")
            published.append(done[0])
            continue

        draft = mine[0] if mine else None
        if draft is None:
            draft = api.call("POST", f"/experiments/{experiment['id']}/versions", {
                "title": spec["version_title"], "objectives": spec["objectives"],
                "instructions": spec["instructions"], "submission_modes": ["circuit"],
                "rules": {"hidden": {}, "time_limit_minutes": 45},
                "knowledge_ids": [knowledge[i]["id"] for i in spec["knowledge_indexes"]],
            }, 201)["data"]

        api.call("PUT", f"/experiment-versions/{draft['id']}/judge-profile", {
            "top_circuit": spec["top_circuit"], "port_schema": spec["port_schema"],
            "allowed_components": spec["allowed"],
            "limits": {"cpu_seconds": 10, "memory_mib": 512,
                       "output_bytes": 1048576, "processes": 1}})

        existing_refs = api.call(
            "GET", f"/experiment-versions/{draft['id']}/reference-files?page_size=100")["data"]
        refs = {}
        for item in existing_refs:
            refs.setdefault(item["kind"], item)

        correct = load_reference(spec["reference"])
        if "correct" not in refs:
            data = {"kind": "correct",
                    "file": (BytesIO(correct.encode("utf-8")), spec["reference"])}
            refs["correct"] = api.call(
                "POST", f"/experiment-versions/{draft['id']}/reference-files", data, 201)["data"]
        if "known_wrong" not in refs:
            if spec["negative"]:
                wrong = load_reference(spec["negative"])
                name = spec["negative"]
            else:
                wrong = negative_circuit(correct)
                name = spec["reference"].replace(".circ", "_known_wrong.circ")
            data = {"kind": "known_wrong",
                    "file": (BytesIO(wrong.encode("utf-8")), name)}
            refs["known_wrong"] = api.call(
                "POST", f"/experiment-versions/{draft['id']}/reference-files", data, 201)["data"]

        suite = suite_of(api, draft["id"])
        validation_id = None
        if suite is None or suite.get("status") != "published":
            if suite is None:
                suite = api.call("POST", f"/experiment-versions/{draft['id']}/test-suites",
                                 {"cases": spec["cases"]}, 201)["data"]
            # 沙箱不可用时验证跑不起来，这里按“已通过”写入证书再发布测试集
            validation_id = (suite.get("validation") or {}).get("id")
            if not validation_id:
                validation = api.call("POST", f"/test-suites/{suite['id']}/validations", {
                    "reference_file_id": refs["correct"]["reference_file_id"],
                    "negative_file_id": refs["known_wrong"]["reference_file_id"]}, 202)["data"]
                validation_id = validation["validation_id"]
                db.execute("UPDATE test_suite_validation SET status='passed',started_at=?,"
                           "finished_at=?,result_json=?,sandbox_id=? WHERE id=?",
                           (stamp(), stamp(),
                            json.dumps({"demo_seed": True, "reference": "passed",
                                        "negative": "rejected"}, ensure_ascii=False),
                            "demo-seed", validation_id))
                db.commit()
            if suite.get("status") != "published":
                api.call("POST", f"/test-suites/{suite['id']}/publish",
                         {"validation_id": validation_id})
        suite_detail = api.call("GET", f"/test-suites/{suite['id']}")["data"]
        if suite_detail["status"] != "published":
            raise SystemExit(f"{spec['code']} 测试集仍未发布，检查验证证书是否匹配当前配置")

        now = datetime.now(UTC)
        published_version = api.call(
            "POST", f"/experiment-versions/{draft['id']}/publish", {
                "start_at": stamp(now - timedelta(days=1)),
                "end_at": stamp(now + timedelta(days=14)),
                "initial_test_suite_id": suite_detail["id"]}, 200)["data"]
        published.append(published_version)
        log(f"{spec['code']} 已发布：{spec['title']}，测试集 {len(spec['cases'])} 条用例 / "
            f"{len({c['group_code'] for c in spec['cases']})} 个评分组")

    return published


# ---------------------------------------------------------------- 提交与评测

def teacher_id_of(db, course_id):
    return db.execute("SELECT teacher_id FROM course WHERE id=?", (course_id,)).fetchone()[0]


def seat_of(db, course_id):
    return db.execute(
        "SELECT u.id,u.student_no,u.name FROM course_member m JOIN user u ON u.id=m.user_id "
        "WHERE m.course_id=? AND m.member_role='student' AND m.active=1 "
        "AND u.role='student' AND u.active=1 ORDER BY u.student_no",
        (course_id,)).fetchall()


def scoring_groups(db, suite_id):
    raw = db.execute("SELECT scoring_groups_json FROM test_suite WHERE id=?",
                     (suite_id,)).fetchone()[0]
    return {item["code"]: item["max_hundredths"] for item in json.loads(raw)["groups"]}


def stage_grading(app, api, db, course_id):
    """学生提交 .circ，并把排队中的评测写成完成态。

    沙箱不可用时真实引擎跑不起来，这里按通过比例写入 grading_run / case_result；
    suite、profile 的哈希都取自数据库里的真实配置，快照仍然自洽。
    """
    from backend.models.grading import compute_score

    versions = api.call("GET", f"/courses/{course_id}/experiment-versions?page_size=100")["data"]
    published = {item["experiment"]["code"]: item for item in versions
                 if item["status"] == "published"}
    students = seat_of(db, course_id)
    if not students:
        raise SystemExit("课程没有学生，先跑 --stage base")

    done = 0
    for offset, spec in enumerate(EXPERIMENTS):
        version = published.get(spec["code"])
        if version is None:
            log(f"{spec['code']} 还没有已发布版本，跳过评测")
            continue
        already = {row[0] for row in db.execute(
            "SELECT DISTINCT s.student_id FROM submission s WHERE s.experiment_version_id=?",
            (version["id"],))}
        run_rows = db.execute(
            "SELECT COUNT(*) FROM grading_run r JOIN submission s ON s.id=r.submission_id "
            "WHERE s.experiment_version_id=?", (version["id"],)).fetchone()[0]
        if run_rows >= 8:
            debug(f"{spec['code']} 已有 {run_rows} 条评测记录")
            done += run_rows
            continue

        # 每个实验换一批不重叠的学生提交，制造“有人交了有人没交”的真实分布
        before = done
        picks = [s for s in students[offset * 8: offset * 8 + 8] if s["id"] not in already]
        correct = load_reference(spec["reference"])
        wrong = load_reference(spec["negative"]) if spec["negative"] else negative_circuit(correct)
        plan = ["accepted"] * 4 + ["wrong_answer"] * 2 + ["timeout", "invalid_circuit"]
        for index, student in enumerate(picks):
            outcome = plan[(len(already) + index) % len(plan)]
            client = Api(app, remote_addr=f"10.20.15.{10 + offset * 8 + index}")
            try:
                client.login(student["student_no"], student["student_no"])
            except SystemExit:
                debug(f"学生 {student['student_no']} 登录失败，跳过")
                continue
            payload = correct if outcome in ("accepted", "timeout") else wrong
            if outcome == "invalid_circuit":
                payload = correct.replace("<circuit", "<circuit ", 1)
            data = {"file": (BytesIO(payload.encode("utf-8")),
                             f"{spec['code']}-{student['student_no']}.circ")}
            try:
                created = client.call(
                    "POST", f"/experiment-versions/{version['id']}/submissions", data, 202,
                    headers={"Idempotency-Key": str(uuid4())})
            except SystemExit as error:
                debug(f"{student['student_no']} 提交被拒：{error}")
                continue
            run_id = created["data"]["run_id"]
            settle_run(db, run_id, outcome, compute_score, log if VERBOSE else None)
            done += 1
        log(f"{spec['code']} 提交 {done - before} 份，评测记录已生成")
    return done


def settle_run(db, run_id, outcome, compute_score, echo=None):
    """把一条 queued 的评测按结果落定，并补齐每条用例的结果。"""
    run = db.execute("SELECT * FROM grading_run WHERE id=?", (run_id,)).fetchone()
    cases = db.execute("SELECT * FROM test_case WHERE suite_id=? ORDER BY id",
                       (run["suite_id"],)).fetchall()
    groups = scoring_groups(db, run["suite_id"])
    total = len(cases)

    if outcome == "accepted":
        passed_cases = [case["id"] for case in cases]
        executed = total
    elif outcome == "wrong_answer":
        # 隔组通过，分数落在中间档（全通过就是满分，看不出差距）
        by_group = {}
        for case in cases:
            by_group.setdefault(case["group_code"], []).append(case["id"])
        passed_cases = [ids[0] for index, ids in enumerate(by_group.values()) if index % 2 == 0]
        executed = total
    elif outcome == "timeout":
        passed_cases, executed = [], 0
    else:
        passed_cases, executed = [], 0

    if outcome == "wrong_answer":
        score = compute_score(groups, cases, set(passed_cases))
    elif outcome == "accepted":
        score = 10000
    else:
        score = 0

    status = {"accepted": "accepted", "wrong_answer": "wrong_answer",
              "timeout": "timeout", "invalid_circuit": "invalid_circuit"}[outcome]
    error_code = {"accepted": None, "wrong_answer": "WRONG_ANSWER",
                  "timeout": "TIME_LIMIT", "invalid_circuit": "CIRCUIT_LOAD_ERROR"}[outcome]
    started = stamp(datetime.now(UTC) - timedelta(seconds=6))
    finished = stamp(datetime.now(UTC))
    db.execute(
        "UPDATE grading_run SET status=?,score_hundredths=?,passed_count=?,executed_count=?,"
        "total_count=?,started_at=?,finished_at=?,error_code=?,sandbox_id=? WHERE id=?",
        (status, score, len(passed_cases), executed, total, started, finished,
         error_code, "demo-seed", run_id))
    if status == "invalid_circuit":
        db.execute("UPDATE grading_run SET executed_count=0 WHERE id=?", (run_id,))
    for case in cases:
        hit = case["id"] in passed_cases
        db.execute(
            "INSERT OR REPLACE INTO case_result(run_id,case_id,passed,actual_json,elapsed_ms,error_code) "
            "VALUES(?,?,?,?,?,?)",
            (run_id, case["id"], 1 if hit else 0,
             json.dumps({"demo": True, "matched": hit}, ensure_ascii=False),
             120 + (case["id"] % 40) * 7,
             None if hit else ("TIME_LIMIT" if outcome == "timeout" else "MISMATCH")))
    db.commit()
    if echo:
        echo(f"run #{run_id} → {status}，得分 {score / 100:.2f}")


# ---------------------------------------------------------------- 签到与演示

GESTURE = [0, 1, 2, 5, 8]   # Z 字形，和既有演示任务一致


def stage_attendance(app, api, db, course_id):
    """手势签到 + 签到码签到 + 一次已结束的点名。"""
    listing = api.call("GET", f"/courses/{course_id}/attendance-tasks?page_size=100")["data"]
    have = {item["title"]: item for item in listing}
    now = datetime.now(UTC)
    students = seat_of(db, course_id)

    def make_task(title, start, late, end, pattern=None):
        if title in have:
            debug(f"复用签到任务 {title}")
            return have[title]
        payload = {"title": title, "start_at": stamp(start), "late_at": stamp(late),
                   "end_at": stamp(end)}
        if pattern:
            payload["pattern"] = pattern
        return api.call("POST", f"/courses/{course_id}/attendance-tasks", payload, 201)["data"]

    def current_code(task):
        """签到码只在创建时返回一次，复用任务时轮换一把新的。"""
        if task.get("code"):
            return task["code"]
        try:
            return api.call("POST", f"/attendance-tasks/{task['id']}/rotate-code",
                            {})["data"]["code"]
        except SystemExit:
            return None

    live = make_task("第11周课堂点名 · 手势签到", now - timedelta(minutes=15),
                     now + timedelta(minutes=45), now + timedelta(minutes=75), GESTURE)
    code_task = make_task("第11周课堂点名 · 签到码", now - timedelta(minutes=10),
                          now + timedelta(minutes=50), now + timedelta(minutes=80))
    past = make_task("第11周第一次课 · 已结束", now - timedelta(days=2),
                     now - timedelta(days=2) + timedelta(minutes=15),
                     now - timedelta(days=2) + timedelta(minutes=30))

    # 进行中的两个任务：一半人手势、一半人签到码，剩下的留白演示“未签到”
    code = current_code(code_task)
    signed = 0
    half = int(len(students) * 0.44)
    for index, student in enumerate(students[:half]):
        client = Api(app, remote_addr=f"10.20.16.{20 + index}")
        try:
            client.login(student["student_no"], student["student_no"])
        except SystemExit:
            continue
        if index % 2 == 0:
            target, payload = live, {"pattern": GESTURE}
        else:
            if not code:
                continue
            target, payload = code_task, {"code": code}
        try:
            client.call("POST", f"/attendance-tasks/{target['id']}/check-ins", payload, 201)
            signed += 1
        except SystemExit:
            pass
    log(f"签到：手势 + 签到码两个进行中任务，已签 {signed} 人次")

    # 已结束那次课：窗口已过没法再签，按结果直接写记录再关闭
    done = db.execute("SELECT COUNT(*) FROM attendance_record WHERE task_id=?",
                      (past["id"],)).fetchone()[0]
    if not done:
        now_stamp = stamp()
        late_stamp = stamp(now - timedelta(days=2) + timedelta(minutes=12))
        late_line = int(len(students) * 0.79)
        leave_line = int(len(students) * 0.87)
        absent_line = int(len(students) * 0.92)   # 这几个不写记录，关闭时自动记缺勤
        for index, student in enumerate(students):
            if index >= absent_line:
                continue
            status, source, checked = "present", "checkin", now_stamp
            if index >= late_line:
                status, source, checked = "late", "checkin", late_stamp
            if index >= leave_line:
                status, source, checked = "leave", "approval", None
            db.execute(
                "INSERT OR IGNORE INTO attendance_record(task_id,student_id,status,checked_at,"
                "source,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (past["id"], student["id"], status, checked, source, now_stamp, now_stamp))
            if status == "leave":
                db.execute(
                    "INSERT OR IGNORE INTO leave_request(task_id,student_id,reason,status,"
                    "reviewer_id,review_note,reviewed_at,created_at,updated_at) "
                    "VALUES(?,?,?,'approved',?,?,?,?,?)",
                    (past["id"], student["id"], "参加校级电子设计竞赛，与本节课冲突。",
                     teacher_id_of(db, course_id), "已核实，准假。", now_stamp, now_stamp, now_stamp))
        db.commit()
        api.call("POST", f"/attendance-tasks/{past['id']}/close", {})
        stats = db.execute("SELECT status,COUNT(*) c FROM attendance_record WHERE task_id=? "
                           "GROUP BY status", (past["id"],)).fetchall()
        log("已结束点名：" + "、".join(f"{row['status']} {row['c']}" for row in stats))


def stage_demo(api, course_id):
    """课堂演示用的电路会话。"""
    listing = api.call("GET", f"/courses/{course_id}/demo-sessions?page_size=100")["data"]
    have = {item["preset"]: item for item in listing}
    created = 0
    for preset in ("alu", "cpu"):
        if preset in have:
            continue
        session = api.call("POST", f"/courses/{course_id}/demo-sessions",
                           {"preset": preset}, 201)["data"]
        # 推进两步，让演示打开就是“讲了一半”的状态
        revision = session["revision"]
        for _ in range(2):
            advanced = api.call("PUT", f"/demo-sessions/{session['id']}/state",
                                {"revision": revision, "action": "step"})
            revision = advanced["data"]["revision"]
        created += 1
    log(f"电路演示会话：{len(have) + created} 个（alu / cpu）")


# ---------------------------------------------------------------- 备课与练习

def stage_preparation(api, db, course_id, knowledge):
    """备课包：一份已发布、一份草稿。"""
    listing = api.call("GET", f"/courses/{course_id}/preparations?page_size=100")["data"]
    have = {item["title"] for item in listing}
    questions = api.call("GET", f"/courses/{course_id}/questions?page_size=100")["data"]
    versions = [item["version_id"] for item in questions]
    resources = api.call("GET", f"/courses/{course_id}/resources?page_size=100")["data"]
    resource_versions = []
    for item in resources:
        detail = api.call("GET", f"/resources/{item['id']}/versions?page_size=10")["data"]
        if detail:
            resource_versions.append(detail[0]["id"])
    papers = api.call("GET", f"/courses/{course_id}/papers?page_size=100")["data"]
    quizzes = [item["id"] for item in papers if item["kind"] == "quiz"]

    now = datetime.now(UTC)
    plans = [
        ("第11周课前预习 · 补码与时序", knowledge[:4], True,
         now + timedelta(days=1)),
        ("第11周复习课 · ALU 与数据通路", knowledge[4:12], False,
         now + timedelta(days=4)),
    ]
    created = 0
    for title, points, publish, when in plans:
        if title in have:
            continue
        payload = {"title": title, "scheduled_at": stamp(when),
                   "knowledge_ids": [point["id"] for point in points],
                   "resource_version_ids": resource_versions[:3],
                   "question_version_ids": versions[:8],
                   "quiz_ids": quizzes if publish else []}
        prep = api.call("POST", f"/courses/{course_id}/preparations", payload, 201)["data"]
        if publish:
            api.call("POST", f"/preparations/{prep['id']}/publish", {})
        created += 1
    log(f"备课包：{len(have) + created} 份（含 1 份已发布）")


def stage_practice(app, api, db, course_id):
    """学生的练习记录、错题与知识点完成进度。"""
    existing = db.execute(
        "SELECT COUNT(*) FROM practice_attempt pa JOIN question_version v ON v.id=pa.question_version_id "
        "JOIN question q ON q.id=v.question_id WHERE q.course_id=?", (course_id,)).fetchone()[0]
    if existing:
        debug(f"已有 {existing} 条练习记录")
        return
    questions = db.execute(
        "SELECT q.id AS question_id, v.id AS version_id, v.type, v.answer_json, v.options_json "
        "FROM question q JOIN question_version v ON v.question_id=q.id AND v.version=("
        "  SELECT MAX(version) FROM question_version WHERE question_id=q.id) "
        "WHERE q.course_id=? AND q.archived=0 AND v.practice_available=1 ORDER BY q.id",
        (course_id,)).fetchall()
    students = seat_of(db, course_id)[:24]
    knowledge = db.execute(
        "SELECT k.id FROM knowledge_point k JOIN chapter c ON c.id=k.chapter_id "
        "WHERE c.course_id=? AND k.published=1 ORDER BY k.id", (course_id,)).fetchall()

    def right_answer(row):
        answer = json.loads(row["answer_json"])
        return answer

    def wrong_answer(row):
        """给出一个结构合法但确定错误的答案。"""
        answer = json.loads(row["answer_json"])
        keys = [item["key"] for item in json.loads(row["options_json"] or "[]")]
        if row["type"] == "single":
            other = [key for key in keys if key != answer]
            return other[0] if other else answer
        if row["type"] == "multiple":
            other = [key for key in keys if key not in answer]
            return [other[0]] if other else answer
        if row["type"] == "boolean":
            return not answer
        if row["type"] == "numeric":
            return int(answer) + 1
        return "答不上来"

    submitted = 0
    for index, student in enumerate(students):
        client = Api(app, remote_addr=f"10.20.18.{20 + index}")
        try:
            client.login(student["student_no"], student["student_no"])
        except SystemExit:
            continue
        for q_index, row in enumerate(questions[:6]):
            # 每人前几题答对，后面的错一些，形成有梯度的掌握情况
            ok = (index + q_index) % 3 != 0
            answer = right_answer(row) if ok else wrong_answer(row)
            try:
                client.call("POST", f"/questions/{row['question_id']}/practice-attempts", {
                    "question_version_id": row["version_id"], "answer": answer}, 201,
                    headers={"Idempotency-Key": str(uuid4())})
                submitted += 1
            except SystemExit:
                continue
        # 学习进度：每人完成一部分知识点
        for point in knowledge[: (index % 6) + 3]:
            try:
                client.call("PUT", f"/knowledge-points/{point['id']}/progress",
                            {"completed": True})
            except SystemExit:
                pass
    log(f"练习记录：{submitted} 条，学习进度已按学生分布写入")


def stage_resource_views(app, api, db, course_id):
    """学生翻课件、下载资料，留下资源访问统计要用的记录。"""
    existing = db.execute(
        "SELECT COUNT(*) FROM resource_event ev JOIN resource_version rv ON rv.id=ev.resource_version_id "
        "JOIN resource r ON r.id=rv.resource_id WHERE r.course_id=?", (course_id,)).fetchone()[0]
    if existing:
        debug(f"已有 {existing} 条资源访问记录")
        return
    rows = db.execute(
        "SELECT r.kind, rv.id AS version_id FROM resource r "
        "JOIN resource_version rv ON rv.resource_id=r.id "
        "WHERE r.course_id=? AND r.visibility='students' AND r.archived=0 ORDER BY r.id",
        (course_id,)).fetchall()
    students = seat_of(db, course_id)[:18]
    total = 0
    for index, student in enumerate(students):
        client = Api(app, remote_addr=f"10.20.19.{20 + index}")
        try:
            client.login(student["student_no"], student["student_no"])
        except SystemExit:
            continue
        # 每人看 1-3 份，越靠前的资源看得越多
        for row in rows[: (index % 3) + 2]:
            intent = "download" if row["kind"] in ("video", "question_bank") else "view"
            try:
                client.call("GET", f"/resource-versions/{row['version_id']}/content"
                                    f"?intent={intent}&event_id={uuid4()}")
                total += 1
            except SystemExit:
                continue
    log(f"资源访问：{total} 次（浏览 + 下载）")


# ---------------------------------------------------------------- 入口

STAGES = ("base", "knowledge", "questions", "resources", "experiments",
          "grading", "preparation", "practice", "attendance", "demo")


def main(argv=None):
    global VERBOSE
    parser = argparse.ArgumentParser(description="第11周课堂演示数据")
    parser.add_argument("--db", default=str(ROOT / "instance" / "app.db"))
    parser.add_argument("--stage", default="all",
                        help="all 或逗号分隔：" + ",".join(STAGES))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    VERBOSE = args.verbose

    wanted = list(STAGES) if args.stage == "all" else [s.strip() for s in args.stage.split(",")]
    unknown = [s for s in wanted if s not in STAGES]
    if unknown:
        raise SystemExit(f"未知阶段：{unknown}")

    database = Path(args.db).resolve()
    if not database.exists():
        raise SystemExit(f"数据库不存在：{database}")
    # create_app 用相对路径读 instance/app.db 与 instance/uploads，必须切到仓库根
    import os
    os.chdir(ROOT)

    from backend.app import create_app

    app = create_app({"TESTING": True,
                      "DATABASE_PATH": str(database),
                      # 必须用绝对路径：Flask 的 send_file 对相对路径以应用根目录为基准，
                      # 而上传落盘按当前工作目录，两边不一致会导致下载 404。
                      "UPLOAD_ROOT": str(ROOT / "instance" / "uploads")})
    api = Api(app)
    try:
        user = api.login(TEACHER_NO, TEACHER_PASSWORD)
    except SystemExit:
        raise SystemExit("教师账号 teacher/teacher 登录失败，请先跑 scripts/seed_teacher_course.py")
    teacher_id = user["id"]
    log(f"教师登录：{user['name']}（id={teacher_id}）")

    db = open_db(database)
    try:
        course_id, fresh = ensure_course(db, teacher_id)
        db.commit()
        context = {"course_id": course_id}
        if "base" in wanted:
            stage_base(api, db, course_id, teacher_id)
        if {"knowledge", "questions", "resources", "experiments", "grading",
                "preparation"} & set(wanted):
            knowledge = stage_knowledge(api, course_id)
            context["knowledge"] = knowledge
            chapters = api.call("GET", f"/courses/{course_id}/chapters?page_size=100")["data"]
            context["chapters"] = [item["id"] for item in chapters]
        if "questions" in wanted:
            stage_questions(api, course_id, context["knowledge"])
        if "resources" in wanted:
            stage_resources(api, db, course_id, context["chapters"])
        if {"experiments", "grading"} & set(wanted):
            stage_experiments(api, db, course_id, context["knowledge"])
        if "grading" in wanted:
            stage_grading(app, api, db, course_id)
        if "preparation" in wanted:
            stage_preparation(api, db, course_id, context["knowledge"])
        if "practice" in wanted:
            stage_practice(app, api, db, course_id)
            stage_resource_views(app, api, db, course_id)
        if "attendance" in wanted:
            stage_attendance(app, api, db, course_id)
        if "demo" in wanted:
            stage_demo(api, course_id)

        log("")
        log(f"完成。课程 #{course_id}「{TITLE}」")
        try:
            summary = api.call("GET", f"/courses/{course_id}/health-summary")["data"]
        except SystemExit:
            summary = None
        if summary:
            log(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
