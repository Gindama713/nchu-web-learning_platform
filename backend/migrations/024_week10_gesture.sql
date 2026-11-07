-- SPEC-002 第10周：学生端手势图案签到。
--
-- 和签到码并存：签到码是老师课上念的公共码，手势图案是学生自己的
-- 「图形密码」，两者都能完成一次签到，靠 attendance_record.source 区分。
-- 图案本身不落库，只存哈希（与口令同一个哈希器），泄露数据库也拿不到图案。
--
-- attendance_record.source 原有的 CHECK 只允许 checkin/approval/close/correction，
-- SQLite 不能改 CHECK，只能重建表；这张表没有索引，直接搬数据即可。

ALTER TABLE user ADD COLUMN gesture_hash TEXT;
ALTER TABLE user ADD COLUMN gesture_updated_at TEXT;

CREATE TABLE attendance_record_next (
  id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('present','late','leave','absent')),
  checked_at TEXT,
  source TEXT NOT NULL CHECK(source IN ('checkin','gesture','approval','close','correction')),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(task_id,student_id),
  FOREIGN KEY(task_id,student_id) REFERENCES attendance_participant(task_id,student_id)
);

INSERT INTO attendance_record_next(id,task_id,student_id,status,checked_at,source,created_at,updated_at)
  SELECT id,task_id,student_id,status,checked_at,source,created_at,updated_at FROM attendance_record;

DROP TABLE attendance_record;

ALTER TABLE attendance_record_next RENAME TO attendance_record;
