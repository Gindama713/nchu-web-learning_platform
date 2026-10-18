-- SPEC-018 电路在线评测：test_suite / test_case / submission / grading_run / case_result /
-- experiment_grading / test_suite_validation / reference_file。
-- judge_profile 主体表由 009_experiments.sql 创建；按 DBD 第7节补充 canonical_sha256
-- （包含端口、白名单、限制、引擎身份），实验发布后 profile 冻结。

ALTER TABLE judge_profile ADD COLUMN canonical_sha256 TEXT;

CREATE TABLE test_suite (
    id INTEGER PRIMARY KEY,
    experiment_version_id INTEGER NOT NULL REFERENCES experiment_version(id),
    version INTEGER NOT NULL CHECK(version >= 1),
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published')),
    content_sha256 TEXT NOT NULL,
    scoring_groups_json TEXT NOT NULL,
    published_at TEXT,
    published_validation_id INTEGER REFERENCES test_suite_validation(id),
    created_at TEXT NOT NULL,
    UNIQUE(experiment_version_id, version)
);
CREATE INDEX test_suite_version_status ON test_suite(experiment_version_id, status);

CREATE TABLE test_case (
    id INTEGER PRIMARY KEY,
    suite_id INTEGER NOT NULL REFERENCES test_suite(id),
    label TEXT NOT NULL CHECK(length(label) BETWEEN 1 AND 100),
    visibility TEXT NOT NULL CHECK(visibility IN ('public','hidden')),
    group_code TEXT NOT NULL,
    steps_json TEXT NOT NULL,
    UNIQUE(suite_id, label)
);
CREATE INDEX test_case_suite ON test_case(suite_id, group_code);

CREATE TABLE reference_file (
    id INTEGER PRIMARY KEY,
    experiment_version_id INTEGER NOT NULL REFERENCES experiment_version(id),
    file_id INTEGER NOT NULL REFERENCES file_object(id),
    kind TEXT NOT NULL CHECK(kind IN ('correct','known_wrong')),
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(experiment_version_id, file_id)
);

CREATE TABLE submission (
    id INTEGER PRIMARY KEY,
    experiment_version_id INTEGER NOT NULL REFERENCES experiment_version(id),
    student_id INTEGER NOT NULL REFERENCES user(id),
    file_id INTEGER NOT NULL REFERENCES file_object(id),
    file_sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK(size_bytes BETWEEN 1 AND 2097152),
    filename TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX submission_student ON submission(student_id, experiment_version_id, created_at);
CREATE INDEX submission_version_date ON submission(experiment_version_id, created_at);

-- 状态八态见 PRD 第7节；score_hundredths 为 0—10000（两位小数分）；
-- passed≤executed≤total；受理时固化 suite/profile/JAR 身份快照（R03/AC-10）。
CREATE TABLE grading_run (
    id INTEGER PRIMARY KEY,
    submission_id INTEGER NOT NULL REFERENCES submission(id),
    suite_id INTEGER NOT NULL REFERENCES test_suite(id),
    engine_version TEXT NOT NULL,
    jar_sha256 TEXT,
    status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN
        ('queued','running','accepted','wrong_answer','timeout','resource_limit',
         'invalid_circuit','system_error')),
    score_hundredths INTEGER CHECK(score_hundredths IS NULL OR
        (score_hundredths BETWEEN 0 AND 10000)),
    passed_count INTEGER NOT NULL DEFAULT 0 CHECK(passed_count >= 0),
    executed_count INTEGER NOT NULL DEFAULT 0 CHECK(executed_count >= 0),
    total_count INTEGER NOT NULL DEFAULT 0 CHECK(total_count >= 0),
    started_at TEXT,
    finished_at TEXT,
    error_code TEXT,
    retry_of INTEGER REFERENCES grading_run(id),
    reason TEXT,
    worker_token TEXT,
    lease_until TEXT,
    sandbox_id TEXT,
    profile_snapshot_json TEXT NOT NULL,
    profile_sha256 TEXT NOT NULL,
    suite_sha256 TEXT NOT NULL,
    reference_validation_id INTEGER REFERENCES test_suite_validation(id),
    created_at TEXT NOT NULL,
    CHECK(passed_count <= executed_count AND executed_count <= total_count)
);
CREATE INDEX grading_run_status_date ON grading_run(status, created_at);
CREATE INDEX grading_run_status_lease ON grading_run(status, lease_until);
CREATE INDEX grading_run_submission ON grading_run(submission_id, id);
-- 同一 submission 同时最多一个排队/运行中的 run（DBD 第7节）
CREATE UNIQUE INDEX grading_run_one_active ON grading_run(submission_id)
    WHERE status IN ('queued','running');

CREATE TABLE case_result (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES grading_run(id),
    case_id INTEGER NOT NULL REFERENCES test_case(id),
    passed INTEGER NOT NULL CHECK(passed IN (0,1)),
    actual_json TEXT,
    elapsed_ms INTEGER,
    error_code TEXT,
    UNIQUE(run_id, case_id)
);

-- 仅 circuit 模式；active_suite 必须同实验版本 published 且证书有效；切换原子更新 revision
CREATE TABLE experiment_grading (
    experiment_version_id INTEGER PRIMARY KEY REFERENCES experiment_version(id),
    active_suite_id INTEGER NOT NULL REFERENCES test_suite(id),
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1)
);

-- passed 需要标准电路全过、反例至少一项功能失败；不接受反例 system_error/超时作验证成功
CREATE TABLE test_suite_validation (
    id INTEGER PRIMARY KEY,
    suite_id INTEGER NOT NULL REFERENCES test_suite(id),
    profile_sha256 TEXT NOT NULL,
    suite_sha256 TEXT NOT NULL,
    jar_sha256 TEXT,
    reference_file_id INTEGER NOT NULL REFERENCES reference_file(id),
    reference_sha256 TEXT NOT NULL,
    negative_file_id INTEGER NOT NULL REFERENCES reference_file(id),
    negative_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN
        ('queued','running','passed','failed','system_error')),
    result_json TEXT,
    error_code TEXT,
    worker_token TEXT,
    lease_until TEXT,
    sandbox_id TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX test_suite_validation_suite ON test_suite_validation(suite_id, status);
