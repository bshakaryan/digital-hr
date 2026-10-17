"""The web launcher requires PostgreSQL and prepares only mock SQLite files."""
import sqlite3

import pytest

from app.web_storage import prepare_storage, verify_storage


POSTGRES_URL = "postgresql+psycopg://user:unused-test-value@example.invalid/jana"


def test_default_mock_databases_are_created_on_data_disk(tmp_path):
    env = {"DATA_DIR": str(tmp_path / "disk"), "DATABASE_URL": POSTGRES_URL}
    paths = prepare_storage(env)
    verify_storage(paths)
    assert env["DATABASE_URL"] == POSTGRES_URL
    assert {path.name for path in paths} == {"zup.sqlite3", "documentolog.sqlite3"}
    assert all(path.is_file() for path in paths)
    assert not (tmp_path / "disk/jana.sqlite3").exists()


def test_new_relative_mock_database_uses_data_disk(tmp_path, monkeypatch):
    app = tmp_path / "app"
    app.mkdir()
    monkeypatch.chdir(app)
    data = tmp_path / "disk"
    env = {"DATA_DIR": str(data), "DATABASE_URL": POSTGRES_URL,
           "ZUP_MOCK_DATABASE": "nested/source.db"}
    verify_storage(prepare_storage(env))
    assert env["ZUP_MOCK_DATABASE"] == str(data / "nested/source.db")
    assert not (app / "nested").exists()


def test_existing_relative_mock_database_is_preserved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with sqlite3.connect("existing.db") as db:
        db.execute("CREATE TABLE saved (value TEXT)")
        db.execute("INSERT INTO saved VALUES ('preserved')")
    env = {"DATA_DIR": str(tmp_path / "disk"), "DATABASE_URL": POSTGRES_URL,
           "ZUP_MOCK_DATABASE": "existing.db"}
    verify_storage(prepare_storage(env))
    assert env["ZUP_MOCK_DATABASE"] == str(tmp_path / "existing.db")
    with sqlite3.connect("existing.db") as db:
        assert db.execute("SELECT value FROM saved").fetchone() == ("preserved",)
    assert not (tmp_path / "disk/existing.db").exists()


def test_custom_mock_paths_create_parents(tmp_path):
    env = {"DATA_DIR": str(tmp_path / "disk"), "DATABASE_URL": POSTGRES_URL,
           "ZUP_MOCK_DATABASE": str(tmp_path / "zup/deep/source.db"),
           "DOCUMENTOLOG_MOCK_DATABASE": "documents/source.db"}
    verify_storage(prepare_storage(env))
    assert (tmp_path / "zup/deep/source.db").is_file()
    assert (tmp_path / "disk/documents/source.db").is_file()


@pytest.mark.parametrize("url", [None, "", "sqlite:///jana.db", "sqlite:///:memory:", "invalid"])
def test_missing_or_non_postgres_url_fails_before_creating_storage(tmp_path, url):
    env = {"DATA_DIR": str(tmp_path / "disk")}
    if url is not None:
        env["DATABASE_URL"] = url
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        prepare_storage(env)
    assert not (tmp_path / "disk").exists()
