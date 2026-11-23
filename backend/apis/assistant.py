"""SPEC-020 教学助手：只用已记录的统计事实回答，不调用外部模型，也不写数据库。

设计边界：
1. 只读。提问不产生 analysis_run、不写访问日志以外的任何业务表，课堂演示零副作用。
2. 不编数字。每一项数字都来自 010A/010B/011/014 已有实现，缺数据时明确说"算不出来"。
3. 规则意图。识别不了的问题退回知识检索，不伪造"我理解了"。
"""

import hashlib
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app

from backend.apis import analytics as analytics_api
from backend.apis import warnings as warnings_api
from backend.models import assistant_charts, knowledge_analysis, score_analysis
from backend.models import qa as qa_model
from backend.shared.api import (
    ApiError,
    body,
    now,
    positive_int,
    result,
    stamp,
    text_field,
)
from backend.shared.auth import course_access, require_user
from backend.shared.db import get_db

bp = Blueprint("assistant", __name__)
VERSION = "assistant-rules-v1"
WINDOW_DAYS = 28
MAX_QUESTION = 200
MAX_LISTED_STUDENTS = 5
MAX_ATTENDANCE_ROWS = 5
MAX_ATTEMPT_ROWS = 5
KIND_TEXT = {"exam": "考试", "homework": "作业", "quiz": "随堂测"}
STATUS_TEXT = {"present": "出勤", "late": "迟到", "leave": "请假", "absent": "缺勤"}

TEACHER_SUGGESTIONS = [
    "这周学情怎么样？",
    "哪个知识点最薄弱？",
    "谁需要重点关注？",
    "下节课该讲什么？",
]
STUDENT_SUGGESTIONS = [
    "程序计数器是什么？",
    "我哪里薄弱？",
    "下一步该练什么？",
    "我这段时间考勤怎么样？",
]
REASON_TEXT = {
    "LOW_OBJECTIVE_RATE": "客观题正确率偏低",
    "RECENT_ATTENDANCE": "最近两次考勤迟到或未到",
    "RELATIVE_WEAK_CLUSTER": "聚类显示处于相对薄弱组",
}


def time_window():
    end = now()
    return stamp(end - timedelta(days=WINDOW_DAYS)), stamp(end)


TEACHER_TOPICS = (
    ("session_absence", ("谁没到", "谁没来", "谁缺勤", "谁缺席", "未到名单", "缺席名单", "缺勤名单",
                         "没来的", "没到的人", "没签到", "缺了谁", "谁没上课", "几个人没来", "点名",
                         "哪些人缺席", "缺席了", "哪些人没来", "哪些人没到")),
    ("attendance", ("考勤情况", "出勤情况", "班级考勤", "来了多少人", "到了多少人", "考勤", "出勤",
                    "签到", "到课", "上课", "来了", "到了", "到场", "缺勤", "缺课", "旷课", "迟到",
                    "请假", "逃课", "没来", "没到", "到勤")),
    ("scores", ("成绩", "分数", "得分", "考了", "考得", "考分", "卷面", "及格", "挂科", "平均分",
                "满分", "考试", "作业", "随堂测")),
    ("weak", ("考得不好", "分数低", "错得多", "掌握得最差", "哪块最难", "难的是", "薄弱", "最弱",
              "弱项", "短板", "难点", "不会", "搞不懂", "没掌握", "掌握度", "错题", "错得",
              "拉分", "学不会", "最难", "最差")),
    ("risk", ("预警", "风险", "掉队", "跟不上", "关注", "异常", "危险", "需要帮")),
    ("advice", ("讲什么", "讲啥", "备课", "下节课", "这节课", "重点讲", "建议", "怎么教",
                "教学安排", "课堂安排", "先讲")),
    ("overview", ("学情", "整体", "情况", "总结", "概览", "怎么样", "如何", "表现", "状态")),
)
STUDENT_TOPICS = (
    ("my_attendance", ("考勤", "出勤", "签到", "到课", "上课", "来了", "来过", "到了", "缺勤", "缺课",
                       "旷课", "迟到", "请假", "请过假", "逃课", "没来", "没到", "到勤")),
    ("my_attempts", ("做题", "练习", "刷题", "错题", "错了几", "错得多", "做对", "做错", "答对",
                     "答错", "做了", "多少题", "几道", "正确率", "错了几道")),
    ("my_scores", ("成绩", "分数", "得分", "考了", "考得", "考分", "卷面", "及格", "挂科",
                   "平均分", "满分", "考试", "作业", "随堂测")),
    ("my_progress", ("考得不好", "学得怎么样", "学到哪", "差多少", "哪里弱", "薄弱", "最弱", "弱项",
                     "短板", "掌握", "进度", "学情", "水平", "表现", "学得")),
    ("next_practice", ("下一步", "接下来", "练什么", "学什么", "推荐", "复习", "该练", "先练")),
)
# 具体维度比「怎么样/情况/如何」这类泛词更可信：泛词只用来兜底，不抢维度。
TOPIC_BOOST = {
    "session_absence": 2, "attendance": 1, "scores": 1, "weak": 1, "risk": 1, "advice": 1, "overview": 0,
    "my_attendance": 1, "my_scores": 1, "my_attempts": 1, "my_progress": 1, "next_practice": 1,
}
PRONOUNS = ("他", "她", "该生", "这个学生", "这位同学", "刚才那位", "这名学生", "此人", "那位同学")
KNOWLEDGE_MARKERS = ("是什么", "什么是", "为什么", "原理", "区别", "作用", "含义", "解释",
                     "定义", "怎么实现", "怎么算", "如何实现", "怎么理解", "举例")
TEACHER_CLARIFY = ("这周学情怎么样？", "哪个知识点最薄弱？", "上次点名谁没到？", "谁需要重点关注？")
STUDENT_CLARIFY = ("我哪里薄弱？", "我的成绩怎么样？", "我做了多少题？", "我这段时间考勤怎么样？")


def best_topic(text, topics):
    """最长命中词 + 维度权重；同分按词表顺序，避免「考勤」压过「谁没到」这类更具体的说法。"""
    best, score = None, 0
    for name, words in topics:
        hits = [len(word) for word in words if word in text]
        if not hits:
            continue
        value = max(hits) + TOPIC_BOOST.get(name, 0)
        if value > score:
            best, score = name, value
    return best


def mentions_student(text):
    return any(pronoun in text for pronoun in PRONOUNS)


def is_knowledge_question(text):
    return any(marker in text for marker in KNOWLEDGE_MARKERS)


