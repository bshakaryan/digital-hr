"""Add explicit Academy assignment tracks and optional self-enrollment."""

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("courses", sa.Column("self_enrollable", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("course_assignments", sa.Column("learning_track", sa.String(20), nullable=False, server_default="legacy"))
    op.create_check_constraint("ck_course_assignment_learning_track", "course_assignments",
        "learning_track IN ('onboarding', 'development', 'legacy')")


def downgrade():
    op.drop_constraint("ck_course_assignment_learning_track", "course_assignments", type_="check")
    op.drop_column("course_assignments", "learning_track")
    op.drop_column("courses", "self_enrollable")
