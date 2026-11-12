"""课堂即时投票：状态判定、资格校验、计票与对错统计。

设计取舍见 docs/PLAN_POLL_20261112.md：
- 投票挂在「进行中的考勤任务」上，只有该任务里已签到（已到/迟到）的学生能投。
- 一人一票由 UNIQUE(poll_id, student_id) 兜底，应用层只负责给出友好错误码。
- 判断题不另写一套：落库时生成「正确 / 错误」两个选项，判分与统计只有一份代码。
"""

from backend.shared.api import ApiError, audit, stamp

TYPES = ("single", "multiple", "boolean")
MIN_OPTIONS = 2
MAX_OPTIONS = 8
BOOLEAN_LABELS = ("正确", "错误")
CHECKED_IN = ("present", "late")


def find(db, poll_id):
    row = db.execute("SELECT * FROM poll WHERE id=?", (poll_id,)).fetchone()
    if not row:
        raise ApiError(404, "POLL_NOT_FOUND", "投票不存在")
    return row


def task_of(db, poll):
    return db.execute("SELECT * FROM attendance_task WHERE id=?", (poll["task_id"],)).fetchone()


def option_rows(db, poll_id):
    return db.execute(
        "SELECT id,ordinal,label,is_correct FROM poll_option WHERE poll_id=? ORDER BY ordinal",
        (poll_id,)).fetchall()


def task_is_open(task, at):
    return bool(task) and task["status"] == "open" and task["start_at"] <= at < task["end_at"]


def is_open(db, poll, at=None):
    """投票是否还能投：自己的状态是 open，且挂着的那节课还在签到窗口里。"""
    return poll["status"] == "open" and task_is_open(task_of(db, poll), at or stamp())


def eligibility(db, poll, student_id):
    """返回 (能否投票, 不能投的原因)。人没签到就不参与表决。"""
    participant = db.execute(
        "SELECT 1 FROM attendance_participant WHERE task_id=? AND student_id=?",
        (poll["task_id"], student_id)).fetchone()
    if not participant:
        return False, "NOT_IN_CLASS"
    record = db.execute(
        "SELECT status FROM attendance_record WHERE task_id=? AND student_id=?",
        (poll["task_id"], student_id)).fetchone()
    if not record or record["status"] not in CHECKED_IN:
        return False, "NOT_CHECKED_IN"
    return True, None


def checked_in_count(db, task_id):
    marks = ",".join("?" for _ in CHECKED_IN)
    return db.execute(
        "SELECT COUNT(*) FROM attendance_participant p JOIN attendance_record r "
        "ON r.task_id=p.task_id AND r.student_id=p.student_id "
        f"WHERE p.task_id=? AND r.status IN ({marks})", (task_id, *CHECKED_IN)).fetchone()[0]


def ballot_count(db, poll_id):
    return db.execute("SELECT COUNT(*) FROM poll_ballot WHERE poll_id=?", (poll_id,)).fetchone()[0]


def my_choices(db, poll_id, student_id):
    rows = db.execute(
        "SELECT c.option_id FROM poll_ballot b JOIN poll_choice c ON c.ballot_id=b.id "
        "WHERE b.poll_id=? AND b.student_id=?", (poll_id, student_id)).fetchall()
    return [row["option_id"] for row in rows]