def classify(question, role, members=(), context_student=None):
    """打分式意图：取最长命中词，不再「第一个关键词决定一切」。

    换种说法也能命中靠两件事：词表按口语/同义词铺开；同义短语比单词得分高。
    学生视角永远不进入教师意图，问题里出现别人姓名也只查本人。
    """
    text = question.lower()
    matched = match_student(question, members) if role == "teacher" else []
    if role == "teacher":
        target = matched[0] if matched else (context_student if mentions_student(text) else None)
        topic = best_topic(text, TEACHER_TOPICS)
        if topic == "session_absence":
            return "session_absence", None
        if target is not None:
            return ("student_attendance" if topic == "attendance" else "student_profile"), target
        if topic in ("attendance", "scores", "weak", "risk", "advice", "overview"):
            return {"attendance": "attendance", "scores": "class_scores", "weak": "weak_knowledge",
                    "risk": "at_risk", "advice": "advice", "overview": "class_overview"}[topic], None
        return ("knowledge_qa" if is_knowledge_question(text) else "clarify"), None
    topic = best_topic(text, STUDENT_TOPICS)
    if topic:
        return topic, None
    return ("knowledge_qa" if is_knowledge_question(text) else "clarify"), None


def roster(db, course_id):
    return [dict(row) for row in db.execute(
        "SELECT u.id,u.student_no,u.name FROM course_member m JOIN user u ON u.id=m.user_id "
        "WHERE m.course_id=? AND m.member_role='student' AND m.active=1 "
        "AND u.role='student' AND u.active=1 ORDER BY u.student_no", (course_id,))]


def match_student(question, members):
    """先按学号精确匹配，再按姓名包含匹配；重名时只保留最长匹配，避免「王伟」命中「王伟民」。"""
    numbers = set(re.findall(r"\d{6,20}", question))
    by_number = [item for item in members if item["student_no"] in numbers]
    if by_number:
        return by_number
    hits = [item for item in members if item["name"] and item["name"] in question]
    if len(hits) > 1:
        hits = [item for item in hits
                if not any(item is not other and item["name"] in other["name"] for other in hits)]
    return hits


def safe(calculate, caveats, label):
    """单个数据源失败只降级这部分，不让整个回答 503，也绝不返回假数字。"""
    try:
        return calculate()
    except ApiError as error:
        if error.status != 503:
            raise
        caveats.append(f"{label}暂不可用（{error.code}），本次回答不含这部分。")
        return None
    except Exception:
        current_app.logger.exception("assistant source failed: %s", label)
        caveats.append(f"{label}计算失败，本次回答不含这部分。")
        return None


def class_snapshot(db, course_id, start, end, cutoff, caveats):
    """一次取数：文字回答和图表共用同一份事实，不允许各查一遍。"""
    snapshots = {}

    def read_attendance():
        snapshots["attendance"] = analytics_api.facts(db, course_id, start, end, cutoff, None)
        return analytics_api.interval_metrics(snapshots["attendance"], start, end, None)

    knowledge = safe(lambda: knowledge_analysis.metrics(
        knowledge_analysis.extract(db, course_id, start, end, cutoff, None), start, end),
        caveats, "知识点掌握度")
    attendance = safe(read_attendance, caveats, "考勤统计")
    warning = safe(lambda: warnings_api.analyze(
        warnings_api.read_facts(db, course_id, start, end, cutoff)),
        caveats, "学习预警")
    return knowledge, attendance, warning, snapshots


def personal_snapshot(db, course_id, student_id, start, end, cutoff, caveats):
    knowledge = safe(lambda: knowledge_analysis.metrics(
        knowledge_analysis.extract(db, course_id, start, end, cutoff, student_id), start, end),
        caveats, "知识点掌握度")
    attendance = safe(lambda: analytics_api.interval_metrics(
        analytics_api.facts(db, course_id, start, end, cutoff, None), start, end, student_id),
        caveats, "考勤统计")
    return knowledge, attendance


def search_knowledge(db, course_id, question, top_k=3):
    rows = [dict(row) for row in db.execute(
        "SELECT k.id,k.title,k.content,k.example,k.content_revision FROM knowledge_point k "
        "JOIN chapter c ON c.id=k.chapter_id WHERE c.course_id=? AND k.published=1 ORDER BY k.id",
        (course_id,))]
    if not rows:
        return []
    revision = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")).encode()).hexdigest()
    index = qa_model.build_index(revision, rows)
    matches, _ = index.search(question, top_k)
    titles = {row["id"]: row["title"] for row in rows}
    return [{**match, "title": titles.get(match["knowledge_id"], "")} for match in matches]


def student_attendance(db, course_id, student_id, start, end, cutoff):
    rows = [dict(row) for row in db.execute(
        "SELECT t.id,t.title,t.start_at,COALESCE(r.status,'absent') status "
        "FROM attendance_task t JOIN attendance_participant p ON p.task_id=t.id AND p.student_id=? "
        "LEFT JOIN attendance_record r ON r.task_id=t.id AND r.student_id=? "
        "WHERE t.course_id=? AND t.status='closed' AND t.start_at>=? AND t.start_at<? "
        "AND t.updated_at<=? ORDER BY t.start_at DESC,t.id DESC",
        (student_id, student_id, course_id, start, end, cutoff))]
    counts = {status: sum(row["status"] == status for row in rows) for status in STATUS_TEXT}
    return {"rows": rows, **{f"{status}_count": value for status, value in counts.items()},
            "expected_count": len(rows),
            "attendance_rate": round((counts["present"] + counts["late"]) / len(rows), 6) if rows else None}


def latest_task_absences(db, course_id):
    task = db.execute(
        "SELECT id,title,start_at FROM attendance_task WHERE course_id=? AND status='closed' "
        "ORDER BY start_at DESC,id DESC LIMIT 1", (course_id,)).fetchone()
    if not task:
        return None
    rows = [dict(row) for row in db.execute(
        "SELECT u.name,u.student_no,COALESCE(r.status,'absent') status "
        "FROM attendance_participant p JOIN user u ON u.id=p.student_id "
        "LEFT JOIN attendance_record r ON r.task_id=p.task_id AND r.student_id=p.student_id "
        "WHERE p.task_id=? AND COALESCE(r.status,'absent') IN ('absent','leave') ORDER BY u.student_no",
        (task["id"],))]
    expected = db.execute("SELECT COUNT(*) FROM attendance_participant WHERE task_id=?",
                          (task["id"],)).fetchone()[0]
    return {"task": dict(task), "rows": rows, "expected": expected,
            "absent": [row for row in rows if row["status"] == "absent"],
            "leave": [row for row in rows if row["status"] == "leave"]}


