-- SPEC-009 实验辅助：experiment / experiment_version / experiment_knowledge / experiment_participant
-- judge_profile 表供 ExperimentVersion 读模型派生 judge_profile_id 及发布闸门使用，
-- 其管理端点（PUT /experiment-versions/{id}/judge-profile 等）属于 SPEC-018，本迁移只建表。
-- wiring_attempt / wiring_action 等过程表属于 SPEC-017，此处不建。

CREATE TABLE experiment (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES course(id),
    code TEXT NOT NULL CHECK(code IN ('EXP-01','EXP-02','EXP-03','EXP-04')),
    title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 100),
    description TEXT,
    archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(course_id, code)
);

CREATE TABLE experiment_version (
    id INTEGER PRIMARY KEY,
    experiment_id INTEGER NOT NULL REFERENCES experiment(id),
    version INTEGER NOT NULL CHECK(version >= 1),
    title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 100),
    objectives TEXT NOT NULL,
    instructions TEXT NOT NULL,
    submission_modes_json TEXT NOT NULL,
    panel_json TEXT,
    rules_json TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published')),
    published_at TEXT,
    start_at TEXT,
    end_at TEXT,
    definition_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(experiment_id, version),
    -- 已发布版本必须带完整窗口；draft 不带
    CHECK((status = 'draft') OR (published_at IS NOT NULL AND start_at IS NOT NULL AND end_at IS NOT NULL))
);
CREATE INDEX experiment_version_experiment ON experiment_version(experiment_id, version);
CREATE INDEX experiment_version_status ON experiment_version(status, created_at);

CREATE TABLE experiment_knowledge (
    experiment_version_id INTEGER NOT NULL REFERENCES experiment_version(id),
    knowledge_id INTEGER NOT NULL REFERENCES knowledge_point(id),
    PRIMARY KEY(experiment_version_id, knowledge_id)
);

CREATE TABLE experiment_participant (
    experiment_version_id INTEGER NOT NULL REFERENCES experiment_version(id),
    student_id INTEGER NOT NULL REFERENCES user(id),
    PRIMARY KEY(experiment_version_id, student_id)
);
CREATE INDEX experiment_participant_student ON experiment_participant(student_id, experiment_version_id);

CREATE TABLE judge_profile (
    id INTEGER PRIMARY KEY,
    experiment_version_id INTEGER NOT NULL UNIQUE REFERENCES experiment_version(id),
    top_circuit TEXT NOT NULL,
    port_schema_json TEXT NOT NULL,
    allowed_components_json TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    jar_sha256 TEXT,
    limits_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
