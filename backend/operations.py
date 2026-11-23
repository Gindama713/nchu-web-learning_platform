"""Local-only maintenance, consistent backups, verified restore and bounded cleanup.

No HTTP administration endpoint, no overwrite of an existing restore directory.
"""

import hashlib
import json
import re
import shutil
import sqlite3
import time
from contextlib import closing, contextmanager
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import click

from backend.shared.api import now, stamp
from backend.shared.db import connect, database_ready


def maintenance_path(database):
    return Path(database).resolve().with_name(Path(database).name + ".maintenance")


def in_maintenance(database):
    return maintenance_path(database).exists()


def database_paused(db):
    """Worker claim guard; active jobs may finish while new claims are paused."""
    path = db.execute("PRAGMA database_list").fetchone()[2]
    return bool(path) and in_maintenance(path)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_path(root, key):
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}", key):
        raise ValueError("Unsafe storage key")
    root = Path(root).resolve()
    path = root / key
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("Storage path escapes root")
    return path


@contextmanager
def operation_lock(database):
    path = maintenance_path(database).with_suffix(".operations-lock")
    with path.open("x", encoding="utf-8") as handle:
        handle.write(stamp())
    try:
        yield
    finally:
        path.unlink()


def check_database(path):
    if not Path(path).is_file() or Path(path).is_symlink():
        raise ValueError("Missing or unsafe database")
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Database integrity or foreign keys failed")
        files = [dict(row) for row in db.execute("SELECT storage_key,size_bytes,sha256 FROM file_object ORDER BY storage_key")]
    if not database_ready(path):
        raise ValueError("Database migrations do not match this application")
    return files