def create(db, course_id, task_id, title, kind, labels, max_choices, anonymous,
           correct_ordinals, actor_id):
    """建投票。labels 为空且 kind=boolean 时自动用「正确 / 错误」。"""
    if kind not in TYPES:
        raise ApiError(422, "VALIDATION_ERROR", "type 只能是 single/multiple/boolean")
    if kind == "boolean":
        labels = list(BOOLEAN_LABELS)
        if max_choices is not None:
            max_choices = None
        if len(correct_ordinals) > 1:
            raise ApiError(422, "VALIDATION_ERROR", "判断题只能有一个正确答案")
    if not MIN_OPTIONS <= len(labels) <= MAX_OPTIONS:
        raise ApiError(422, "VALIDATION_ERROR", f"选项需要 {MIN_OPTIONS}—{MAX_OPTIONS} 个")
    cleaned = []
    seen = set()
    for label in labels:
        text = " ".join(str(label).split())
        if not text or len(text) > 120:
            raise ApiError(422, "VALIDATION_ERROR", "选项文字需要 1—120 个字符")
        if text in seen:
            raise ApiError(422, "VALIDATION_ERROR", "选项不能重复")
        seen.add(text)
        cleaned.append(text)

    if kind != "multiple":
        max_choices = None
    elif max_choices is not None:
        if not 2 <= max_choices <= len(cleaned):
            raise ApiError(422, "VALIDATION_ERROR", "多选上限需要在 2 和选项数之间")
    for ordinal in correct_ordinals:
        if not 1 <= ordinal <= len(cleaned):
            raise ApiError(422, "VALIDATION_ERROR", "正确答案指向了不存在的选项")

    timestamp = stamp()
    cursor = db.execute(
        "INSERT INTO poll(course_id,task_id,title,type,max_choices,anonymous,has_correct,"
        "status,created_by,created_at) VALUES(?,?,?,?,?,?,?,'open',?,?)",
        (course_id, task_id, title, kind, max_choices, 1 if anonymous else 0,
         1 if correct_ordinals else 0, actor_id, timestamp))
    poll_id = cursor.lastrowid
    correct = set(correct_ordinals)
    db.executemany(
        "INSERT INTO poll_option(poll_id,ordinal,label,is_correct) VALUES(?,?,?,?)",
        [(poll_id, index, label, 1 if index in correct else 0)
         for index, label in enumerate(cleaned, start=1)])
    audit("poll.create", "poll", poll_id,
          after={"course_id": course_id, "task_id": task_id, "type": kind, "options": len(cleaned)})
    return poll_id


def submit(db, poll, student_id, option_ids):
    """投票。一人一票，重复提交 409；多选上限、判断题单选都在这里挡。"""
    if not is_open(db, poll):
        raise ApiError(409, "POLL_CLOSED", "投票已经结束了")
    can_vote, reason = eligibility(db, poll, student_id)
    if not can_vote:
        raise ApiError(403, "NOT_CHECKED_IN", "签到之后才能参与投票")
    existing = db.execute("SELECT id FROM poll_ballot WHERE poll_id=? AND student_id=?",
                          (poll["id"], student_id)).fetchone()
    if existing:
        raise ApiError(409, "ALREADY_VOTED", "已经投过票了")

    valid = {row["id"] for row in option_rows(db, poll["id"])}
    chosen = []
    for option_id in option_ids:
        if option_id not in valid:
            raise ApiError(422, "INVALID_OPTION", "选项不属于这次投票")
        if option_id in chosen:
            continue
        chosen.append(option_id)
    if not chosen:
        raise ApiError(422, "EMPTY_CHOICE", "至少选一项")
    if poll["type"] == "multiple":
        if poll["max_choices"] and len(chosen) > poll["max_choices"]:
            raise ApiError(422, "TOO_MANY_CHOICES", f"最多选 {poll['max_choices']} 项")
    elif len(chosen) > 1:
        raise ApiError(422, "TOO_MANY_CHOICES", "这道题只能选一项")

    timestamp = stamp()
    cursor = db.execute(
        "INSERT INTO poll_ballot(poll_id,student_id,submitted_at) VALUES(?,?,?)",
        (poll["id"], student_id, timestamp))
    db.executemany("INSERT INTO poll_choice(ballot_id,option_id) VALUES(?,?)",
                   [(cursor.lastrowid, option_id) for option_id in chosen])
    audit("poll.vote", "poll", poll["id"], actor_id=student_id,
          after={"options": len(chosen)})
    return chosen


def close(db, poll):
    if poll["status"] == "closed":
        return poll["closed_at"]
    timestamp = stamp()
    db.execute("UPDATE poll SET status='closed',closed_at=? WHERE id=? AND status='open'",
               (timestamp, poll["id"]))
    audit("poll.close", "poll", poll["id"], after={"closed_at": timestamp})
    return timestamp


