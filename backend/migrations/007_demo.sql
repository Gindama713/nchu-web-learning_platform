-- SPEC-007 课堂演示会话。
-- state 为 JSON，结构由内置可信场景引擎定义。
-- experiment_version_id 暂不加外键，待 SPEC-009 实验模块落地后补齐。

CREATE TABLE demo_session (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES course(id),
    preset TEXT NOT NULL CHECK(preset IN ('gate','comb','sequential','alu','memory','cpu')),
    experiment_version_id INTEGER,
    revision INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX demo_course_active ON demo_session(course_id, active, id);

CREATE TRIGGER demo_closed_frozen BEFORE UPDATE ON demo_session
WHEN OLD.active=0 AND NOT (
    NEW.id IS OLD.id AND NEW.course_id IS OLD.course_id AND NEW.preset IS OLD.preset
    AND NEW.experiment_version_id IS OLD.experiment_version_id AND NEW.revision IS OLD.revision
    AND NEW.state IS OLD.state AND NEW.active IS OLD.active
    AND NEW.created_at IS OLD.created_at AND NEW.updated_at IS OLD.updated_at
)
BEGIN SELECT RAISE(ABORT, 'closed demo session is immutable'); END;
