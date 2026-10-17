"""Prepare only the mock SQLite stores before the Docker launcher drops root."""
import os
from pathlib import Path
import sqlite3
import tempfile

from app.config import postgres_database_url


def prepare_storage(env: dict[str, str], *, owner: tuple[int, int] | None = None):
    try:
        env["DATABASE_URL"] = postgres_database_url(env.get("DATABASE_URL", ""))
    except ValueError as error:
        raise RuntimeError(str(error)) from None
    data = Path(env.get("DATA_DIR") or "/var/data").expanduser().resolve()
    env["DATA_DIR"] = str(data)
    paths = []

    def directory(path):
        missing = []
        current = path
        while not current.exists():
            missing.append(current)
            current = current.parent
        path.mkdir(parents=True, exist_ok=True)
        if owner:
            for item in reversed(missing):
                os.chown(item, *owner)
            os.chown(path, *owner)
            for parent in path.parents:
                if parent == data or data in parent.parents:
                    os.chown(parent, *owner)
                else:
                    break

    def database_path(value):
        path = Path(value).expanduser()
        if not path.is_absolute():
            # Preserve an existing explicitly configured relative database. New
            # relative files belong on the mounted data disk, not in /app/backend.
            existing = path.resolve()
            path = existing if existing.exists() else data / path
        path = path.resolve()
        directory(path.parent)
        if owner:
            for item in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm"), Path(str(path) + "-journal")):
                if item.exists():
                    os.chown(item, *owner)
        paths.append(path)
        return str(path)

    directory(data)
    for key, name in (("ZUP_MOCK_DATABASE", "zup.sqlite3"), ("DOCUMENTOLOG_MOCK_DATABASE", "documentolog.sqlite3")):
        env[key] = database_path(env.get(key) or str(data / name))
    return paths


def verify_storage(paths):
    """Check the effective unprivileged user's DB and journal-file access."""
    for path in paths:
        try:
            with tempfile.TemporaryFile(dir=path.parent):
                pass
            if path.exists() and not os.access(path, os.R_OK | os.W_OK):
                raise PermissionError("Database is not readable and writable")
            with sqlite3.connect(path) as db:
                db.execute("PRAGMA schema_version")
        except (OSError, sqlite3.Error) as error:
            raise RuntimeError(f"Mock SQLite storage is not writable: {path}. Check DATA_DIR, mock database paths and disk permissions.") from error