def student_scores(db, course_id, student_id, start, end, cutoff, caveats):
    items = []
    for kind in ("exam", "homework", "quiz"):
        snapshot = safe(lambda k=kind: score_analysis.extract(
            db, course_id, start, end, cutoff, student_id, k, None), caveats, f"{KIND_TEXT[kind]}成绩")
        if not snapshot:
            continue
        papers = {paper["id"]: paper for paper in snapshot["papers"]}
        for row in snapshot["assignments"]:
            paper = papers.get(row["paper_id"])
            if not paper:
                continue
            total = paper["total_hundredths"]
            graded = row["status"] == "graded" and row["score_hundredths"] is not None
            items.append({
                "kind": kind, "title": paper["title"], "start_at": paper["start_at"],
                "status": "graded" if graded else ("missing" if row["attempt_id"] is None else "partial"),
                "score": round(row["score_hundredths"] / 100, 2) if graded else None,
                "total": round(total / 100, 2) if total else None,
                "percentage": round(100 * row["score_hundredths"] / total, 1) if graded and total else None,
                "submitted_at": row["submitted_at"],
            })
    return sorted(items, key=lambda item: (item["start_at"], item["title"]), reverse=True)


def student_attempts(db, course_id, student_id, start, end, cutoff):
    """与 010B 共用客观作答样本；简答待批不进入题目数/正确率/错题。"""
    snapshot = knowledge_analysis.extract(db, course_id, start, end, cutoff, student_id)
    practice = {row["id"]: row["stem"] for row in db.execute(
        "SELECT pa.id,qv.stem FROM practice_attempt pa "
        "JOIN question_version qv ON qv.id=pa.question_version_id "
        "JOIN question q ON q.id=qv.question_id "
        "WHERE pa.student_id=? AND q.course_id=? AND qv.type!='short' AND pa.answered=1 "
        "AND pa.created_at>=? AND pa.created_at<? AND pa.created_at<=?",
        (student_id, course_id, start, end, cutoff))}
    answers = {row["id"]: (row["stem"], row["paper"]) for row in db.execute(
        "SELECT ans.id,qv.stem,p.title paper FROM answer ans "
        "JOIN attempt a ON a.id=ans.attempt_id JOIN paper p ON p.id=a.paper_id "
        "JOIN question_version qv ON qv.id=ans.question_version_id "
        "WHERE a.student_id=? AND p.course_id=? AND qv.type!='short' AND ans.answered=1 "
        "AND a.submitted_at>=? AND a.submitted_at<? AND a.submitted_at<=?",
        (student_id, course_id, start, end, cutoff))}
    titles = {point["id"]: point["title"] for point in snapshot["knowledge"]}
    events = []
    for sample in snapshot["samples"]:
        if sample["source"] == "practice":
            source, stem = "练习", practice.get(sample["sample_id"], "")
        else:
            stem, paper = answers.get(sample["sample_id"], ("", ""))
            source = paper or "试卷"
        knowledge = "、".join(titles[knowledge_id] for knowledge_id in sample["knowledge_ids"]
                              if knowledge_id in titles)
        events.append({"at": sample["event_at"], "correct": bool(sample["correct"]),
                       "from": source, "stem": stem, "knowledge": knowledge})
    events.sort(key=lambda item: item["at"], reverse=True)
    wrong = [item for item in events if not item["correct"]]
    weak = {}
    for item in wrong:
        for title in (item["knowledge"] or "").split("、"):
            if title:
                weak[title] = weak.get(title, 0) + 1
    return {"events": events, "answered": len(events), "correct": len(events) - len(wrong),
            "rate": round((len(events) - len(wrong)) / len(events), 6) if events else None,
            "weak": sorted(weak.items(), key=lambda item: (-item[1], item[0]))[:3]}


def student_facts(profile):
    return [
        {"label": "到勤率", "value": pct(profile["attendance_rate"]), "unit": "%",
         "note": f"应到 {profile['expected_count']} 人次", "source": "010A"},
        {"label": "出勤 / 迟到 / 请假 / 缺勤",
         "value": f"{profile['present_count']}/{profile['late_count']}/{profile['leave_count']}/"
                  f"{profile['absent_count']}", "unit": "人次", "source": "010A"},
    ]


def pct(value):
    return None if value is None else round(value * 100, 1)


def short_time(value):
    try:
        return datetime.fromisoformat(str(value)).astimezone(
            ZoneInfo("Asia/Shanghai")).strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        return str(value)[:16]


def weak_points(knowledge, limit=3):
    if not knowledge:
        return []
    items = [item for item in knowledge["items"] if item["answered_count"] > 0]
    return sorted(items, key=lambda item: (item["mastery"], -item["answered_count"], item["title"]))[:limit]


def point_fact(item):
    return {"label": item["title"], "value": pct(item["mastery"]), "unit": "% 掌握度",
            "note": f"答对 {item['correct_count']}/{item['answered_count']} 次", "source": "010B"}


def attendance_facts(metrics):
    return [
        {"label": "到勤率（出勤+迟到）", "value": pct(metrics["attendance_rate"]), "unit": "%", "source": "010A"},
        {"label": "出勤 / 迟到 / 请假 / 缺勤",
         "value": f"{metrics['present_count']}/{metrics['late_count']}/{metrics['leave_count']}/{metrics['absent_count']}",
         "unit": "人次", "note": f"应到 {metrics['expected_count']} 人次", "source": "010A"},
    ]


def attendance_sentence(metrics):
    if metrics["expected_count"] == 0:
        return f"最近 {WINDOW_DAYS} 天没有已结束的考勤任务，到勤率算不出来。"
    return (f"最近 {WINDOW_DAYS} 天应到 {metrics['expected_count']} 人次，"
            f"到勤率 {pct(metrics['attendance_rate'])}%（出勤 {metrics['present_count']}、"
            f"迟到 {metrics['late_count']}、请假 {metrics['leave_count']}、缺勤 {metrics['absent_count']}）。")


def attendance_donut(metrics, title="到勤构成", unit="人次"):
    return assistant_charts.donut(title, [
        {"label": "出勤", "value": metrics["present_count"], "colorKey": "present"},
        {"label": "迟到", "value": metrics["late_count"], "colorKey": "late"},
        {"label": "请假", "value": metrics["leave_count"], "colorKey": "leave"},
        {"label": "缺勤", "value": metrics["absent_count"], "colorKey": "absent"},
    ], unit=unit)


def mastery_level(value):
    """60% 以下算薄弱（与「最薄弱」同一阈值），60—80 中间，80 以上正常。"""
    if value is None:
        return "low"
    if value < 0.6:
        return "danger"
    if value < 0.8:
        return "warn"
    return "ok"


def mastery_bar(points, title="知识点掌握度"):
    return assistant_charts.bars(title, [
        {"label": item["title"], "value": pct(item["mastery"]),
         "colorKey": mastery_level(item["mastery"]),
         "note": f"答对 {item['correct_count']}/{item['answered_count']} 次"}
        for item in points])


def percent_bar(title, rows):
    """rows: [(标签, 百分比)]。颜色统一用主题色，不暗示及格与否。"""
    return assistant_charts.bars(title, [
        {"label": label, "value": value, "colorKey": "accent"} for label, value in rows])


