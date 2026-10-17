from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine():
    url = get_settings().database_url
    return create_engine(url, pool_pre_ping=True)


def get_db():
    with Session(get_engine(), expire_on_commit=False) as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
