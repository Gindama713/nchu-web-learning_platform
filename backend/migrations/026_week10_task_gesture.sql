-- 第10周：手势图案从「学生个人的图形密码」改成「老师开课时指定的课堂口令」。
--
-- 原来图案存在 user.gesture_hash 上，每个学生自己设一个，教师没法统一要求，
-- 学生也能随时换掉——放到课堂点到里就变成「自己给自己发口令」，没有意义。
-- 改成挂在 attendance_task 上：老师开课时画一次（例如一个 Z），全班照着重画。
-- 图案只存哈希（与签到码同一个思路），库里拿不到图形本身。
--
-- user.gesture_hash / gesture_updated_at 这两列保留不动：024 已经写进历史库，
-- 直接删列要重建 user 表，牵连太多外键，不再使用即可。
ALTER TABLE attendance_task ADD COLUMN gesture_hash TEXT;