def results(db, poll):
    """分布 + 参与率；设了正确答案就再算一遍对错分布。

    对错判定按「所选集合 == 正确集合」：多选必须全对才算对，漏选和多选都算错。
    """
    options = option_rows(db, poll["id"])
    tally = {option["id"]: 0 for option in options}
    for row in db.execute(
            "SELECT c.option_id AS option_id,COUNT(*) AS hits FROM poll_choice c "
            "JOIN poll_ballot b ON b.id=c.ballot_id WHERE b.poll_id=? GROUP BY c.option_id",
            (poll["id"],)):
        tally[row["option_id"]] = row["hits"]

    voted = ballot_count(db, poll["id"])
    counts = [{
        "option_id": option["id"], "ordinal": option["ordinal"], "label": option["label"],
        "is_correct": bool(option["is_correct"]), "count": tally[option["id"]],
        "ratio": round(tally[option["id"]] / voted, 4) if voted else 0.0,
    } for option in options]

    correct_set = {option["id"] for option in options if option["is_correct"]}
    payload = {
        "counts": counts,
        "voted": voted,
        "eligible": checked_in_count(db, poll["task_id"]),
        "timeline": timeline(db, poll["id"]),
    }
    if poll["has_correct"] and correct_set:
        right = wrong = 0
        for ballot in db.execute("SELECT id FROM poll_ballot WHERE poll_id=?", (poll["id"],)):
            picked = {row["option_id"] for row in db.execute(
                "SELECT option_id FROM poll_choice WHERE ballot_id=?", (ballot["id"],))}
            if picked == correct_set:
                right += 1
            else:
                wrong += 1
        payload["correct"] = {
            "answered": right + wrong, "right": right, "wrong": wrong,
            "accuracy": round(right / (right + wrong), 4) if right + wrong else 0.0,
            "option_ids": sorted(correct_set),
        }
    return payload


def timeline(db, poll_id, points=24):
    """累计投票人数随时间的变化，折线图用。

    只暴露「第几个时刻累计几票」，不带学号姓名，所以匿名投票也能给。
    票数多于 points 时等距抽样，最后一点一定保留（收尾要落在总票数上）。
    """
    stamps = [row["submitted_at"] for row in db.execute(
        "SELECT submitted_at FROM poll_ballot WHERE poll_id=? ORDER BY submitted_at, id", (poll_id,))]
    if not stamps:
        return []
    total = len(stamps)
    step = max(1, -(-total // points))
    series = [{"at": stamps[index], "count": index + 1} for index in range(0, total, step)]
    if series[-1]["count"] != total:
        series.append({"at": stamps[-1], "count": total})
    return series


def unvoted(db, poll):
    """已签到但还没投的人。老师看参与率用，匿名投票也只是"谁没投"，不泄露选项。"""
    marks = ",".join("?" for _ in CHECKED_IN)
    rows = db.execute(
        "SELECT u.id AS student_id,u.name,u.student_no FROM attendance_participant p "
        "JOIN attendance_record r ON r.task_id=p.task_id AND r.student_id=p.student_id "
        "JOIN user u ON u.id=p.student_id "
        f"WHERE p.task_id=? AND r.status IN ({marks}) AND p.student_id NOT IN "
        "(SELECT student_id FROM poll_ballot WHERE poll_id=?) ORDER BY u.student_no",
        (poll["task_id"], *CHECKED_IN, poll["id"])).fetchall()
    return [{"student_id": row["student_id"], "name": row["name"],
             "student_no": row["student_no"]} for row in rows]


def response(db, poll):
    """一次投票的公共表示：题目、选项、参与情况、当前状态。"""
    options = option_rows(db, poll["id"])
    voted = ballot_count(db, poll["id"])
    open_now = is_open(db, poll)
    return {
        "id": poll["id"], "course_id": poll["course_id"], "task_id": poll["task_id"],
        "title": poll["title"], "type": poll["type"], "max_choices": poll["max_choices"],
        "anonymous": bool(poll["anonymous"]), "has_correct": bool(poll["has_correct"]),
        "status": poll["status"], "open": open_now,
        "created_at": poll["created_at"], "closed_at": poll["closed_at"],
        "voted": voted, "eligible": checked_in_count(db, poll["task_id"]),
        "options": [{"id": option["id"], "ordinal": option["ordinal"], "label": option["label"]}
                    for option in options],
    }
