-- SPEC-010C 连线验证记录。每次结构验证追加一行，用于错误统计去重。
-- 同一 attempt/revision/code 只计一次错误。

CREATE TABLE wiring_validation (
    id INTEGER PRIMARY KEY,
    attempt_id INTEGER NOT NULL REFERENCES wiring_attempt(id),
    revision INTEGER NOT NULL,
    valid INTEGER NOT NULL CHECK(valid IN (0,1)),
    errors_json TEXT NOT NULL,
    validator_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX wiring_validation_attempt ON wiring_validation(attempt_id, revision);
