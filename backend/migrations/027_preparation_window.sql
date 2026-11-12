-- SPEC-004 备课排期：补充结束时间，支持「开始—结束」的课时区间。
-- 前端表单由「日期 + 开始时间 + 结束时间」三段组成，结束时间可为空。
ALTER TABLE preparation ADD COLUMN scheduled_end_at TEXT;
