-- 020 建的 class_seat 只按 (course_id, group_no, seat_no) 唯一，一个课程放不下多个班：
-- 4 个班各自从「第 1 组第 1 座」开始，会直接撞唯一约束。
-- 座位属于「哪个班的第几组第几座」，因此加上 class_name 并纳入唯一键。
-- 020 应用时表内还没有数据，直接重建即可。

DROP TABLE class_seat;

CREATE TABLE class_seat (
  id INTEGER PRIMARY KEY,
  course_id INTEGER NOT NULL REFERENCES course(id),
  student_id INTEGER NOT NULL REFERENCES user(id),
  class_name TEXT NOT NULL,
  group_no INTEGER NOT NULL CHECK(group_no BETWEEN 1 AND 12),
  seat_no INTEGER NOT NULL CHECK(seat_no BETWEEN 1 AND 20),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(course_id, student_id),
  UNIQUE(course_id, class_name, group_no, seat_no)
);
CREATE INDEX class_seat_class ON class_seat(course_id, class_name);
