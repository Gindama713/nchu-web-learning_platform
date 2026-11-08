-- 025_week10_seat_swap.sql
-- 学生自助换位：点到别人座位时向对方发起申请，对方登录后答复，15 分钟不答复自动失效。
--
-- 「一次只能申请换一个位置」不靠应用层自觉判断，用部分唯一索引兜住：
-- 同一个 requester 最多只能有一条 status='pending'，并发下也插不进第二条。
--
-- from_/to_ 坐标是发起那一刻的快照，答复时用来校验双方座位有没有在这段时间里变过。

CREATE TABLE seat_swap_request (
  id INTEGER PRIMARY KEY,
  course_id INTEGER NOT NULL REFERENCES course(id),
  requester_id INTEGER NOT NULL REFERENCES user(id),
  target_id INTEGER NOT NULL REFERENCES user(id),
  from_group INTEGER NOT NULL,
  from_seat INTEGER NOT NULL,
  to_group INTEGER NOT NULL,
  to_seat INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','accepted','declined','expired','cancelled')),
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  responded_at TEXT
);

CREATE UNIQUE INDEX seat_swap_one_pending ON seat_swap_request(requester_id) WHERE status='pending';
CREATE INDEX seat_swap_target_pending ON seat_swap_request(target_id, status);
CREATE INDEX seat_swap_course ON seat_swap_request(course_id, status);
