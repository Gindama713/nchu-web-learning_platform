"""SPEC-020 问法回归：同一意图换 10 种说法仍要识别，防止「换个词就答不上」。

这些是纯分类测试，不建库：只验证规则层，不验证取数。
"""

from unittest import TestCase

from backend.apis.assistant import classify

MEMBERS = [
    {"id": 1, "student_no": "24201501", "name": "莫涛"},
    {"id": 2, "student_no": "24201502", "name": "董文静"},
    {"id": 3, "student_no": "24201503", "name": "王伟"},
    {"id": 4, "student_no": "24201504", "name": "王伟民"},
]

TEACHER_CASES = {
    "attendance": [
        "这周考勤怎么样", "班里出勤率多少", "有多少人没来上课", "签到情况如何",
        "班级考勤情况", "迟到的人多吗", "请假的有几个", "到勤率是多少",
        "这节课来了多少人", "缺勤多不多", "上课到场情况", "旷课的人有多少",
    ],
    "session_absence": [
        "上次点名谁没到", "谁没签到", "哪些人缺席了", "缺勤名单给我",
        "几个人没来", "谁缺席了", "哪些人没来", "这次点名谁没来",
        "没到的人有哪些", "谁没上课",
    ],
    "weak_knowledge": [
        "哪个知识点最薄弱", "学生哪里不会", "哪章错得多", "掌握度最低的是什么",
        "大家学不会的是什么", "最弱的三个知识点", "学生的短板在哪", "哪块最难",
        "哪些知识点错得最多", "掌握得最差的是什么", "哪里拉分",
    ],
    "at_risk": [
        "谁有风险", "哪些人跟不上", "需要重点关注谁", "谁掉队了",
        "有预警的学生吗", "谁需要帮一把", "表现异常的有谁", "哪些人危险",
    ],
    "advice": [
        "下节课讲什么", "备课建议", "重点讲哪块", "这节课先讲什么",
        "教学安排怎么定", "课堂安排给点建议", "下节课重点讲啥", "怎么教比较好",
    ],
    "class_overview": [
        "这周学情怎么样", "班级整体情况", "最近表现如何", "总结一下班级状态",
        "整体学情概览", "班里情况如何", "学生状态怎么样",
    ],
    "class_scores": [
        "这次考试平均分多少", "班级成绩怎么样", "作业考得如何", "随堂测平均多少",
        "全班考试及格率", "这次卷面成绩如何", "考试分数分布", "班级平均分是多少",
    ],
    "student_attendance": [
        "莫涛到了吗", "24201501 考勤", "董文静来了吗", "莫涛签到情况",
        "24201502 出勤怎么样", "王伟迟到过吗", "莫涛缺勤几次", "董文静上课到场了吗",
    ],
    "student_profile": [
        "莫涛成绩怎么样", "董文静学得怎么样", "莫涛哪里弱", "24201501 表现如何",
        "王伟最近状态怎么样", "莫涛整体情况", "董文静考得怎么样", "莫涛的学情",
    ],
    "knowledge_qa": [
        "程序计数器是什么", "ALU 的作用", "为什么要用补码", "寄存器和存储器有什么区别",
        "PC 的含义", "解释一下取指周期",
    ],
    "clarify": [
        "你好", "今天天气不错", "在吗", "帮我看看", "随便聊聊",
    ],
}

