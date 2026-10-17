"""Repair sequences after explicit demo IDs. No ORM imports or row changes."""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("LOCK TABLE employees, courses, knowledge_documents IN SHARE ROW EXCLUSIVE MODE")
    for table in ("employees", "courses", "knowledge_documents"):
        op.execute(sa.text(f"""
            SELECT setval(pg_get_serial_sequence('{table}', 'id'),
                GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 1),
                         (SELECT last_value FROM {table}_id_seq)),
                (SELECT is_called FROM {table}_id_seq) OR EXISTS (SELECT 1 FROM {table}))
        """))


def downgrade():
    # Never rewind generated IDs, including when rolling back the revision marker.
    pass
