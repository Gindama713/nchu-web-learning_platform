-- SPEC-003 题库导入批次：一次导入的审计记录（DBD question_import）
-- question/version 复用 006_question_versions 的表；幂等记录复用 006c 的 idempotency_record。

CREATE TABLE question_import (
    id INTEGER PRIMARY KEY,
    resource_version_id INTEGER NOT NULL REFERENCES resource_version(id),
    actor_id INTEGER NOT NULL REFERENCES user(id),
    count INTEGER NOT NULL CHECK(count > 0),
    created_at TEXT NOT NULL
);
CREATE INDEX question_import_version ON question_import(resource_version_id, created_at);