def count_bar(title, rows, unit="人"):
    """rows: [(标签, 计数)]。计数最大值就是轴顶，避免小样本被压成一条线。"""
    top = max([count for _, count in rows], default=0)
    return assistant_charts.bars(title, [
        {"label": label, "value": count, "colorKey": "accent"} for label, count in rows],
        unit=unit, max_value=max(1, top))


def attendance_week_line(snapshot, start, end):
    """按周到勤率折线。快照必须与 facts 同一份，不许为画图重读。"""
    if not snapshot:
        return None
    series = analytics_api.week_series(snapshot, start, end, None)
    # period_start 是 UTC 的周一零点，本地化后取「月-日」，避免日期错一天
    points = [{"label": short_time(row["period_start"])[:5], "value": row["metrics"]["attendance_rate"]}
              for row in series if row["metrics"]["expected_count"]]
    return assistant_charts.line(f"按周到勤率（最近 {WINDOW_DAYS} 天）", points)


def reason_counts(warning):
    counts = {}
    for item in warning["warnings"]:
        for reason in item["reasons"]:
            counts[reason["code"]] = counts.get(reason["code"], 0) + 1
    return counts


def warning_facts(warning):
    if not warning:
        return []
    counts = reason_counts(warning)
    facts = [{"label": "规则命中人数", "value": len(warning["warnings"]), "unit": "人", "source": "014"},
             {"label": "聚类状态", "value": "已聚类" if warning["model_status"] == "clustered" else "样本不足，已降级",
              "note": f"纳入聚类 {warning['sample_size']} 人", "source": "014"}]
    for code, number in sorted(counts.items()):
        facts.append({"label": REASON_TEXT.get(code, code), "value": number, "unit": "人", "source": "014"})
    return facts


def teacher_student_answer(intent, student, db, course_id, start, end, cutoff):
    """教师查具体学生：先给考勤，再按需补成绩、掌握度和预警原因。"""
    caveats = []
    label = student["name"] + "（" + student["student_no"] + "）"
    profile = safe(lambda: student_attendance(db, course_id, student["id"], start, end, cutoff),
                   caveats, "这位学生的考勤")
    facts, actions, charts = [], [], []
    if not profile:
        return {"intent": intent, "title": "这位学生的考勤暂时算不出来",
                "answer": "考勤事实表不齐全，先确认统计页是否正常。", "facts": [], "caveats": caveats,
                "matches": [], "actions": [{"kind": "navigate", "label": "打开考勤与学情",
                                            "payload": {"tab": "stats"}}],
                "suggestions": TEACHER_SUGGESTIONS}
    facts = student_facts(profile)
    for index, row in enumerate(profile["rows"][:MAX_ATTENDANCE_ROWS]):
        facts.append({"label": short_time(row["start_at"]) + " " + row["title"],
                      "value": STATUS_TEXT.get(row["status"], row["status"]),
                      "note": "最近一次" if index == 0 else "", "source": "010A"})
    if intent == "student_attendance":
        if profile["expected_count"]:
            title = label + " 到勤率 " + str(pct(profile["attendance_rate"])) + "%"
            answer = (label + f" 最近 {WINDOW_DAYS} 天应到 {profile['expected_count']} 次，到勤率 "
                      f"{pct(profile['attendance_rate'])}%（出勤 {profile['present_count']}、"
                      f"迟到 {profile['late_count']}、请假 {profile['leave_count']}、"
                      f"缺勤 {profile['absent_count']}）。")
            if profile["rows"]:
                answer += ("最近一次是「" + profile["rows"][0]["title"] + "」，状态 "
                           + STATUS_TEXT.get(profile["rows"][0]["status"], profile["rows"][0]["status"]) + "。")
        else:
            title = label + " 暂无到课记录"
            answer = label + f" 最近 {WINDOW_DAYS} 天没有被结算的考勤任务，到课数据算不出来。"
        charts = assistant_charts.limit([attendance_donut(profile)])
    else:
        scores = safe(lambda: student_scores(db, course_id, student["id"], start, end, cutoff, caveats),
                      caveats, "这位学生的成绩")
        knowledge = safe(lambda: knowledge_analysis.metrics(
            knowledge_analysis.extract(db, course_id, start, end, cutoff, student["id"]), start, end),
            caveats, "这位学生的掌握度")
        warning = safe(lambda: warnings_api.analyze(warnings_api.read_facts(db, course_id, start, end, cutoff)),
                       caveats, "预警")
        graded = [item for item in (scores or []) if item["status"] == "graded"]
        if graded:
            average = round(sum(item["percentage"] for item in graded) / len(graded), 1)
            facts.append({"label": "已评分成绩平均", "value": average, "unit": "%",
                          "note": f"{len(graded)} 次已评分", "source": "010B"})
            for item in graded[:3]:
                facts.append({"label": KIND_TEXT.get(item["kind"], item["kind"]) + " · " + item["title"],
                              "value": item["percentage"], "unit": "%",
                              "note": short_time(item["submitted_at"]), "source": "010B"})
        if knowledge and knowledge["answered_count"]:
            facts.append({"label": "客观题掌握度", "value": pct(knowledge["mastery"]), "unit": "%",
                          "note": f"{knowledge['answered_count']} 次作答", "source": "010B"})
        hit = None
        if warning:
            hit = next((item for item in warning["warnings"] if item["student_id"] == student["id"]), None)
        if hit:
            facts.append({"label": "预警原因", "value": "、".join(
                REASON_TEXT.get(reason["code"], reason["code"]) for reason in hit["reasons"]), "source": "014"})
        pieces = []
        if profile["expected_count"]:
            pieces.append(f"到勤率 {pct(profile['attendance_rate'])}%"
                          f"（缺勤 {profile['absent_count']} 次）")
        if graded:
            pieces.append(f"{len(graded)} 次已评分成绩平均 {average}%")
        if knowledge and knowledge["answered_count"]:
            pieces.append(f"客观题掌握度 {pct(knowledge['mastery'])}%")
        if hit:
            pieces.append("命中预警：" + "、".join(REASON_TEXT.get(reason["code"], reason["code"])
                                                 for reason in hit["reasons"]))
        title = label + " 的情况"
        answer = ("；".join(pieces) + "。") if pieces else (label + " 目前没有可用于分析的记录。")
        charts = assistant_charts.limit([
            attendance_donut(profile),
            percent_bar("这位学生的已评分成绩",
                        [(item["title"], item["percentage"]) for item in graded[:5]]),
        ])
    actions.append({"kind": "navigate", "label": "打开考勤与学情", "payload": {"tab": "stats"}})
    return {"intent": intent, "title": title, "answer": answer, "facts": facts, "caveats": caveats,
            "matches": [], "actions": actions, "charts": charts, "suggestions": TEACHER_SUGGESTIONS}


