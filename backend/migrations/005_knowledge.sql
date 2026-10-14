CREATE TABLE chapter (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES course(id),
    title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 100),
    position INTEGER NOT NULL CHECK(position >= 0),
    UNIQUE(course_id, position)
);

CREATE TABLE knowledge_point (
    id INTEGER PRIMARY KEY,
    chapter_id INTEGER NOT NULL REFERENCES chapter(id),
    title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 100),
    content TEXT NOT NULL,
    example TEXT NOT NULL DEFAULT '',
    published INTEGER NOT NULL CHECK(published IN (0,1)),
    content_revision INTEGER NOT NULL DEFAULT 1 CHECK(content_revision >= 1),
    is_foundational INTEGER NOT NULL DEFAULT 0 CHECK(is_foundational IN (0,1))
);
CREATE INDEX knowledge_chapter_published ON knowledge_point(chapter_id, published);

CREATE TABLE bookmark (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES user(id),
    knowledge_id INTEGER NOT NULL REFERENCES knowledge_point(id),
    UNIQUE(user_id, knowledge_id)
);

CREATE TABLE learning_progress (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES user(id),
    knowledge_id INTEGER NOT NULL REFERENCES knowledge_point(id),
    completed INTEGER NOT NULL CHECK(completed IN (0,1)),
    completed_at TEXT,
    CHECK((completed=1 AND completed_at IS NOT NULL)
        OR (completed=0 AND completed_at IS NULL)),
    UNIQUE(user_id, knowledge_id)
);
