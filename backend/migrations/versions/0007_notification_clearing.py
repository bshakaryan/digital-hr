"""Keep notification clearing across sessions without deleting history."""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("notifications", sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("notifications") as batch:
        batch.drop_column("cleared_at")
