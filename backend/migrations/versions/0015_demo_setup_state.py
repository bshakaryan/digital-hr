"""Persist one-time synthetic demo setup checkpoints across container restarts."""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("demo_setup_state",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("demo_setup_state")