def teacher_absence_answer(db, course_id):
    data = safe(lambda: latest_task_absences(db, course_id), [], "考勤")
    if not data:
        return {"intent": "session_absence", "title": "还没有已结算的点名",
                "answer": "这门课还没有关闭的考勤任务，没法列出未到名单。先发布并结束一次点名。",
                "facts": [], "caveats": [], "matches": [],
                "actions": [{"kind": "navigate", "label": "打开考勤与学情", "payload": {"tab": "stats"}}],
                "suggestions": TEACHER_SUGGESTIONS}
    task = data["task"]
    absent = data["absent"]
    leave = data["leave"]
    names = [row["name"] + "（" + row["student_no"] + "）" for row in absent]
    facts = [
        {"label": "点名任务", "value": task["title"], "note": short_time(task["start_at"]), "source": "010A"},
        {"label": "应到 / 缺勤 / 请假", "value": f"{data['expected']}/{len(absent)}/{len(leave)}",
         "unit": "人", "source": "010A"},
    ]
    if names:
        facts.append({"label": "缺勤名单", "value": "、".join(names[:10]), "wide": True,
                      "note": f"共 {len(names)} 人" + ("，仅列前 10 人" if len(names) > 10 else ""),
                      "source": "010A"})
    title = f"最近一次点名：{len(absent)} 人缺勤"
    answer = (f"「{task['title']}」（{short_time(task['start_at'])}）应到 {data['expected']} 人，"
              f"缺勤 {len(absent)} 人、请假 {len(leave)} 人。")
    if names:
        answer += "缺勤：" + "、".join(names[:10]) + ("。" if len(names) <= 10 else " 等。")
    else:
        answer += "这次没有缺勤学生。"
    present = max(0, data["expected"] - len(absent) - len(leave))
    charts = assistant_charts.limit([assistant_charts.donut("这次点名的到课构成", [
        {"label": "出勤", "value": present, "colorKey": "present"},
        {"label": "请假", "value": len(leave), "colorKey": "leave"},
        {"label": "缺勤", "value": len(absent), "colorKey": "absent"},
    ], unit="人")])
    return {"intent": "session_absence", "title": title, "answer": answer, "facts": facts,
            "caveats": [], "matches": [], "charts": charts,
            "actions": [{"kind": "navigate", "label": "打开考勤与学情", "payload": {"tab": "stats"}},
                        {"kind": "warning_run", "label": "按最新数据生成预警批次", "payload": {}}],
            "suggestions": TEACHER_SUGGESTIONS}


def class_scores_answer(db, course_id, start, end, cutoff):
    """教师问班级成绩：按考试/作业/随堂测分开给平均百分比与批改进度。"""
    caveats, facts, rows = [], [], []
    for kind in ("exam", "homework", "quiz"):
        snapshot = safe(lambda k=kind: score_analysis.extract(
            db, course_id, start, end, cutoff, None, k, None), caveats, KIND_TEXT[kind] + "成绩")
        if not snapshot:
            continue
        metric = score_analysis.metrics(snapshot, start, end)
        if metric["expected_count"]:
            rows.append((kind, metric))
    if not rows:
        return {"intent": "class_scores", "title": "最近没有作业或考试",
                "answer": f"最近 {WINDOW_DAYS} 天没有已发布并分配名单的作业、随堂测或考试，班级成绩算不出来。",
                "facts": [], "caveats": caveats, "matches": [],
                "actions": [{"kind": "navigate", "label": "打开测评与练习", "payload": {"tab": "exam"}}],
                "suggestions": TEACHER_SUGGESTIONS}
    graded_rows = []
    for kind, metric in rows:
        if metric["graded_count"]:
            graded_rows.append((kind, metric))
            facts.append({"label": KIND_TEXT[kind], "value": metric["mean_percentage"], "unit": "%",
                          "note": f"已批 {metric['graded_count']}/{metric['expected_count']} 人卷次",
                          "source": "010B"})
        else:
            facts.append({"label": KIND_TEXT[kind], "value": None, "unit": "%",
                          "note": f"尚未批改，应交 {metric['expected_count']} 人卷次", "source": "010B"})
    expected = sum(metric["expected_count"] for _, metric in rows)
    graded = sum(metric["graded_count"] for _, metric in rows)
    missing = sum(metric["missing_count"] for _, metric in rows)
    if graded_rows:
        parts = [f"{KIND_TEXT[kind]}平均 {metric['mean_percentage']}%" for kind, metric in graded_rows]
        title = "班级成绩：" + "、".join(parts)
        answer = (f"最近 {WINDOW_DAYS} 天共 {expected} 人卷次应交，已批 {graded}、缺交 {missing}。"
                  + "；".join(parts) + "。只统计已评分答卷，待批和缺交不进均分。")
    else:
        title = "还没有已评分答卷"
        answer = (f"最近 {WINDOW_DAYS} 天共 {expected} 人卷次应交，但已批 0、缺交 {missing}。"
                  "没有已评分答卷，平均分算不出来；批改后再问就有数了。")
    charts = assistant_charts.limit([percent_bar(
        "各类平均分（只含已评分答卷）",
        [(KIND_TEXT[kind], metric["mean_percentage"]) for kind, metric in graded_rows])])
    return {"intent": "class_scores", "title": title, "answer": answer, "facts": facts,
            "caveats": caveats, "matches": [], "charts": charts,
            "actions": [{"kind": "navigate", "label": "打开分类成绩统计", "payload": {"tab": "stats"}}],
            "suggestions": TEACHER_SUGGESTIONS}


def clarify_answer(role):
    options = TEACHER_CLARIFY if role == "teacher" else STUDENT_CLARIFY
    return {"intent": "clarify", "title": "你想问哪一类？",
            "answer": ("我没确定你问的是哪类数据。可以直接点下面的问题，"
                       "或者换一种说法：带上学生姓名，或提到「考勤 / 成绩 / 薄弱 / 预警」。"),
            "facts": [], "caveats": [], "matches": [],
            "actions": [{"kind": "ask", "label": item, "payload": {"question": item}} for item in options],
            "suggestions": TEACHER_SUGGESTIONS if role == "teacher" else STUDENT_SUGGESTIONS}


