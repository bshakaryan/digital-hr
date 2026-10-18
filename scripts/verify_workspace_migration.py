"""Run inside backend: preserves every pre-existing column while applying head.

Use with no concurrent user commands or workers. Only digests/counts are printed.
"""
import hashlib
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from app.config import get_settings

engine = create_engine(get_settings().database_url)
with engine.connect() as connection:
    inspector = inspect(connection)
    primary_keys = {name: inspector.get_pk_constraint(name)["constrained_columns"] for name in inspector.get_table_names()}
    columns = {name: [column["name"] for column in inspector.get_columns(name)] for name in inspector.get_table_names() if name != "alembic_version"}


def snapshot():
    with engine.connect() as connection:
        return {name: connection.execute(text(f'SELECT {",".join(fields)} FROM {name} ORDER BY {",".join(primary_keys[name])}')).all() for name, fields in columns.items()}


before = snapshot()
config = Config("alembic.ini")
command.upgrade(config, "head")
after = snapshot()
assert before == after, "Existing table contents changed"
command.check(config)
print({"preserved_tables": len(before), "rows": sum(len(rows) for rows in before.values()), "sha256": hashlib.sha256(repr(before).encode()).hexdigest(), "preserved": True})
engine.dispose()
