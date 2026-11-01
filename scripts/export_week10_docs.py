"""从数据库导出第10周被测组要交的两份记录。

    docs/week10-server-log.md     访问日志记录（谁在何时访问了哪个模块/接口）
    docs/week10-server-report.md  本组系统生成的点到结果

任务书要求这两份由被测组提交，内容必须来自系统实际记录，不能手写编造，
因此这里全部从 access_log / attendance_* 表读取，并带上导出时间与统计口径。

    python scripts/export_week10_docs.py
    python scripts/export_week10_docs.py --db instance/app.db --out docs
"""

from __future__ import annotations

# ruff: noqa: UP031  — 报表行以 % 拼接更直观，无需转 f-string
import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

STATUS_LABEL = {"present": "已到", "late": "迟到", "leave": "请假", "absent": "缺勤", "pending": "未签到"}


def stamp():
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_time(value):
    if not value:
        return "—"
    try:
        moment = datetime.fromisoformat(value).astimezone()
        return moment.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value


def build_log(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        total = db.execute("SELECT COUNT(*) FROM access_log").fetchone()[0]
        users = db.execute("SELECT COUNT(DISTINCT user_id) FROM access_log WHERE user_id IS NOT NULL").fetchone()[0]
        failed = db.execute("SELECT COUNT(*) FROM access_log WHERE status>=400").fetchone()[0]
        first = db.execute("SELECT MIN(at) FROM access_log").fetchone()[0]
        last = db.execute("SELECT MAX(at) FROM access_log").fetchone()[0]

        lines = [
            "# 第10周 用户访问日志记录",
            "",
            "- 小组：g24201710（计算机组成原理组，242017 班）",
            f"- 导出时间：{local_time(stamp())}",
            f"- 日志区间：{local_time(first)} — {local_time(last)}",
            ("- 统计口径：`access_log` 表按每次 HTTP 请求记一条，含登录前的匿名请求；"
            "导出脚本为 `scripts/export_week10_docs.py`，可用 `python scripts/export_week10_docs.py` 复现。"),
            "",
            "## 1 概览",
            "",
            "| 指标 | 数值 |",
            "|---|---|",
            "| 请求总数 | %d |" % total,
            "| 有登录身份的账号数 | %d |" % users,
            "| 失败请求（状态码 ≥ 400） | %d |" % failed,
            "",
        ]

        lines += ["## 2 按账号统计", "",
                  "| 学号 | 姓名 | 角色 | 请求数 | 失败数 | 最近访问 |",
                  "|---|---|---|---|---|---|"]
        for row in db.execute(
                "SELECT student_no,name,role,COUNT(*) n,SUM(status>=400) bad,MAX(at) last "
                "FROM access_log WHERE user_id IS NOT NULL GROUP BY user_id ORDER BY n DESC"):
            lines.append("| %s | %s | %s | %d | %d | %s |" % (
                row["student_no"], row["name"], row["role"], row["n"], row["bad"] or 0, local_time(row["last"])))
        lines.append("")

        lines += ["## 3 访问最多的接口", "",
                  "| 方法 | 路径 | 次数 |", "|---|---|---|"]
        for row in db.execute("SELECT method,path,COUNT(*) n FROM access_log "
                              "GROUP BY method,path ORDER BY n DESC LIMIT 15"):
            lines.append("| %s | %s | %d |" % (row["method"], row["path"], row["n"]))
        lines.append("")

        lines += ["## 4 失败请求明细", "",
                  "权限隔离与限流的直接证据，按时间倒序最多列 30 条。", "",
                  "| 时间 | 学号 | 方法 | 路径 | 状态 |", "|---|---|---|---|---|"]
        for row in db.execute("SELECT at,student_no,method,path,status FROM access_log "
                              "WHERE status>=400 ORDER BY id DESC LIMIT 30"):
            lines.append("| %s | %s | %s | %s | %d |" % (
                local_time(row["at"]), row["student_no"] or "未登录", row["method"], row["path"], row["status"]))
        lines.append("")

        lines += ["## 5 最近访问明细", "",
                  "| 时间 | 学号 | 姓名 | 方法 | 路径 | 状态 | 耗时(ms) |",
                  "|---|---|---|---|---|---|---|"]
        for row in db.execute("SELECT at,student_no,name,method,path,status,duration_ms "
                              "FROM access_log ORDER BY id DESC LIMIT 40"):
            lines.append("| %s | %s | %s | %s | %s | %d | %s |" % (
                local_time(row["at"]), row["student_no"] or "—", row["name"] or "—",
                row["method"], row["path"], row["status"], row["duration_ms"]))
        lines.append("")
        lines.append("> 完整日志可在线导出：`GET /api/v1/logs/access.csv`（教师/管理员）"
                     "或 `GET /api/v1/logs/access`（JSON）。")
        return "\n".join(lines) + "\n"
    finally:
        db.close()


def build_report(path, course_title=None):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        if course_title:
            course = db.execute("SELECT id FROM course WHERE title=?", (course_title,)).fetchone()
            if course is None:
                raise SystemExit(f"找不到课程：{course_title}")
            tasks = db.execute("SELECT * FROM attendance_task WHERE course_id=? ORDER BY id DESC",
                               (course["id"],)).fetchall()
        else:
            tasks = db.execute("SELECT * FROM attendance_task ORDER BY id DESC").fetchall()
        lines = [
            "# 第10周 本组系统生成的点到结果",
            "",
            "- 小组：g24201710（计算机组成原理组，242017 班）",
            f"- 导出时间：{local_time(stamp())}",
            ("- 统计口径：按点到任务统计冻结参与人的四种状态；关闭任务时未签到者自动记缺勤。"
            "座位按课程座位表的「班级-组号-座号」冻结进任务。"),
            "- 数据源：`attendance_task` / `attendance_participant` / `attendance_record` / `attendance_seat`。",
            "",
            "## 1 任务汇总",
            "",
            "| 任务ID | 标题 | 状态 | 开始 | 截止 | 应到 | 已到 | 迟到 | 请假 | 缺勤 |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for task in tasks:
            expected = db.execute("SELECT COUNT(*) FROM attendance_participant WHERE task_id=?",
                                  (task["id"],)).fetchone()[0]
            counts = {key: 0 for key in ("present", "late", "leave", "absent")}
            for row in db.execute("SELECT status,COUNT(*) n FROM attendance_record "
                                  "WHERE task_id=? GROUP BY status", (task["id"],)):
                counts[row["status"]] = row["n"]
            lines.append("| %d | %s | %s | %s | %s | %d | %d | %d | %d | %d |" % (
                task["id"], task["title"], "进行中" if task["status"] == "open" else "已结算",
                local_time(task["start_at"]), local_time(task["end_at"]), expected,
                counts["present"], counts["late"], counts["leave"], counts["absent"]))
        lines.append("")

        for task in tasks:
            seats = db.execute(
                "SELECT u.class_name,u.student_no,u.name,s.group_no,s.seat_no,r.status,r.checked_at "
                "FROM attendance_participant p JOIN user u ON u.id=p.student_id "
                "LEFT JOIN attendance_seat s ON s.task_id=p.task_id AND s.student_id=p.student_id "
                "LEFT JOIN attendance_record r ON r.task_id=p.task_id AND r.student_id=p.student_id "
                "WHERE p.task_id=? ORDER BY u.class_name,s.group_no,s.seat_no", (task["id"],)).fetchall()
            lines += ["## 2.%d 任务 %d「%s」" % (tasks.index(task) + 1, task["id"], task["title"]), ""]
            by_class = {}
            for row in seats:
                by_class.setdefault(row["class_name"] or "未分班", []).append(row)
            lines += ["| 班级 | 应到 | 已到 | 迟到 | 请假 | 缺勤 | 未签到 |",
                      "|---|---|---|---|---|---|---|"]
            for class_name, rows in sorted(by_class.items()):
                stat = {key: 0 for key in ("present", "late", "leave", "absent", "pending")}
                for row in rows:
                    stat[row["status"] or "pending"] += 1
                lines.append("| %s | %d | %d | %d | %d | %d | %d |" % (
                    class_name, len(rows), stat["present"], stat["late"],
                    stat["leave"], stat["absent"], stat["pending"]))
            lines.append("")

            abnormal = [row for row in seats if (row["status"] or "pending") != "present"]
            if abnormal:
                lines += ["异常名单（非“已到”）：", "",
                          "| 班级 | 座位 | 学号 | 姓名 | 状态 | 签到时间 |", "|---|---|---|---|---|---|"]
                for row in abnormal[:60]:
                    seat = "{}-{}".format(row["group_no"], row["seat_no"]) if row["group_no"] else "未排座"
                    lines.append("| {} | {} | {} | {} | {} | {} |".format(
                        row["class_name"] or "未分班", seat, row["student_no"], row["name"],
                        STATUS_LABEL.get(row["status"] or "pending", row["status"]),
                        local_time(row["checked_at"])))
                if len(abnormal) > 60:
                    lines.append("| … | 其余 %d 条略 | | | | |" % (len(abnormal) - 60))
                lines.append("")

        lines.append("> 课堂座位图在「考勤与学情 → 教室座位图」实时展示；"
                     "接口为 `GET /api/v1/attendance-tasks/{id}/seats`。")
        return "\n".join(lines) + "\n"
    finally:
        db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="导出第10周被测组记录")
    parser.add_argument("--db", default="instance/app.db")
    parser.add_argument("--out", default="docs")
    parser.add_argument("--course", default="计算机组成原理 · 课堂点到（第10周）",
                        help="只导出该课程的点到任务；传空字符串则导出全部")
    args = parser.parse_args(argv)

    path = Path(args.db)
    if not path.exists():
        print(f"数据库不存在：{path}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    log_text = build_log(path)
    report_text = build_report(path, args.course or None)
    (out / "week10-server-log.md").write_text(log_text, encoding="utf-8", newline="\n")
    (out / "week10-server-report.md").write_text(report_text, encoding="utf-8", newline="\n")
    print("已写入 {} 与 {}".format(out / "week10-server-log.md", out / "week10-server-report.md"))
    print("日志 %d 字，报告 %d 字" % (len(log_text), len(report_text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