def teacher_answer(intent, question, db, course_id, start, end, cutoff):
    caveats = []
    knowledge, attendance, warning, snapshots = class_snapshot(db, course_id, start, end, cutoff, caveats)
    facts, actions, charts = [], [], []
    if intent == "weak_knowledge":
        points = weak_points(knowledge)
        if not knowledge:
            title, answer = "知识点掌握度暂时算不出来", "这一维度的数据源不可用，先看统计页是否正常。"
        elif not points:
            title = "最近没有客观作答样本"
            answer = (f"最近 {WINDOW_DAYS} 天全班没有形成有效的客观题作答记录，"
                      "掌握度不能凭空排序。可以让学生先完成一次随堂练习或作业，再回来问。")
            actions.append({"kind": "navigate", "label": "打开学情统计", "payload": {"tab": "stats"}})
        else:
            facts = [point_fact(item) for item in points]
            head = points[0]
            answer = (f"最近 {WINDOW_DAYS} 天全班共 {knowledge['answered_count']} 次客观作答。"
                      f"最薄弱的是「{head['title']}」，掌握度 {pct(head['mastery'])}%"
                      f"（答对 {head['correct_count']}/{head['answered_count']} 次）。")
            if len(points) > 1:
                answer += "其次是" + "、".join(
                    f"「{item['title']}」（{pct(item['mastery'])}%）" for item in points[1:]) + "。"
            title = f"最薄弱：{head['title']}"
            charts = assistant_charts.limit([mastery_bar(points)])
            actions.append({"kind": "navigate", "label": "打开知识掌握度统计", "payload": {"tab": "stats"}})
            actions.append({"kind": "navigate", "label": "去教学内容看这一章", "payload": {"tab": "content"}})
    elif intent == "at_risk":
        if not warning:
            title, answer = "预警数据暂不可用", "预警依赖的作答、实验或考勤事实表不齐全，先确认统计页是否正常。"
        else:
            facts = warning_facts(warning)
            charts = assistant_charts.limit([count_bar(
                "预警命中原因（一人可多条）",
                [(REASON_TEXT.get(code, code), number)
                 for code, number in sorted(reason_counts(warning).items())])])
            people = []
            if warning["warnings"]:
                names = {row["id"]: row["name"] for row in db.execute(
                    "SELECT u.id,u.name FROM course_member m JOIN user u ON u.id=m.user_id "
                    "WHERE m.course_id=? AND m.member_role='student' AND m.active=1 "
                    "AND u.role='student' AND u.active=1", (course_id,))}
                for item in warning["warnings"][:MAX_LISTED_STUDENTS]:
                    reasons = "、".join(REASON_TEXT.get(reason["code"], reason["code"])
                                       for reason in item["reasons"])
                    name = names.get(item["student_id"], "学生 " + str(item["student_id"]))
                    people.append(name + "（" + reasons + "）")
            if warning["warnings"]:
                title = f"{len(warning['warnings'])} 人命中预警规则"
                answer = (f"最近 {WINDOW_DAYS} 天有 {len(warning['warnings'])} 人命中规则：" +
                          "；".join(people) + "。")
                if len(warning["warnings"]) > MAX_LISTED_STUDENTS:
                    answer += f"另有 {len(warning['warnings']) - MAX_LISTED_STUDENTS} 人未逐一列出。"
                if warning["model_status"] != "clustered":
                    answer += (f"聚类样本为 {warning['sample_size']} 人，未达到 10 人门槛，"
                               "本次只有规则提示，没有聚类分组。")
                actions.append({"kind": "warning_run", "label": "生成并保存预警批次", "payload": {}})
            else:
                title = "没有命中预警的学生"
                answer = (f"最近 {WINDOW_DAYS} 天按现有口径没有学生命中预警规则。"
                          "这不等于全班都学得好，样本少时结论要谨慎。")
                if warning["model_status"] != "clustered":
                    answer += f"聚类样本 {warning['sample_size']} 人，未达到门槛，已降级为规则提示。"
        if not warning:
            actions.append({"kind": "navigate", "label": "打开考勤与学情", "payload": {"tab": "stats"}})
    elif intent == "attendance":
        if not attendance:
            title, answer = "考勤数据暂不可用", "考勤事实表不齐全，先确认统计页是否正常。"
        else:
            facts = attendance_facts(attendance)
            charts = assistant_charts.limit([attendance_donut(attendance)])
            title = ("到勤率 " + f"{pct(attendance['attendance_rate'])}%") if attendance["expected_count"] else "暂无考勤任务"
            answer = attendance_sentence(attendance)
            actions.append({"kind": "navigate", "label": "打开考勤与学情", "payload": {"tab": "stats"}})
    elif intent == "advice":
        points = weak_points(knowledge, 2)
        if not points and not warning:
            title, answer = "暂时给不出课堂建议", "缺少作答与预警数据，先让学生完成一次练习。"
        else:
            facts = [point_fact(item) for item in points] + warning_facts(warning)[:1]
            charts = assistant_charts.limit([mastery_bar(points)])
            pieces = []
            if points:
                pieces.append("先用 5—10 分钟回顾「" + points[0]["title"] + "」（掌握度 " +
                              f"{pct(points[0]['mastery'])}%）")
            if len(points) > 1:
                pieces.append("再花几分钟过「" + points[1]["title"] + "」")
            if warning and warning["warnings"]:
                pieces.append(f"课后关注 {len(warning['warnings'])} 名命中预警的学生")
            title = "下节课的优先级建议"
            answer = "；".join(pieces) + "。建议来自最近 " + str(WINDOW_DAYS) + " 天的真实作答与考勤，不是教学大纲的固定顺序。"
            actions.append({"kind": "navigate", "label": "打开教学内容", "payload": {"tab": "content"}})
            actions.append({"kind": "navigate", "label": "打开知识掌握度统计", "payload": {"tab": "stats"}})
    else:  # class_overview
        parts = []
        if attendance:
            parts.append(attendance_sentence(attendance))
        if knowledge:
            if knowledge["answered_count"]:
                parts.append(f"客观题共 {knowledge['answered_count']} 次作答，整体掌握度 "
                             f"{pct(knowledge['mastery'])}%。")
            else:
                parts.append("最近没有客观作答样本，整体掌握度算不出来。")
        if warning:
            parts.append(f"预警规则命中 {len(warning['warnings'])} 人"
                         + ("，聚类已生效。" if warning["model_status"] == "clustered" else "，聚类样本不足已降级。"))
        facts = []
        if attendance:
            facts += attendance_facts(attendance)[:1]
        if knowledge and knowledge["answered_count"]:
            facts.append({"label": "整体掌握度", "value": pct(knowledge["mastery"]), "unit": "%",
                          "note": f"{knowledge['answered_count']} 次作答", "source": "010B"})
        if warning:
            facts.append({"label": "预警命中", "value": len(warning["warnings"]), "unit": "人", "source": "014"})
        title = "最近 " + str(WINDOW_DAYS) + " 天学情概览"
        answer = "".join(parts) or "目前没有可用的学情数据。"
        charts = assistant_charts.limit([
            attendance_donut(attendance) if attendance else None,
            attendance_week_line(snapshots.get("attendance"), start, end),
        ])
        actions.append({"kind": "navigate", "label": "打开考勤与学情", "payload": {"tab": "stats"}})
    return {
        "intent": intent, "title": title, "answer": answer, "facts": facts, "caveats": caveats,
        "matches": [], "actions": actions, "charts": charts, "suggestions": TEACHER_SUGGESTIONS,
    }


