CREATE TABLE practice_attempt (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES user(id),
    question_version_id INTEGER NOT NULL REFERENCES question_version(id),
    answer_json TEXT NOT NULL,
    answered INTEGER NOT NULL CHECK(answered IN (0,1)),
    correct INTEGER NOT NULL CHECK(correct IN (0,1)),
    score_hundredths INTEGER NOT NULL CHECK(typeof(score_hundredths)='integer' AND score_hundredths IN (0,10000)),
    created_at TEXT NOT NULL,
    CHECK(score_hundredths=correct*10000),
    CHECK(answered=1 OR (answer_json='null' AND correct=0))
);
CREATE INDEX practice_student_version ON practice_attempt(student_id,question_version_id,id);
CREATE TABLE wrong_question (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES user(id),
    question_id INTEGER NOT NULL REFERENCES question(id),
    last_attempt_type TEXT NOT NULL CHECK(last_attempt_type IN ('paper','practice')),
    last_attempt_id INTEGER NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0 CHECK(resolved IN (0,1)),
    UNIQUE(student_id,question_id)
);
CREATE INDEX wrong_question_student ON wrong_question(student_id,id);

-- Upgrade existing C03 facts, retaining the most recent actual objective error.
INSERT INTO wrong_question(student_id,question_id,last_attempt_type,last_attempt_id)
SELECT student_id,question_id,'paper',attempt_id FROM (
    SELECT a.student_id,v.question_id,a.id AS attempt_id,
        row_number() OVER (PARTITION BY a.student_id,v.question_id ORDER BY a.submitted_at DESC,a.id DESC) AS n
    FROM answer f JOIN attempt a ON a.id=f.attempt_id
    JOIN question_version v ON v.id=f.question_version_id
    WHERE f.answered=1 AND f.score_hundredths=0 AND v.type!='short'
) WHERE n=1;

CREATE TRIGGER practice_objective_guard BEFORE INSERT ON practice_attempt
WHEN NOT EXISTS (SELECT 1 FROM question_version WHERE id=NEW.question_version_id
    AND practice_available=1 AND type!='short')
BEGIN SELECT RAISE(ABORT,'practice requires public objective version'); END;
CREATE TRIGGER practice_no_update BEFORE UPDATE ON practice_attempt
BEGIN SELECT RAISE(ABORT,'practice facts are immutable'); END;
CREATE TRIGGER practice_no_delete BEFORE DELETE ON practice_attempt
BEGIN SELECT RAISE(ABORT,'practice history is retained'); END;
CREATE TRIGGER wrong_source_insert BEFORE INSERT ON wrong_question
WHEN NOT (
    (NEW.last_attempt_type='practice' AND EXISTS (
        SELECT 1 FROM practice_attempt p JOIN question_version v ON v.id=p.question_version_id
        WHERE p.id=NEW.last_attempt_id AND p.student_id=NEW.student_id AND v.question_id=NEW.question_id
            AND p.answered=1 AND p.correct=0)) OR
    (NEW.last_attempt_type='paper' AND EXISTS (
        SELECT 1 FROM answer f JOIN attempt a ON a.id=f.attempt_id
        JOIN question_version v ON v.id=f.question_version_id
        WHERE a.id=NEW.last_attempt_id AND a.student_id=NEW.student_id AND v.question_id=NEW.question_id
            AND f.answered=1 AND f.score_hundredths=0 AND v.type!='short'))
)
BEGIN SELECT RAISE(ABORT,'wrong source must be an actual objective error'); END;
CREATE TRIGGER wrong_source_update BEFORE UPDATE ON wrong_question
WHEN NEW.id IS NOT OLD.id OR NEW.student_id IS NOT OLD.student_id OR NEW.question_id IS NOT OLD.question_id
    OR NOT (
    (NEW.last_attempt_type='practice' AND EXISTS (
        SELECT 1 FROM practice_attempt p JOIN question_version v ON v.id=p.question_version_id
        WHERE p.id=NEW.last_attempt_id AND p.student_id=NEW.student_id AND v.question_id=NEW.question_id
            AND p.answered=1 AND p.correct=0)) OR
    (NEW.last_attempt_type='paper' AND EXISTS (
        SELECT 1 FROM answer f JOIN attempt a ON a.id=f.attempt_id
        JOIN question_version v ON v.id=f.question_version_id
        WHERE a.id=NEW.last_attempt_id AND a.student_id=NEW.student_id AND v.question_id=NEW.question_id
            AND f.answered=1 AND f.score_hundredths=0 AND v.type!='short'))
)
BEGIN SELECT RAISE(ABORT,'wrong identity and objective source are required'); END;
CREATE TRIGGER wrong_no_delete BEFORE DELETE ON wrong_question
BEGIN SELECT RAISE(ABORT,'wrong history is retained'); END;
