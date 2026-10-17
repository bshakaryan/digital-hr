"""Single-host storage paths must survive host settings and container UID changes."""
import sqlite3

import pytest

from app.web_storage import prepare_storage, verify_storage


def test_default_databases_are_created_on_data_disk(tmp_path):
    env = {"DATA_DIR": str(tmp_path / "disk")}
    paths = prepare_storage(env)
    verify_storage(paths)
    assert env["DATABASE_URL"] == f"sqlite:///{tmp_path}/disk/jana.sqlite3"
    assert {path.name for path in paths} == {"jana.sqlite3", "zup.sqlite3", "documentolog.sqlite3"}
    assert all(path.is_file() for path in paths)


def test_new_relative_database_uses_data_disk_and_nested_parents(tmp_path, monkeypatch):
    app = tmp_path / "app"
    app.mkdir()
    monkeypatch.chdir(app)
    data = tmp_path / "disk"
    env = {"DATA_DIR": str(data), "DATABASE_URL": "sqlite:///./nested/jana.db"}
    paths = prepare_storage(env)
    verify_storage(paths)
    assert env["DATABASE_URL"] == f"sqlite:///{data}/nested/jana.db"
    assert (data / "nested/jana.db").is_file()
    assert not (app / "nested").exists()


def test_existing_relative_database_is_preserved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with sqlite3.connect("existing.db") as db:
        db.execute("CREATE TABLE saved (value TEXT)")
        db.execute("INSERT INTO saved VALUES ('preserved')")
    env = {"DATA_DIR": str(tmp_path / "disk"), "DATABASE_URL": "sqlite:///existing.db"}
    verify_storage(prepare_storage(env))
    assert env["DATABASE_URL"] == f"sqlite:///{tmp_path}/existing.db"
    with sqlite3.connect("existing.db") as db:
        assert db.execute("SELECT value FROM saved").fetchone() == ("preserved",)
    assert not (tmp_path / "disk/existing.db").exists()


def test_absolute_database_and_custom_mock_paths_create_parents(tmp_path):
    target = tmp_path / "custom/deep/jana.db"
    env = {"DATA_DIR": str(tmp_path / "disk"), "DATABASE_URL": f"sqlite:///{target}",
           "ZUP_MOCK_DATABASE": str(tmp_path / "zup/deep/source.db"),
           "DOCUMENTOLOG_MOCK_DATABASE": "documents/source.db"}
    verify_storage(prepare_storage(env))
    assert env["DATABASE_URL"] == f"sqlite:///{target}"
    assert target.is_file()
    assert (tmp_path / "zup/deep/source.db").is_file()
    assert (tmp_path / "disk/documents/source.db").is_file()


def test_postgres_url_is_not_redirected_to_sqlite(tmp_path):
    url = "postgresql+psycopg://user:unused-test-value@example.invalid/jana"
    env = {"DATA_DIR": str(tmp_path), "DATABASE_URL": url}
    verify_storage(prepare_storage(env))
    assert env["DATABASE_URL"] == url
    assert not (tmp_path / "jana.sqlite3").exists()


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///:memory:", "sqlite:///file:db?uri=true"])
def test_process_local_memory_or_uri_database_is_rejected(tmp_path, url):
    with pytest.raises(RuntimeError, match="ordinary SQLite file URL"):
        prepare_storage({"DATA_DIR": str(tmp_path), "DATABASE_URL": url})
