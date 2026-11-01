-- SPEC-001 访问日志：满足任务书「记录具体用户在何时访问了哪个模块、页面或 API」，
-- 并能导出 CSV / JSON 的要求。audit_event 记的是关键操作的输入与结果，两者互补。

CREATE TABLE access_log (
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES user(id),
  student_no TEXT,
  name TEXT,
  role TEXT,
  method TEXT NOT NULL,
  path TEXT NOT NULL,
  status INTEGER NOT NULL,
  ip TEXT,
  duration_ms REAL,
  at TEXT NOT NULL
);
CREATE INDEX access_log_at ON access_log(at);
CREATE INDEX access_log_user ON access_log(user_id, at);
