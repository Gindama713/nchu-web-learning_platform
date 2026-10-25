-- SPEC-017 wiring process tables; experiment definitions belong to 009_experiments.sql.

CREATE TABLE wiring_attempt (
    id INTEGER PRIMARY KEY,
    experiment_version_id INTEGER NOT NULL REFERENCES experiment_version(id),
    student_id INTEGER NOT NULL REFERENCES user(id),
    revision INTEGER NOT NULL DEFAULT 0,
    latest_seq INTEGER NOT NULL DEFAULT 0,
    state_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','submitted')),
    completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0,1)),
    functional_results_json TEXT,
    snapshot_hash TEXT,
    saved_at TEXT,
    submitted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(experiment_version_id, student_id)
);
CREATE INDEX wiring_attempt_student ON wiring_attempt(student_id, experiment_version_id);

CREATE TABLE wiring_action (
    attempt_id INTEGER NOT NULL REFERENCES wiring_attempt(id),
    seq INTEGER NOT NULL CHECK(typeof(seq)='integer' AND seq>0),
    type TEXT NOT NULL CHECK(type IN ('connect','disconnect','set_input','step','reset','undo','redo')),
    payload_json TEXT NOT NULL,
    client_at TEXT,
    received_at TEXT NOT NULL,
    PRIMARY KEY(attempt_id, seq)
);
CREATE INDEX wiring_action_attempt ON wiring_action(attempt_id, seq);

CREATE TRIGGER wiring_submitted_frozen BEFORE UPDATE ON wiring_attempt
WHEN OLD.status='submitted' AND NOT (
    NEW.id IS OLD.id AND NEW.experiment_version_id IS OLD.experiment_version_id
    AND NEW.student_id IS OLD.student_id AND NEW.revision IS OLD.revision
    AND NEW.status IS OLD.status AND NEW.state_json IS OLD.state_json
    AND NEW.latest_seq IS OLD.latest_seq AND NEW.snapshot_hash IS OLD.snapshot_hash
    AND NEW.submitted_at IS OLD.submitted_at AND NEW.completed IS OLD.completed
    AND NEW.functional_results_json IS OLD.functional_results_json
    AND NEW.saved_at IS OLD.saved_at AND NEW.created_at IS OLD.created_at
    AND NEW.updated_at IS OLD.updated_at
)
BEGIN SELECT RAISE(ABORT, 'submitted wiring attempt is immutable'); END;
