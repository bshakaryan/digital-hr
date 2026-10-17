"""Add draft/published lifecycle and learning objectives to existing courses."""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("courses") as batch:
        batch.add_column(sa.Column("objectives", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("status", sa.String(20), nullable=False, server_default="published"))


def downgrade():
    with op.batch_alter_table("courses") as batch:
        batch.drop_column("status")
        batch.drop_column("objectives")