def student_answer(intent, question, db, course_id, user_id, start, end, cutoff):
    caveats = []
    knowledge, attendance = personal_snapshot(db, course_id, user_id, start, end, cutoff, caveats)
    facts, actions, charts = [], [], []
    if intent == "my_attendance":
        if not attendance:
            title, answer = "你的考勤数据暂时算不出来", "考勤事实表不齐全，先看考勤页是否正常。"
        else:
            facts = attendance_facts(attendance)
            charts = assistant_charts.limit([attendance_donut(attendance, "你的到课构成")])
            title = ("你的到勤率 " + f"{pct(attendance['attendance_rate'])}%") if attendance["expected_count"] else "暂无考勤记录"
            answer = attendance_sentence(attendance).replace("最近", "你最近", 1)
            actions.append({"kind": "navigate", "label": "打开考勤与学情", "payload": {"tab": "stats"}})
    elif intent == "my_scores":
        scores = student_scores(db, course_id, user_id, start, end, cutoff, caveats)
        graded = [item for item in scores if item["status"] == "graded"]
        pending = [item for item in scores if item["status"] == "partial"]
        missing = [item for item in scores if item["status"] == "missing"]
        if not scores:
            title = "最近没有作业或考试"
            answer = f"最近 {WINDOW_DAYS} 天没有布置给你的作业、随堂测或考试，暂时没有成绩可看。"
        else:
            for item in graded[:5]:
                facts.append({"label": KIND_TEXT.get(item["kind"], item["kind"]) + " · " + item["title"],
                              "value": item["percentage"], "unit": "%",
                              "note": short_time(item["submitted_at"]), "source": "010B"})
            if pending:
                facts.append({"label": "待批", "value": len(pending), "unit": "份", "source": "010B"})
            if missing:
                facts.append({"label": "缺交", "value": len(missing), "unit": "份", "source": "010B"})
            if graded:
                average = round(sum(item["percentage"] for item in graded) / len(graded), 1)
                title = f"已评分 {len(graded)} 次，平均 {average}%"
                best = max(graded, key=lambda item: item["percentage"])
                worst = min(graded, key=lambda item: item["percentage"])
                answer = (f"最近 {WINDOW_DAYS} 天你有 {len(graded)} 次已评分成绩，平均 {average}%。"
                          f"最高是「{best['title']}」{best['percentage']}%，"
                          f"最低是「{worst['title']}」{worst['percentage']}%。")
            else:
                title = "成绩还没有批完"
                answer = (f"你有 {len(pending)} 份待批、{len(missing)} 份缺交，"
                          "暂时没有已评分成绩。批完后这里会按作业/随堂测/考试分开列。")
            charts = assistant_charts.limit([percent_bar(
                "你的已评分成绩", [(item["title"], item["percentage"]) for item in graded[:5]])])
        actions.append({"kind": "navigate", "label": "打开测评与练习", "payload": {"tab": "exam"}})
    elif intent == "my_attempts":
        data = student_attempts(db, course_id, user_id, start, end, cutoff)
        if not data["answered"]:
            title = "最近没有做题记录"
            answer = (f"最近 {WINDOW_DAYS} 天你还没有做题记录。做几道练习后，"
                      "我可以按知识点告诉你错了哪些、错得最多的是哪一块。")
            actions.append({"kind": "practice", "label": "去做练习", "payload": {}})
        else:
            facts = [
                {"label": "做题总数", "value": data["answered"], "unit": "题", "source": "010B"},
                {"label": "正确 / 错误", "value": f"{data['correct']}/{data['answered'] - data['correct']}",
                 "unit": "题", "source": "010B"},
                {"label": "正确率", "value": pct(data["rate"]), "unit": "%", "source": "010B"},
            ]
            for item in data["events"][:MAX_ATTEMPT_ROWS]:
                facts.append({"label": (item["knowledge"] or item["from"])[:18],
                              "value": "对" if item["correct"] else "错",
                              "note": (item["stem"] or "")[:24].replace("\n", " ") + " · " + short_time(item["at"]),
                              "source": "010B"})
            if data["weak"]:
                facts.append({"label": "错得最多的知识点", "wide": True,
                              "value": "、".join(f"{title}（{count} 次）" for title, count in data["weak"]),
                              "source": "010B"})
            title = f"做了 {data['answered']} 题，正确率 {pct(data['rate'])}%"
            answer = (f"最近 {WINDOW_DAYS} 天你做了 {data['answered']} 题，答对 {data['correct']} 题，"
                      f"正确率 {pct(data['rate'])}%。")
            if data["weak"]:
                answer += "错得最多的是「" + data["weak"][0][0] + "」（" + str(data["weak"][0][1]) + " 次），建议优先补这一块。"
            charts = assistant_charts.limit([
                assistant_charts.donut("你的作答对错", [
                    {"label": "答对", "value": data["correct"], "colorKey": "present"},
                    {"label": "答错", "value": data["answered"] - data["correct"], "colorKey": "absent"},
                ], unit="题"),
                count_bar("错题分布（按知识点）", [(title, count) for title, count in data["weak"]], unit="次"),
            ])
            actions.append({"kind": "practice", "label": "去练错得最多的知识点", "payload": {}})
    elif intent in ("my_progress", "next_practice"):
        points = weak_points(knowledge)
        if knowledge and knowledge["answered_count"]:
            facts.append({"label": "你的客观题掌握度", "value": pct(knowledge["mastery"]), "unit": "%",
                          "note": f"{knowledge['answered_count']} 次作答", "source": "010B"})
            if knowledge["progress"] is not None:
                facts.append({"label": "你的知识点完成进度", "value": pct(knowledge["progress"]), "unit": "%",
                              "note": f"{knowledge['completed_knowledge_count']}/"
                                      f"{knowledge['published_knowledge_count']} 个已发布知识点", "source": "010B"})
        if attendance and attendance["expected_count"]:
            facts.append({"label": "你的到勤率", "value": pct(attendance["attendance_rate"]), "unit": "%",
                          "note": f"应到 {attendance['expected_count']} 人次", "source": "010A"})
        if points:
            facts += [point_fact(item) for item in points]
        charts = assistant_charts.limit([mastery_bar(points, "你的知识点掌握度")])
        if not knowledge or not knowledge["answered_count"]:
            title = "还没有足够的作答样本"
            answer = (f"你最近 {WINDOW_DAYS} 天没有客观题作答记录，掌握度算不出来。"
                      "先去做一轮练习，回来我就能按真实正确率告诉你哪里薄弱。")
            actions.append({"kind": "practice", "label": "去做练习", "payload": {}})
        else:
            low = [item for item in points if item["mastery"] < 0.6]
            if intent == "next_practice":
                title = "下一步练什么"
                if low:
                    answer = ("建议先练「" + low[0]["title"] + "」（掌握度 " + f"{pct(low[0]['mastery'])}%）"
                              + ("，再练「" + low[1]["title"] + "」" if len(low) > 1 else "")
                              + "。这些都是你真实做错过的知识点，练完再看错题本。")
                elif points:
                    answer = ("你已经作答的知识点掌握度都在 60% 以上（最低 "
                              + f"「{points[0]['title']}」{pct(points[0]['mastery'])}%），"
                              "可以挑还没做过的知识点继续推进。")
                else:
                    answer = "你已经作答的知识点掌握度都不错，可以挑没做过的知识点继续推进。"
                actions.append({"kind": "practice", "label": "去练习", "payload": {}})
            else:
                title = "你的学习情况"
                answer = (f"最近 {WINDOW_DAYS} 天你做了 {knowledge['answered_count']} 次客观题，"
                          f"掌握度 {pct(knowledge['mastery'])}%")
                if knowledge["progress"] is not None:
                    answer += f"，已学完 {knowledge['completed_knowledge_count']}/" \
                              f"{knowledge['published_knowledge_count']} 个知识点"
                answer += "。"
                if low:
                    head = low[0]
                    answer += (f"最薄弱的是「{head['title']}」，掌握度 {pct(head['mastery'])}%"
                               f"（答对 {head['correct_count']}/{head['answered_count']} 次）。")
                elif points:
                    answer += f"没有低于 60% 的知识点（最低「{points[0]['title']}」{pct(points[0]['mastery'])}%）。"
                actions.append({"kind": "practice", "label": "去练最薄弱的知识点", "payload": {}})
    else:  # knowledge_qa
        matches = search_knowledge(db, course_id, question)
        if not matches:
            title = "知识库里没有找到相关内容"
            answer = ("课程已发布知识点里没有检索到匹配内容。换一种说法，"
                      "或者直接看对应章节，也可以问老师。")
            actions.append({"kind": "navigate", "label": "打开教学内容", "payload": {"tab": "content"}})
        else:
            head = matches[0]
            title = "最相关：" + head["title"]
            answer = (f"「{head['title']}」：" + head["excerpt"].strip() + "…")
            if len(matches) > 1:
                answer += " 相关知识点还有：" + "、".join(f"「{item['title']}」" for item in matches[1:]) + "。"
            facts = [{"label": item["title"], "value": round(item["similarity"] * 100, 1), "unit": "% 相似度",
                      "note": "相似度不是正确率，只表示文本接近程度", "source": "011"} for item in matches]
            actions.append({"kind": "navigate", "label": "打开教学内容", "payload": {"tab": "content"}})
        return {"intent": "knowledge_qa", "title": title, "answer": answer, "facts": facts,
                "caveats": caveats, "matches": matches, "actions": actions,
                "suggestions": STUDENT_SUGGESTIONS}
    return {"intent": intent, "title": title, "answer": answer, "facts": facts, "caveats": caveats,
            "matches": [], "actions": actions, "charts": charts, "suggestions": STUDENT_SUGGESTIONS}


