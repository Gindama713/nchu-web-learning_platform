"""SQLite readiness check. Business tables arrive with their owning modules."""

import sqlite3
from contextlib import closing
from pathlib import Path


def database_ready(path: Path) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=5)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("SELECT 1")
        return True
    except (OSError, sqlite3.Error):
        return False