def verify_backup(directory):
    directory = Path(directory).resolve()
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("Unsafe manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != "cpu-backup-v1":
        raise ValueError("Unknown backup format")
    database = directory / "app.db"
    if sha256(database) != manifest["database_sha256"]:
        raise ValueError("Database checksum mismatch")
    files = check_database(database)
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        migrations = [list(row) for row in db.execute("SELECT version,checksum FROM schema_migration ORDER BY version")]
    if migrations != manifest["migrations"]:
        raise ValueError("Migration manifest mismatch")
    if manifest["files"] != files:
        raise ValueError("Manifest file references differ from database")
    if (directory / "uploads").is_symlink():
        raise ValueError("Unsafe upload root")
    for row in files:
        path = file_path(directory / "uploads", row["storage_key"])
        if path.stat().st_size != row["size_bytes"] or sha256(path) != row["sha256"]:
            raise ValueError("Referenced file missing or checksum mismatch")
    return manifest


def create_backup(database, uploads, destination):
    database, uploads, destination = Path(database).resolve(), Path(uploads).resolve(), Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(uploads):
        raise ValueError("Backup destination must be new and outside uploads")
    if not in_maintenance(database):
        raise ValueError("Enable maintenance before backup")
    if not database.is_file():
        raise ValueError("Database does not exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with operation_lock(database), closing(connect(database)) as lock:
        lock.execute("BEGIN IMMEDIATE")  # Drain writes; freeze DB references while copying immutable uploads.
        try:
            for table in ("grading_run", "test_suite_validation"):
                if lock.execute(f"SELECT 1 FROM {table} WHERE status='running' LIMIT 1").fetchone():
                    raise ValueError("Wait for active grading jobs before backup")
            with TemporaryDirectory(prefix=".cpu-backup-", dir=destination.parent) as temporary:
                stage = Path(temporary) / "bundle"
                (stage / "uploads").mkdir(parents=True)
                with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source, \
                        closing(sqlite3.connect(stage / "app.db")) as target:
                    source.backup(target)
                files = check_database(stage / "app.db")
                for row in files:
                    shutil.copyfile(file_path(uploads, row["storage_key"]), stage / "uploads" / row["storage_key"])
                manifest = {"format": "cpu-backup-v1", "created_at": stamp(),
                            "database_sha256": sha256(stage / "app.db"), "files": files,
                            "migrations": [list(row) for row in lock.execute(
                                "SELECT version,checksum FROM schema_migration ORDER BY version")]}
                (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                verify_backup(stage)
                stage.rename(destination)
        finally:
            lock.rollback()
    return manifest


def restore_backup(directory, destination, active_database, active_uploads):
    directory, destination = Path(directory).resolve(), Path(destination).resolve()
    active_database, active_uploads = Path(active_database).resolve(), Path(active_uploads).resolve()
    if destination.exists() or destination.is_relative_to(active_uploads) or active_database.is_relative_to(destination):
        raise ValueError("Restore only into a new directory outside live data")
    manifest = verify_backup(directory)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".cpu-restore-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "restored"
        (stage / "uploads").mkdir(parents=True)
        shutil.copyfile(directory / "app.db", stage / "app.db")
        for row in manifest["files"]:
            key = row["storage_key"]
            shutil.copyfile(file_path(directory / "uploads", key), stage / "uploads" / key)
        shutil.copyfile(directory / "manifest.json", stage / "manifest.json")
        verify_backup(stage)
        maintenance_path(stage / "app.db").touch(exist_ok=False)
        stage.rename(destination)
    return manifest


def cleanup(database, days=90, batch=1000):
    """One bounded transaction per invocation; never delete audit, grades or files."""
    if days < 90 or not 1 <= batch <= 10000:
        raise ValueError("Retention must be >=90 days; batch must be 1..10000")
    if in_maintenance(database):
        raise ValueError("Cleanup paused during maintenance")
    with closing(connect(database)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            sessions = db.execute("DELETE FROM session WHERE id IN (SELECT id FROM session WHERE expires_at<=? "
                                  "ORDER BY id LIMIT ?)", (stamp(), batch)).rowcount
            logs = db.execute("DELETE FROM access_log WHERE id IN (SELECT id FROM access_log WHERE at<? "
                              "ORDER BY id LIMIT ?)", (stamp(now() - timedelta(days=days)), batch)).rowcount
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return {"expired_sessions_deleted": sessions, "old_access_logs_deleted": logs, "retention_days": days}


def maintenance_tick(app):
    """Reuse the existing five-second scanner; no extra maintenance thread."""
    if in_maintenance(app.config["DATABASE_PATH"]):
        return
    with app.app_context():
        from backend.apis.logs import flush_access
        flush_access()
        if app.config.get("AUTO_CLEANUP") and time.monotonic() >= app.extensions.get("cleanup_due", 0):
            cleanup(app.config["DATABASE_PATH"])
            app.extensions["cleanup_due"] = time.monotonic() + 60


def register_commands(app):
    def output(action, *args):
        try:
            value = action(*args)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
            raise click.ClickException(str(error)) from error
        click.echo(json.dumps(value, ensure_ascii=False))

    @app.cli.group("maintenance")
    def maintenance_commands():
        """Pause Web API traffic and new grading claims (persisted per database)."""

    @maintenance_commands.command("on")
    def maintenance_on():
        path = maintenance_path(app.config["DATABASE_PATH"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        click.echo("Maintenance enabled; allow active jobs to drain before backup")

    @maintenance_commands.command("off")
    def maintenance_off():
        with operation_lock(app.config["DATABASE_PATH"]):
            maintenance_path(app.config["DATABASE_PATH"]).unlink(missing_ok=True)
        click.echo("Maintenance disabled")

    @maintenance_commands.command("status")
    def maintenance_status():
        click.echo(json.dumps({"maintenance": in_maintenance(app.config["DATABASE_PATH"])}))

    @app.cli.group("backup")
    def backup_commands():
        """Create/verify backups and restore into a NEW directory, never overwrite live data."""

    @backup_commands.command("create")
    @click.option("--destination", required=True, type=click.Path(path_type=Path))
    def backup_create(destination):
        output(create_backup, app.config["DATABASE_PATH"], app.config["UPLOAD_ROOT"], destination)

    @backup_commands.command("verify")
    @click.option("--directory", required=True, type=click.Path(path_type=Path))
    def backup_verify(directory):
        output(verify_backup, directory)

    @backup_commands.command("restore")
    @click.option("--directory", required=True, type=click.Path(path_type=Path))
    @click.option("--destination", required=True, type=click.Path(path_type=Path))
    def backup_restore(directory, destination):
        output(restore_backup, directory, destination, app.config["DATABASE_PATH"], app.config["UPLOAD_ROOT"])

    @app.cli.command("cleanup")
    @click.option("--retention-days", default=90, type=click.IntRange(min=90))
    @click.option("--batch-size", default=1000, type=click.IntRange(1, 10000))
    def cleanup_command(retention_days, batch_size):
        output(cleanup, app.config["DATABASE_PATH"], retention_days, batch_size)
