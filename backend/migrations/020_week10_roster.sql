-- SPEC-001/002 第10周互测：真实班级名单与课堂点到座位表。
-- 只加列和加表，不改既有列，旧数据保持原样。

-- 班级名称，如 242017；未录入时为 NULL，界面按“未分班”显示。
ALTER TABLE user ADD COLUMN class_name TEXT;

-- 课程内的座位安排：一组座位固定下来，点到时按这个布局渲染教室。
CREATE TABLE class_seat (
  id INTEGER PRIMARY KEY,
  course_id INTEGER NOT NULL REFERENCES course(id),
  student_id INTEGER NOT NULL REFERENCES user(id),
  group_no INTEGER NOT NULL CHECK(group_no BETWEEN 1 AND 12),
  seat_no INTEGER NOT NULL CHECK(seat_no BETWEEN 1 AND 20),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(course_id, student_id)
);
CREATE UNIQUE INDEX class_seat_position ON class_seat(course_id, group_no, seat_no);

-- 点到任务创建时冻结一份座位快照：之后改座位表不影响已发布任务的历史布局。
CREATE TABLE attendance_seat (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES attendance_task(id),
  student_id INTEGER NOT NULL REFERENCES user(id),
  group_no INTEGER NOT NULL,
  seat_no INTEGER NOT NULL,
  UNIQUE(task_id, student_id)
);
CREATE INDEX attendance_seat_task ON attendance_seat(task_id);
