"""本组公开信息：GET /who 的唯一事实来源。

改成员、改组号只改这里，/who 与前端展示都从这里取，避免两处不一致。
所有值均为课程任务书要求公开的信息，不含任何凭据。
"""

CLASS_NAME = "242017班"
GROUP_NO = "g24201710"
GROUP_NAME = "计算机组成原理组"
PROJECT = "计算机组成原理课程学习系统（中央处理器）"

LEADER = {"student_no": "24201718", "name": "姜苏豪"}

# 顺序即名单顺序，组长在第一位。
MEMBERS = [
    {"student_no": "24201718", "name": "姜苏豪", "role": "组长"},
    {"student_no": "24201716", "name": "黄俊诚", "role": "组员"},
    {"student_no": "24201723", "name": "罗浩铭", "role": "组员"},
    {"student_no": "24201737", "name": "石佰合", "role": "组员"},
]

# 任务书规定的公开测试账号规则，互测方据此登录。
ACCOUNT_RULES = {
    "teacher": "teacher/teacher（学号输入 teacher，密码 teacher）",
    "student": "学号/学号（密码默认与学号相同）",
}


def payload():
    """/who 的 data 段。"""
    return {
        "class_name": CLASS_NAME,
        "group_no": GROUP_NO,
        "group_name": GROUP_NAME,
        "project": PROJECT,
        "leader": dict(LEADER),
        "members": [dict(member) for member in MEMBERS],
        "member_count": len(MEMBERS),
        "student_nos": [member["student_no"] for member in MEMBERS],
        "accounts": dict(ACCOUNT_RULES),
    }
