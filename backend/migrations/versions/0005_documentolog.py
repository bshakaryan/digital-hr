"""Persist Documentolog sessions and immutable document snapshots. No ORM imports."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("documentolog_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("leave_requests.id"), nullable=False, unique=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("command_key", sa.String(128), nullable=False, unique=True),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("file_content", sa.LargeBinary(), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("file_token", sa.String(100), nullable=False, unique=True),
        sa.Column("callback_token", sa.String(100), nullable=False, unique=True),
        sa.Column("session_url", sa.Text(), nullable=True),
        sa.Column("external_id", sa.String(100), nullable=True),
        sa.Column("view_url", sa.Text(), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("mode IN ('mock','real')", name="ck_documentolog_mode"),
        sa.CheckConstraint("status IN ('prepared','creating','signing','completed_reported','completed','declined','needs_review')", name="ck_documentolog_status"))


def downgrade():
    op.drop_table("documentolog_deliveries")
