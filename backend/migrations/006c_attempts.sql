CREATE TABLE attempt (
    id INTEGER PRIMARY KEY,
    paper_id INTEGER NOT NULL REFERENCES paper(id),
    student_id INTEGER NOT NULL REFERENCES user(id),
    status TEXT NOT NULL CHECK(status IN ('partial','graded')),
    score_hundredths INTEGER,
    partial_score_hundredths INTEGER NOT NULL CHECK(typeof(partial_score_hundredths)='integer' AND partial_score_hundredths>=0),
    revision INTEGER NOT NULL DEFAULT 0 CHECK(typeof(revision)='integer' AND revision>=0),
    submitted_at TEXT NOT NULL,
    UNIQUE(paper_id,student_id),
    FOREIGN KEY(paper_id,student_id) REFERENCES paper_participant(paper_id,student_id),
    CHECK((status='partial' AND score_hundredths IS NULL) OR
        (status='graded' AND typeof(score_hundredths)='integer' AND score_hundredths=partial_score_hundredths))
);
CREATE INDEX attempt_student ON attempt(student_id,paper_id,id);
CREATE TABLE answer (
    id INTEGER PRIMARY KEY,
    attempt_id INTEGER NOT NULL REFERENCES attempt(id),
    question_version_id INTEGER NOT NULL REFERENCES question_version(id),
    value_json TEXT NOT NULL,
    score_hundredths INTEGER CHECK(score_hundredths IS NULL OR (typeof(score_hundredths)='integer' AND score_hundredths>=0)),
    answered INTEGER NOT NULL CHECK(answered IN (0,1)),
    graded_by INTEGER REFERENCES user(id),
    comment TEXT NOT NULL DEFAULT '' CHECK(length(comment)<=1000),
    UNIQUE(attempt_id,question_version_id),
    CHECK(answered=1 OR (value_json='null' AND score_hundredths IS NOT NULL AND score_hundredths=0))
);
CREATE INDEX answer_version ON answer(question_version_id,attempt_id);

-- Shared APIC section 11 ledger; C03a only consumes operation=paper_attempt.
CREATE TABLE idempotency_record (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES user(id),
    operation TEXT NOT NULL,
    key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id INTEGER NOT NULL,
    response_status INTEGER NOT NULL CHECK(response_status BETWEEN 200 AND 299),
    response_json TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    UNIQUE(user_id,operation,key)
);
CREATE INDEX idempotency_expiry ON idempotency_record(expires_at);

CREATE TRIGGER attempt_published_guard BEFORE INSERT ON attempt
WHEN (SELECT status FROM paper WHERE id=NEW.paper_id)!='published'
BEGIN SELECT RAISE(ABORT,'attempt requires published paper'); END;
CREATE TRIGGER attempt_identity_frozen BEFORE UPDATE ON attempt
WHEN NEW.id IS NOT OLD.id OR NEW.paper_id IS NOT OLD.paper_id OR NEW.student_id IS NOT OLD.student_id
    OR NEW.submitted_at IS NOT OLD.submitted_at
BEGIN SELECT RAISE(ABORT,'submission identity is frozen'); END;
CREATE TRIGGER attempt_no_delete BEFORE DELETE ON attempt
BEGIN SELECT RAISE(ABORT,'attempts are retained'); END;
CREATE TRIGGER answer_insert_guard BEFORE INSERT ON answer
WHEN NOT EXISTS (
    SELECT 1 FROM attempt a JOIN paper_item i ON i.paper_id=a.paper_id
    JOIN question_version v ON v.id=i.question_version_id
    WHERE a.id=NEW.attempt_id AND i.question_version_id=NEW.question_version_id
        AND ((NEW.score_hundredths IS NULL AND v.type='short' AND NEW.answered=1)
            OR (NEW.score_hundredths IS NOT NULL AND NEW.score_hundredths<=i.points_hundredths
                AND (v.type='short' OR NEW.score_hundredths IN (0,i.points_hundredths)))))
BEGIN SELECT RAISE(ABORT,'answer must belong to paper with valid score'); END;
CREATE TRIGGER answer_update_guard BEFORE UPDATE ON answer
WHEN NEW.id IS NOT OLD.id OR NEW.attempt_id IS NOT OLD.attempt_id
    OR NEW.question_version_id IS NOT OLD.question_version_id OR NEW.value_json IS NOT OLD.value_json
    OR NEW.answered IS NOT OLD.answered OR NOT EXISTS (
        SELECT 1 FROM attempt a JOIN paper_item i ON i.paper_id=a.paper_id
        JOIN question_version v ON v.id=i.question_version_id
        WHERE a.id=NEW.attempt_id AND i.question_version_id=NEW.question_version_id
            AND v.type='short' AND NEW.answered=1
            AND (NEW.score_hundredths IS NULL OR NEW.score_hundredths<=i.points_hundredths))
BEGIN SELECT RAISE(ABORT,'only answered short scores can change'); END;
CREATE TRIGGER answer_no_delete BEFORE DELETE ON answer
BEGIN SELECT RAISE(ABORT,'answers are retained'); END;
