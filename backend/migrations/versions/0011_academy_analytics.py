"""Add course category, stable demo code, and assignment deadline."""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("courses") as batch:
        batch.add_column(sa.Column("category", sa.String(30), nullable=False, server_default="general"))
        batch.add_column(sa.Column("demo_code", sa.String(40), nullable=True))
        batch.create_unique_constraint("uq_course_demo_code", ["demo_code"])
    with op.batch_alter_table("course_assignments") as batch:
        batch.add_column(sa.Column("deadline", sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table("course_assignments") as batch:
        batch.drop_column("deadline")
    with op.batch_alter_table("courses") as batch:
        batch.drop_constraint("uq_course_demo_code", type_="unique")
        batch.drop_column("demo_code")
        batch.drop_column("category")
