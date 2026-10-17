"""Align the legacy knowledge serial sequence after seed rows with explicit IDs."""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("LOCK TABLE knowledge_documents IN ACCESS EXCLUSIVE MODE")
        op.execute("SELECT setval(pg_get_serial_sequence('knowledge_documents', 'id'), "
                   "GREATEST((SELECT COALESCE(MAX(id), 0) + 1 FROM knowledge_documents), 1), false)")


def downgrade():
    # Sequence repair is harmless to retain and cannot be meaningfully reversed.
    pass