@bp.post("/courses/<int:course_id>/assistant/ask")
def ask(course_id):
    user = require_user()
    course_access(course_id)
    role = user["role"]
    data = body(("question",), allowed=("student_id",))
    question = text_field(data["question"], "question", 1, MAX_QUESTION)
    requested = data.get("student_id")
    context_student = None
    if requested is not None:
        if role != "teacher":
            raise ApiError(403, "FORBIDDEN", "Students can only ask about themselves")
        requested = positive_int(requested, "student_id")
        member = get_db().execute(
            "SELECT u.id,u.student_no,u.name FROM course_member m JOIN user u ON u.id=m.user_id "
            "WHERE m.course_id=? AND m.user_id=? AND m.member_role='student' AND m.active=1 "
            "AND u.role='student' AND u.active=1", (course_id, requested)).fetchone()
        if not member:
            raise ApiError(404, "NOT_FOUND", "Student not found")
        context_student = dict(member)
    start, end = time_window()
    cutoff = stamp()
    members = roster(get_db(), course_id) if role == "teacher" else []
    intent, target = classify(question, role, members, context_student)
    if role == "teacher" and intent in {"student_attendance", "student_profile"}:
        reply = teacher_student_answer(intent, target, get_db(), course_id, start, end, cutoff)
    elif role == "teacher" and intent == "session_absence":
        reply = teacher_absence_answer(get_db(), course_id)
    elif role == "teacher" and intent == "class_scores":
        reply = class_scores_answer(get_db(), course_id, start, end, cutoff)
    elif role == "teacher" and intent in {"weak_knowledge", "at_risk", "attendance", "advice", "class_overview"}:
        reply = teacher_answer(intent, question, get_db(), course_id, start, end, cutoff)
    elif intent == "clarify":
        reply = clarify_answer(role)
    elif role == "teacher":
        matches = search_knowledge(get_db(), course_id, question)
        if matches:
            head = matches[0]
            reply = {"intent": "knowledge_qa", "title": "最相关：" + head["title"],
                     "answer": f"「{head['title']}」：" + head["excerpt"].strip() + "…",
                     "facts": [{"label": item["title"], "value": round(item["similarity"] * 100, 1),
                                "unit": "% 相似度", "source": "011"} for item in matches],
                     "caveats": [], "matches": matches,
                     "actions": [{"kind": "navigate", "label": "打开教学内容", "payload": {"tab": "content"}}],
                     "suggestions": TEACHER_SUGGESTIONS}
        else:
            reply = {"intent": "knowledge_qa", "title": "没有找到相关内容",
                     "answer": "课程已发布知识点里没有检索到匹配内容。换一种说法，或直接看对应章节。",
                     "facts": [], "caveats": [], "matches": [],
                     "actions": [{"kind": "navigate", "label": "打开教学内容", "payload": {"tab": "content"}}],
                     "suggestions": TEACHER_SUGGESTIONS}
    else:
        # 学生只能问自己：requested 已在上面拦掉非教师传参。
        reply = student_answer(intent, question, get_db(), course_id, user["id"], start, end, cutoff)
    return result({
        **reply,
        "charts": reply.get("charts") or [],
        "role": role,
        "question": question,
        "student_id": target["id"] if role == "teacher" and target else (None if role == "teacher" else user["id"]),
        "student": ({"id": target["id"], "name": target["name"], "student_no": target["student_no"]}
                    if role == "teacher" and target else None),
        "algorithm_version": VERSION,
        "window": {"from": start, "to": end, "days": WINDOW_DAYS},
        "source_until": cutoff,
    })
