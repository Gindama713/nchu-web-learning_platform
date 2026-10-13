"""SPEC-005 migration entry, to be called by the team's migration runner.

This module never creates SPEC-001 tables or initializes users/courses.
The caller owns BEGIN/COMMIT, backup and schema_migration bookkeeping.
"""

from hashlib import sha256

VERSION = "spec-005-001"
STATEMENTS = (
    """CREATE TABLE chapter (
        id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES course(id),
        title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 100),
        position INTEGER NOT NULL CHECK(position >= 0), UNIQUE(course_id, position)
    )""",
    """CREATE TABLE knowledge_point (
        id INTEGER PRIMARY KEY, chapter_id INTEGER NOT NULL REFERENCES chapter(id),
        title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 100),
        content TEXT NOT NULL, example TEXT NOT NULL DEFAULT '',
        published INTEGER NOT NULL CHECK(published IN (0,1)),
        content_revision INTEGER NOT NULL DEFAULT 1 CHECK(content_revision >= 1),
        is_foundational INTEGER NOT NULL DEFAULT 0 CHECK(is_foundational IN (0,1))
    )""",
    "CREATE INDEX knowledge_chapter_published ON knowledge_point(chapter_id, published)",
    """CREATE TABLE bookmark (
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES user(id),
        knowledge_id INTEGER NOT NULL REFERENCES knowledge_point(id),
        UNIQUE(user_id, knowledge_id)
    )""",
    """CREATE TABLE learning_progress (
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES user(id),
        knowledge_id INTEGER NOT NULL REFERENCES knowledge_point(id),
        completed INTEGER NOT NULL CHECK(completed IN (0,1)),
        completed_at TEXT,
        CHECK((completed=1 AND completed_at IS NOT NULL)
            OR (completed=0 AND completed_at IS NULL)), UNIQUE(user_id, knowledge_id)
    )""",
)
CHECKSUM = sha256(";\n".join(STATEMENTS).encode()).hexdigest()


def apply(connection):
    """Apply DDL inside an existing transaction; runner records VERSION/CHECKSUM."""
    if not connection.in_transaction:
        raise RuntimeError("SPEC-005 migration requires a runner-owned transaction")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("foreign_keys must be enabled before BEGIN")
    for table, columns in {
        "user": {"id", "role", "active"}, "course": {"id", "chapters_revision"},
        "course_member": {"course_id", "user_id", "member_role", "active"},
        "schema_migration": {"version", "checksum", "applied_at"},
    }.items():
        actual = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if not columns <= actual:
            raise RuntimeError(f"SPEC-001/public migration prerequisite missing: {table}")
    for statement in STATEMENTS:
        connection.execute(statement)
