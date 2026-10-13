CREATE TABLE paper (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES course(id),
    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 100),
    kind TEXT NOT NULL CHECK(kind IN ('homework','exam','quiz')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published')),
    confidential INTEGER NOT NULL CHECK(confidential IN (0,1)),
    confidentiality_note TEXT,
    start_at TEXT,
    end_at TEXT,
    review_at TEXT,
    seed INTEGER,
    algorithm_version TEXT,
    CHECK(status='draft' OR (start_at IS NOT NULL AND end_at IS NOT NULL AND start_at<end_at
        AND ((kind='quiz' AND review_at IS NULL) OR (review_at IS NOT NULL AND end_at<=review_at)))),
    CHECK(status='draft' OR confidential=0 OR (confidentiality_note IS NOT NULL
        AND length(trim(confidentiality_note)) BETWEEN 1 AND 1000))
);
CREATE INDEX paper_course ON paper(course_id,status,kind,id);
CREATE TABLE paper_item (
    paper_id INTEGER NOT NULL REFERENCES paper(id),
    question_version_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL REFERENCES question(id),
    position INTEGER NOT NULL CHECK(typeof(position)='integer' AND position>0),
    points_hundredths INTEGER NOT NULL CHECK(typeof(points_hundredths)='integer' AND points_hundredths>0),
    PRIMARY KEY(paper_id,question_id),
    UNIQUE(paper_id,position),
    FOREIGN KEY(question_version_id,question_id) REFERENCES question_version(id,question_id)
);
CREATE INDEX paper_item_question ON paper_item(question_id,paper_id);
CREATE TABLE paper_participant (
    paper_id INTEGER NOT NULL REFERENCES paper(id),
    student_id INTEGER NOT NULL REFERENCES user(id),
    PRIMARY KEY(paper_id,student_id)
);
CREATE INDEX paper_participant_student ON paper_participant(student_id,paper_id);

CREATE TRIGGER paper_no_delete BEFORE DELETE ON paper
BEGIN SELECT RAISE(ABORT,'papers are retained'); END;
CREATE TRIGGER paper_published_frozen BEFORE UPDATE ON paper
WHEN OLD.status='published' AND NOT (
    OLD.kind='quiz' AND OLD.review_at IS NULL AND NEW.review_at IS NOT NULL AND NEW.review_at>=OLD.end_at
    AND NEW.id IS OLD.id AND NEW.course_id IS OLD.course_id AND NEW.title IS OLD.title
    AND NEW.kind IS OLD.kind AND NEW.status IS OLD.status AND NEW.confidential IS OLD.confidential
    AND NEW.confidentiality_note IS OLD.confidentiality_note AND NEW.start_at IS OLD.start_at
    AND NEW.end_at IS OLD.end_at AND NEW.seed IS OLD.seed AND NEW.algorithm_version IS OLD.algorithm_version
)
BEGIN SELECT RAISE(ABORT,'published papers are frozen'); END;
CREATE TRIGGER paper_item_insert_guard BEFORE INSERT ON paper_item
WHEN (SELECT status FROM paper WHERE id=NEW.paper_id)!='draft'
    OR (SELECT course_id FROM question WHERE id=NEW.question_id)!=(SELECT course_id FROM paper WHERE id=NEW.paper_id)
BEGIN SELECT RAISE(ABORT,'paper items require same course draft'); END;
CREATE TRIGGER paper_item_update_guard BEFORE UPDATE ON paper_item
WHEN (SELECT status FROM paper WHERE id=OLD.paper_id)!='draft'
    OR (SELECT status FROM paper WHERE id=NEW.paper_id)!='draft'
    OR (SELECT course_id FROM question WHERE id=NEW.question_id)!=(SELECT course_id FROM paper WHERE id=NEW.paper_id)
BEGIN SELECT RAISE(ABORT,'paper items require same course draft'); END;
CREATE TRIGGER paper_item_delete_guard BEFORE DELETE ON paper_item
WHEN (SELECT status FROM paper WHERE id=OLD.paper_id)!='draft'
BEGIN SELECT RAISE(ABORT,'published paper items are frozen'); END;
CREATE TRIGGER paper_participant_insert_guard BEFORE INSERT ON paper_participant
WHEN (SELECT status FROM paper WHERE id=NEW.paper_id)!='draft' OR NOT EXISTS (
    SELECT 1 FROM course_member m JOIN user u ON u.id=m.user_id JOIN paper p ON p.course_id=m.course_id
    WHERE p.id=NEW.paper_id AND m.user_id=NEW.student_id AND m.active=1
        AND m.member_role='student' AND u.role='student' AND u.active=1)
BEGIN SELECT RAISE(ABORT,'participants require active students in draft course'); END;
CREATE TRIGGER paper_participant_no_update BEFORE UPDATE ON paper_participant
BEGIN SELECT RAISE(ABORT,'participants are immutable'); END;
CREATE TRIGGER paper_participant_no_delete BEFORE DELETE ON paper_participant
BEGIN SELECT RAISE(ABORT,'participants are retained'); END;
