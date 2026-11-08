-- SPEC-002 第10周互测：教师自定义教室规模。
--
-- 021 把座位写死成「12 组 × 20 座」，一颗座位对应一个组号。实际教室
-- （尤其是阶梯教室）行列远超这个范围，教师也需要按自己的教室改。
-- 这里把 class_seat 的 CHECK 放宽到 1-40，并把语义明确成二维坐标：
--   group_no = 第几排，seat_no = 第几座。
-- 021 已被 schema_migration 记录校验和，改动会让 migrate() 直接报
-- “Migration changed after application”，所以只能新建这一份来演进。
--
-- 用「建新表 → 搬数据 → 删旧表 → 改名」而不是直接 DROP 重建，
-- 已经排好座的课程不会因为这次迁移丢座位。

CREATE TABLE class_seat_next (
  id INTEGER PRIMARY KEY,
  course_id INTEGER NOT NULL REFERENCES course(id),
  student_id INTEGER NOT NULL REFERENCES user(id),
  class_name TEXT NOT NULL,
  group_no INTEGER NOT NULL CHECK(group_no BETWEEN 1 AND 40),
  seat_no INTEGER NOT NULL CHECK(seat_no BETWEEN 1 AND 40),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(course_id, student_id),
  UNIQUE(course_id, class_name, group_no, seat_no)
);

INSERT INTO class_seat_next(id,course_id,student_id,class_name,group_no,seat_no,created_at,updated_at)
  SELECT id,course_id,student_id,class_name,group_no,seat_no,created_at,updated_at FROM class_seat;

DROP TABLE class_seat;

ALTER TABLE class_seat_next RENAME TO class_seat;

CREATE INDEX class_seat_class ON class_seat(course_id, class_name);

-- 教室规模是课程级配置：同一门课的多个班共用一间教室，座位图按
-- rows × cols 铺开。aisle_every 表示「每几座留一条过道」，0 表示不留。
CREATE TABLE classroom (
  id INTEGER PRIMARY KEY,
  course_id INTEGER NOT NULL UNIQUE REFERENCES course(id),
  name TEXT NOT NULL,
  template TEXT NOT NULL,
  rows INTEGER NOT NULL CHECK(rows BETWEEN 1 AND 40),
  cols INTEGER NOT NULL CHECK(cols BETWEEN 1 AND 40),
  aisle_every INTEGER NOT NULL DEFAULT 0 CHECK(aisle_every BETWEEN 0 AND 10),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
