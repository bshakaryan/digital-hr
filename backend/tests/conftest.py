"""HTTP scenarios on a fresh, migrated SQLite database for every test.

No create_all, dependency overrides, production secrets, or persistent local DBs.
App imports happen only after the test environment has been installed.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


BACKEND = Path(__file__).resolve().parents[1]
TEST_PASSWORD = "test-only-demo-password-2026"
TEST_SECRET = "test-only-jwt-secret-never-use-outside-pytest-2026"


@pytest.fixture
def database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'scenario.sqlite3'}")
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("DEMO_PASSWORD", TEST_PASSWORD)

    from app.config import get_settings
    from app.database import Base, get_engine
    from app.seed import seed

    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()
    config = Config(str(BACKEND / "alembic.ini"))
    try:
        command.upgrade(config, "head")
        seed()
        engine = get_engine()

        def snapshot(*names):
            tables = [table for table in Base.metadata.sorted_tables if not names or table.name in names]
            with engine.connect() as connection:
                return {
                    table.name: connection.execute(select(table).order_by(*table.primary_key.columns)).all()
                    for table in tables
                }

        yield SimpleNamespace(
            engine=engine,
            session=sessionmaker(engine, expire_on_commit=False),
            snapshot=snapshot,
            config=config,
            seed=seed,
            password=TEST_PASSWORD,
            secret=TEST_SECRET,
        )
    finally:
        if get_engine.cache_info().currsize:
            get_engine().dispose()
        get_engine.cache_clear()
        get_settings.cache_clear()


class Scenario:
    def __init__(self, client, database):
        self.client = client
        self.db = database
        self._headers = {}

    def headers(self, actor="employee"):
        if actor not in self._headers:
            response = self.client.post(
                "/api/auth/login",
                json={"email": f"{actor}@example.com", "password": self.db.password},
            )
            assert response.status_code == 200, response.text
            self._headers[actor] = {"Authorization": f"Bearer {response.json()['access_token']}"}
        return self._headers[actor].copy()

    def get(self, path, actor="employee"):
        return self.client.get(path, headers=self.headers(actor))

    def post(self, path, body, actor="employee", **kwargs):
        return self.client.post(path, headers=self.headers(actor), json=body, **kwargs)

    def patch(self, path, body=None, actor="employee"):
        return self.client.patch(path, headers=self.headers(actor), json=body)

    def create(self, actor="employee", key="test-leave-command", **changes):
        body = {"start_date": "2027-01-11", "end_date": "2027-01-15", "comment": "Test leave"}
        body.update(changes)
        return self.client.post(
            "/api/requests", headers={**self.headers(actor), "Idempotency-Key": key}, json=body
        )

    def leave(self, actor="employee", key="test-leave-command", **changes):
        response = self.create(actor, key, **changes)
        assert response.status_code == 201, response.text
        return response.json()

    def decide(self, item, actor="manager", status="approved", version=None):
        return self.patch(
            f"/api/requests/{item['id']}/status",
            {"status": status, "version": item["version"] if version is None else version, "comment": "Human decision"},
            actor,
        )


@pytest.fixture
def api(database):
    from app.main import app

    with TestClient(app) as client:
        yield Scenario(client, database)
