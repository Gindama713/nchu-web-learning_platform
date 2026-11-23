-- 027_poll.sql
-- 课堂即时投票：老师在一节「进行中的考勤任务」里抛题，已签到的学生点选，老师实时看分布。
--
-- 与试卷（paper/attempt）刻意分开：投票不计分、没有答卷生命周期、要求实时出结果。
-- 与 SPEC-008 随堂测的区别见 docs/PLAN_POLL_20261112.md 第 1 节。
--
-- 一人一票不靠应用层判断，用 UNIQUE(poll_id, student_id) 兜住：并发也插不进第二张。
-- 选项与票分成两张表（单选一行、多选多行），统计统一走 GROUP BY option_id，
-- 不在 SQLite 里拆 JSON 数组（那样没法建索引）。
-- 判断题（boolean）不另存类型，落库时自动生成「正确 / 错误」两个选项，
-- 这样判分、统计、渲染三条链路都只有一套代码。

CREATE TABLE poll (
  id INTEGER PRIMARY KEY,
  course_id INTEGER NOT NULL REFERENCES course(id),
  task_id INTEGER NOT NULL REFERENCES attendance_task(id),
  title TEXT NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('single','multiple','boolean')),
  max_choices INTEGER CHECK(max_choices IS NULL OR max_choices BETWEEN 2 AND 26),
  anonymous INTEGER NOT NULL DEFAULT 1 CHECK(anonymous IN (0,1)),
  has_correct INTEGER NOT NULL DEFAULT 0 CHECK(has_correct IN (0,1)),
  status TEXT NOT NULL CHECK(status IN ('open','closed')),
  created_by INTEGER NOT NULL REFERENCES user(id),
  created_at TEXT NOT NULL,
  closed_at TEXT
);
CREATE INDEX poll_course ON poll(course_id, status);
CREATE INDEX poll_task ON poll(task_id);

CREATE TABLE poll_option (
  id INTEGER PRIMARY KEY,
  poll_id INTEGER NOT NULL REFERENCES poll(id),
  ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 26),
  label TEXT NOT NULL,
  is_correct INTEGER NOT NULL DEFAULT 0 CHECK(is_correct IN (0,1)),
  UNIQUE(poll_id, ordinal)
);

CREATE TABLE poll_ballot (
  id INTEGER PRIMARY KEY,
  poll_id INTEGER NOT NULL REFERENCES poll(id),
  student_id INTEGER NOT NULL REFERENCES user(id),
  submitted_at TEXT NOT NULL,
  UNIQUE(poll_id, student_id)
);
CREATE INDEX poll_ballot_poll ON poll_ballot(poll_id);

CREATE TABLE poll_choice (
  ballot_id INTEGER NOT NULL REFERENCES poll_ballot(id),
  option_id INTEGER NOT NULL REFERENCES poll_option(id),
  PRIMARY KEY(ballot_id, option_id)
);
CREATE INDEX poll_choice_option ON poll_choice(option_id);
