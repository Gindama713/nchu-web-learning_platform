-- SPEC-004 备课单元：关联知识点、资源版本、题目版本与随堂测。
-- resource_version_id 暂不加外键，待 SPEC-003 资源模块落地后补齐约束。

CREATE TABLE preparation (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES course(id),
    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 100),
    scheduled_at TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','withdrawn')),
    source_id INTEGER REFERENCES preparation(id),
    published_at TEXT,
    replaces_id INTEGER REFERENCES preparation(id),
    withdrawn_at TEXT,
    withdraw_reason TEXT CHECK(withdraw_reason IS NULL OR length(trim(withdraw_reason)) BETWEEN 1 AND 500),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(replaces_id)
);
CREATE INDEX preparation_course_status ON preparation(course_id, status, id);

CREATE TABLE preparation_knowledge (
    preparation_id INTEGER NOT NULL REFERENCES preparation(id),
    knowledge_id INTEGER NOT NULL REFERENCES knowledge_point(id),
    PRIMARY KEY(preparation_id, knowledge_id)
);

CREATE TABLE preparation_resource (
    preparation_id INTEGER NOT NULL REFERENCES preparation(id),
    resource_version_id INTEGER NOT NULL,
    PRIMARY KEY(preparation_id, resource_version_id)
);

CREATE TABLE preparation_question (
    preparation_id INTEGER NOT NULL REFERENCES preparation(id),
    question_version_id INTEGER NOT NULL REFERENCES question_version(id),
    PRIMARY KEY(preparation_id, question_version_id)
);

CREATE TABLE preparation_quiz (
    preparation_id INTEGER NOT NULL REFERENCES preparation(id),
    paper_id INTEGER NOT NULL REFERENCES paper(id),
    PRIMARY KEY(preparation_id, paper_id)
);

CREATE TRIGGER preparation_published_frozen BEFORE UPDATE ON preparation
WHEN OLD.status='published' AND NOT (
    NEW.id IS OLD.id AND NEW.course_id IS OLD.course_id AND NEW.title IS OLD.title
    AND NEW.scheduled_at IS OLD.scheduled_at AND NEW.status='withdrawn'
    AND NEW.source_id IS OLD.source_id AND NEW.published_at IS OLD.published_at
    AND NEW.replaces_id IS OLD.replaces_id AND OLD.withdrawn_at IS NULL
    AND NEW.withdrawn_at IS NOT NULL AND NEW.withdraw_reason IS NOT NULL
)
BEGIN SELECT RAISE(ABORT, 'published preparation may only be withdrawn'); END;

CREATE TRIGGER preparation_withdrawn_frozen BEFORE UPDATE ON preparation
WHEN OLD.status='withdrawn' AND NOT (
    NEW.id IS OLD.id AND NEW.course_id IS OLD.course_id AND NEW.title IS OLD.title
    AND NEW.scheduled_at IS OLD.scheduled_at AND NEW.status IS OLD.status
    AND NEW.source_id IS OLD.source_id AND NEW.published_at IS OLD.published_at
    AND NEW.replaces_id IS OLD.replaces_id AND NEW.withdrawn_at IS OLD.withdrawn_at
    AND NEW.withdraw_reason IS OLD.withdraw_reason
)
BEGIN SELECT RAISE(ABORT, 'withdrawn preparation is immutable'); END;

CREATE TRIGGER preparation_knowledge_no_update BEFORE UPDATE ON preparation_knowledge
BEGIN SELECT RAISE(ABORT, 'preparation knowledge links are immutable'); END;

CREATE TRIGGER preparation_question_no_update BEFORE UPDATE ON preparation_question
BEGIN SELECT RAISE(ABORT, 'preparation question links are immutable'); END;

CREATE TRIGGER preparation_quiz_no_update BEFORE UPDATE ON preparation_quiz
BEGIN SELECT RAISE(ABORT, 'preparation quiz links are immutable'); END;

CREATE TRIGGER preparation_resource_no_update BEFORE UPDATE ON preparation_resource
BEGIN SELECT RAISE(ABORT, 'preparation resource links are immutable'); END;
