-- SPEC-003 教学资源：resource / resource_version / resource_event
-- file_object 已由 001_identity_attendance.sql 创建，此处不重复建表。

CREATE TABLE resource (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES course(id),
    chapter_id INTEGER REFERENCES chapter(id),
    title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 100),
    kind TEXT NOT NULL CHECK(kind IN ('slides','video','guide','question_bank')),
    visibility TEXT NOT NULL CHECK(visibility IN ('students','teacher_only')),
    archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    -- 题库源文件永久教师可见，禁止对学生公开
    CHECK(NOT (kind = 'question_bank' AND visibility = 'students'))
);
CREATE INDEX resource_course_kind ON resource(course_id, kind);
CREATE INDEX resource_course_chapter ON resource(course_id, chapter_id);

CREATE TABLE resource_version (
    id INTEGER PRIMARY KEY,
    resource_id INTEGER NOT NULL REFERENCES resource(id),
    version INTEGER NOT NULL CHECK(version >= 1),
    file_id INTEGER NOT NULL REFERENCES file_object(id),
    change_note TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(resource_id, version)
);
CREATE INDEX resource_version_resource ON resource_version(resource_id, version);

CREATE TABLE resource_event (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES user(id),
    resource_version_id INTEGER NOT NULL REFERENCES resource_version(id),
    event_type TEXT NOT NULL CHECK(event_type IN ('view','download')),
    event_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, event_id)
);
CREATE INDEX resource_event_version_date ON resource_event(resource_version_id, created_at);
