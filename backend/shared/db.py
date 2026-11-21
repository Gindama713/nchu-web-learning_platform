"""SQLite connections and checksum-verified migrations."""

import hashlib
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, g

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"

# 全班同时点签到实测：一次有效签到要写 attendance_record + audit 两行，回滚日志模式下
# 每次 commit 都要 fsync，单个事务约 40ms。160 个人同一瞬间点，排队总时长约 6.4 秒，
# 超过 sqlite 的 5 秒 busy_timeout 就会成批报 "database is locked" → 503 DB_BUSY
# （实测 100 人 6 个失败、160 人 80 个失败）。抢锁失败时事务还没开，重试是安全的，
# 所以这里把「等锁」从 sqlite 内部挪到 Python 层，给足总预算，宁可慢几秒也不要失败。
WRITE_BUSY_SECONDS = 25.0
WRITE_BUSY_RETRY = 0.05


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    return db


def _begin_immediate(db):
    """抢写锁；BUSY 就重试，直到 WRITE_BUSY_SECONDS 用完。

    只在抢锁这一小段把 busy_timeout 压到 200ms：否则每次抢不到都先干等满 5 秒
    才轮到我们的重试，160 人同时点时最后几个要等 10 秒以上。200ms 一轮、轮着来，
    总时长不变但排队更均匀。读请求的 5 秒窗口不受影响（下面 finally 会还原）。
    """
    deadline = time.monotonic() + WRITE_BUSY_SECONDS
    db.execute("PRAGMA busy_timeout = 200")
    try:
        while True:
            try:
                db.execute("BEGIN IMMEDIATE")
                return
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                if "locked" not in message and "busy" not in message:
                    raise
                if time.monotonic() >= deadline:
                    raise
                time.sleep(WRITE_BUSY_RETRY)
    finally:
        db.execute("PRAGMA busy_timeout = 5000")


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def write(db=None):
    db = db or get_db()
    _begin_immediate(db)
    try:
        if getattr(g, "session_id", None) and getattr(g, "user", None):
            row = db.execute("SELECT u.active,u.role,u.session_version,s.session_version AS saved_version "
                             "FROM session s JOIN user u ON u.id=s.user_id WHERE s.id=? AND u.id=?",
                             (g.session_id, g.user["id"])).fetchone()
            if not row or not row["active"] or row["role"] != g.user["role"] or row["session_version"] != row["saved_version"]:
                from backend.shared.api import ApiError

                raise ApiError(401, "UNAUTHENTICATED", "Session revoked")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise


def _legacy_class_seat(db):
    table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='class_seat'").fetchone()
    if not table:
        return False
    columns = {row["name"] for row in db.execute("PRAGMA table_info(class_seat)")}
    return "class_name" not in columns


def _preserve_legacy_seats(sql):
    """021 drops 020's class_seat; carry existing rows into its new table."""
    return ("CREATE TABLE class_seat_pre021 AS SELECT * FROM class_seat;\n" + sql +
            "\nINSERT INTO class_seat(id,course_id,student_id,class_name,group_no,seat_no,created_at,updated_at) "
            "SELECT b.id,b.course_id,b.student_id,"
            "COALESCE(NULLIF(TRIM(u.class_name),''),'未分班'),"
            "b.group_no,b.seat_no,b.created_at,b.updated_at "
            "FROM class_seat_pre021 b JOIN user u ON u.id=b.student_id;\n"
            "DROP TABLE class_seat_pre021;\n")


def migrate(path):
    db = connect(path)
    try:
        db.execute("CREATE TABLE IF NOT EXISTS schema_migration "
                   "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL, checksum TEXT NOT NULL)")
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            sql = migration.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            existing = db.execute("SELECT checksum FROM schema_migration WHERE version=?", (migration.stem,)).fetchone()
            if existing:
                if existing["checksum"] != checksum:
                    raise RuntimeError(f"Migration changed after application: {migration.name}")
                continue
            if migration.stem == "021_week10_seat_class" and _legacy_class_seat(db):
                sql = _preserve_legacy_seats(sql)
            if migration.stem == "019_wiring_retries":
                # SQLite cannot drop the old UNIQUE table while child FKs are enabled.
                # Disable only on this dedicated migration connection, validate before commit.
                db.execute("PRAGMA foreign_keys=OFF")
                try:
                    db.executescript("BEGIN IMMEDIATE;\n" + sql)
                    if db.execute("PRAGMA foreign_key_check").fetchall():
                        raise RuntimeError("Wiring retry migration breaks foreign keys")
                    db.execute("INSERT INTO schema_migration(version,applied_at,checksum) "
                               "VALUES(?,strftime('%Y-%m-%dT%H:%M:%fZ','now'),?)",
                               (migration.stem, checksum))
                    db.commit()
                except BaseException:
                    db.rollback()
                    raise
                finally:
                    db.execute("PRAGMA foreign_keys=ON")
            else:
                # executescript commits first, so put the migration and ledger in one script transaction.
                db.executescript("BEGIN IMMEDIATE;\n" + sql + "\nINSERT INTO schema_migration "
                                 "(version,applied_at,checksum) VALUES "
                                 f"('{migration.stem}',strftime('%Y-%m-%dT%H:%M:%fZ','now'),'{checksum}');\nCOMMIT;")
    finally:
        db.close()


def database_ready(path):
    try:
        db = connect(path)
        try:
            applied = {row["version"]: row["checksum"] for row in db.execute(
                "SELECT version,checksum FROM schema_migration")}
            return bool(applied) and all(applied.get(file.stem) == hashlib.sha256(
                file.read_text(encoding="utf-8").encode()).hexdigest() for file in MIGRATIONS.glob("*.sql"))
        finally:
            db.close()
    except (OSError, sqlite3.Error):
        return False
