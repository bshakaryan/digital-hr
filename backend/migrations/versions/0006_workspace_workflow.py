"""Workflow commands, cancellation outbox and linked notifications. No ORM imports."""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("leave_requests") as batch:
        batch.drop_constraint("ck_request_status", type_="check")
        batch.alter_column("status", existing_type=sa.String(20), type_=sa.String(30), existing_nullable=False)
        batch.create_check_constraint("ck_request_status", "status IN ('submitted','manager_approved','approved','rejected','withdrawn','cancellation_requested','cancelled')")
    with op.batch_alter_table("request_history") as batch:
        batch.alter_column("status", existing_type=sa.String(20), type_=sa.String(30), existing_nullable=False)
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("entity_type", sa.String(30), nullable=True))
        batch.add_column(sa.Column("entity_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("actor_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_notification_actor", "employees", ["actor_id"], ["id"])
    op.create_table("request_commands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("command_key", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("result_id", sa.Integer(), sa.ForeignKey("leave_requests.id"), nullable=False),
        sa.UniqueConstraint("actor_id", "command_key", name="uq_request_command"))
    op.create_table("leave_cancellations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("leave_requests.id"), nullable=False, unique=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("command_key", sa.String(128), nullable=False, unique=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('pending','synced','error')", name="ck_leave_cancellation_status"))


def downgrade():
    # Restoring the old status constraint would discard lifecycle semantics.
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT (SELECT count(*) FROM request_commands) + (SELECT count(*) FROM leave_cancellations) + (SELECT count(*) FROM request_history WHERE status IN ('withdrawn','cancellation_requested','cancelled')) + (SELECT count(*) FROM leave_requests WHERE status IN ('withdrawn','cancellation_requested','cancelled'))")).scalar():
        raise RuntimeError("Cannot downgrade while extended workflow requests exist")
    op.drop_table("leave_cancellations")
    op.drop_table("request_commands")
    with op.batch_alter_table("notifications") as batch:
        batch.drop_constraint("fk_notification_actor", type_="foreignkey")
        batch.drop_column("actor_id")
        batch.drop_column("entity_id")
        batch.drop_column("entity_type")
    with op.batch_alter_table("request_history") as batch:
        batch.alter_column("status", existing_type=sa.String(30), type_=sa.String(20), existing_nullable=False)
    with op.batch_alter_table("leave_requests") as batch:
        batch.drop_constraint("ck_request_status", type_="check")
        batch.alter_column("status", existing_type=sa.String(30), type_=sa.String(20), existing_nullable=False)
        batch.create_check_constraint("ck_request_status", "status IN ('submitted','manager_approved','approved','rejected')")
