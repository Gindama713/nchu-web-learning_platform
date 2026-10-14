"""SPEC-005 SQL identity and isolated DDL helper. No public migration runner.

The team's runner uses the SQL file stem as version and SHA-256 of
read_text(encoding='utf-8').encode() as checksum.
"""

from hashlib import sha256
from pathlib import Path

SQL_PATH = Path(__file__).resolve().parents[1] / "migrations" / "005_knowledge.sql"
VERSION = SQL_PATH.stem
SQL = SQL_PATH.read_text(encoding="utf-8")
CHECKSUM = sha256(SQL.encode()).hexdigest()
STATEMENTS = tuple(statement.strip() for statement in SQL.split(";") if statement.strip())


def apply(connection):
    """Test/helper DDL only; caller owns the transaction and migration ledger."""
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
