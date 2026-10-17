"""Backend DSNs must never select a second database engine implicitly."""
import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.config import Settings


SECRET = "test-settings-secret-at-least-32-characters"
BASE_SETTINGS = {"_env_file": None, "jwt_secret": SECRET, "zup_mode": "mock", "documentolog_mode": "disabled"}


def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Settings(**BASE_SETTINGS)


@pytest.mark.parametrize("value", ["", "invalid", "sqlite:///jana.db", "sqlite:///:memory:",
                                    "mysql://localhost/jana", "postgresql://localhost",
                                    "postgresql+psycopg2://localhost/jana"])
def test_other_database_urls_are_rejected(value):
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(**BASE_SETTINGS, database_url=value)


@pytest.mark.parametrize("driver", ["postgres", "postgresql", "postgresql+psycopg"])
def test_hosting_urls_use_psycopg_and_preserve_credentials_and_tls(driver):
    settings = Settings(**BASE_SETTINGS,
                        database_url=f"{driver}://jana:p%40ss%2Fword@db.example:5432/jana?sslmode=require")
    url = make_url(settings.database_url)
    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss/word"
    assert url.host == "db.example"
    assert url.database == "jana"
    assert url.query == {"sslmode": "require"}


def test_invalid_url_error_does_not_expose_credentials():
    with pytest.raises(ValidationError) as error:
        Settings(**BASE_SETTINGS, database_url="mysql://jana:private-password@host/jana")
    assert "private-password" not in str(error.value)