STUDENT_CASES = {
    "my_attendance": [
        "我考勤怎么样", "我来过几次", "我缺课了吗", "我迟到过吗",
        "我签到情况如何", "我的出勤率", "我请过假吗", "我到勤多少",
    ],
    "my_scores": [
        "我成绩怎么样", "我考了多少分", "考试考得如何", "作业得了多少",
        "我的分数", "随堂测多少分", "我及格了吗", "我平均分多少",
    ],
    "my_attempts": [
        "我做了多少题", "我正确率多少", "我错了几道", "刷题情况",
        "我做对几道", "练习错得多吗", "我答错了几题", "我做了几道题",
    ],
    "my_progress": [
        "我哪里薄弱", "我学到哪了", "我进度怎么样", "我还差多少",
        "我哪里弱", "我掌握得怎么样", "我学得怎么样", "我水平如何",
        "我哪里考得不好", "我的短板",
    ],
    "next_practice": [
        "下一步练什么", "推荐我学什么", "该复习啥", "接下来练哪块",
        "我先练什么", "下一步该做什么",
    ],
    "knowledge_qa": [
        "PC 是什么", "为什么要用补码", "ALU 的作用", "寄存器和存储器有什么区别",
        "解释一下取指周期",
    ],
    "clarify": [
        "你好", "在吗", "随便聊聊",
    ],
}


class PhrasingTest(TestCase):
    def assert_cases(self, cases, role):
        failures = []
        for intent, phrases in cases.items():
            for phrase in phrases:
                got, _ = classify(phrase, role, MEMBERS if role == "teacher" else ())
                if got != intent:
                    failures.append(f"{phrase} → {got}（期望 {intent}）")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_teacher_phrasings(self):
        self.assert_cases(TEACHER_CASES, "teacher")

    def test_student_phrasings(self):
        self.assert_cases(STUDENT_CASES, "student")

    def test_pronoun_uses_context_student(self):
        context = MEMBERS[0]
        self.assertEqual(classify("他到了吗", "teacher", MEMBERS, context)[0], "student_attendance")
        self.assertEqual(classify("她考得怎么样", "teacher", MEMBERS, context)[0], "student_profile")
        # 没有指代词时，上下文学生不能劫持班级问题
        self.assertEqual(classify("这周学情怎么样", "teacher", MEMBERS, context)[0], "class_overview")
        for question in ("其他学生出勤怎么样", "他们考勤怎么样", "她们考勤怎么样", "他人成绩如何"):
            intent, target = classify(question, "teacher", MEMBERS, context)
            self.assertIn(intent, {"attendance", "class_scores"})
            self.assertIsNone(target)

    def test_student_never_leaves_own_scope(self):
        # 学生问别人姓名也只落到自己的意图，不会变成教师意图
        intent, target = classify("莫涛考了多少分", "student", MEMBERS)
        self.assertEqual(intent, "my_scores")
        self.assertIsNone(target)

    def test_duplicate_names_prefer_longest(self):
        matched = classify("王伟民到了吗", "teacher", MEMBERS)
        self.assertEqual(matched[0], "student_attendance")
        self.assertEqual(matched[1]["name"], "王伟民")

    def test_ambiguous_names_and_multiple_targets_require_clarification(self):
        duplicate = [*MEMBERS, {"id": 5, "student_no": "24201505", "name": "王伟"}]
        for question, members in (("王伟到了吗", duplicate), ("王伟和王伟民考勤如何", MEMBERS),
                                  ("24201501 和 24201502 考勤", MEMBERS)):
            with self.subTest(question=question):
                self.assertEqual(classify(question, "teacher", members), ("clarify", None))

    def test_named_absence_and_all_pronouns_stay_on_selected_student(self):
        self.assertEqual(classify("莫涛没签到吗", "teacher", MEMBERS),
                         ("student_attendance", MEMBERS[0]))
        for pronoun in ("这名学生", "那名学生", "那位同学"):
            self.assertEqual(classify(f"{pronoun}没签到吗", "teacher", MEMBERS, MEMBERS[0]),
                             ("student_attendance", MEMBERS[0]))

    def test_alphanumeric_student_number_matches_without_name(self):
        member = {"id": 6, "student_no": "STUDENT01", "name": "同学甲"}
        self.assertEqual(classify("STUDENT01 考勤", "teacher", [member]),
                         ("student_attendance", member))
        self.assertEqual(classify("XSTUDENT01 考勤", "teacher", [member]), ("attendance", None))
