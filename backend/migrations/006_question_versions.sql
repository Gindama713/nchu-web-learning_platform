CREATE TABLE question (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES course(id),
    archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
    ever_public INTEGER NOT NULL DEFAULT 0 CHECK(ever_public IN (0,1))
);
CREATE INDEX question_course ON question(course_id, archived);

CREATE TABLE question_version (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES question(id),
    version INTEGER NOT NULL CHECK(version >= 1),
    type TEXT NOT NULL CHECK(type IN ('single','multiple','boolean','numeric','short')),
    stem TEXT NOT NULL CHECK(length(stem) BETWEEN 1 AND 5000),
    options_json TEXT NOT NULL,
    answer_json TEXT NOT NULL,
    explanation TEXT NOT NULL DEFAULT '' CHECK(length(explanation) <= 5000),
    difficulty TEXT NOT NULL CHECK(difficulty IN ('easy','medium','hard')),
    tolerance REAL NOT NULL DEFAULT 0 CHECK(tolerance >= 0),
    practice_available INTEGER NOT NULL DEFAULT 0 CHECK(practice_available IN (0,1)),
    UNIQUE(question_id, version),
    UNIQUE(id, question_id)
);
CREATE TABLE question_knowledge (
    question_version_id INTEGER NOT NULL REFERENCES question_version(id),
    knowledge_id INTEGER NOT NULL REFERENCES knowledge_point(id),
    PRIMARY KEY(question_version_id, knowledge_id)
);
CREATE INDEX question_knowledge_lookup ON question_knowledge(knowledge_id, question_version_id);

CREATE TRIGGER question_version_no_update BEFORE UPDATE ON question_version
BEGIN SELECT RAISE(ABORT, 'question versions are immutable'); END;
CREATE TRIGGER question_version_no_delete BEFORE DELETE ON question_version
BEGIN SELECT RAISE(ABORT, 'question versions are retained'); END;
CREATE TRIGGER question_knowledge_no_update BEFORE UPDATE ON question_knowledge
BEGIN SELECT RAISE(ABORT, 'version knowledge links are immutable'); END;
CREATE TRIGGER question_knowledge_no_delete BEFORE DELETE ON question_knowledge
BEGIN SELECT RAISE(ABORT, 'version knowledge links are retained'); END;
CREATE TRIGGER question_public_history BEFORE UPDATE OF ever_public ON question
WHEN OLD.ever_public = 1 AND NEW.ever_public != 1
BEGIN SELECT RAISE(ABORT, 'public history cannot be cleared'); END;
