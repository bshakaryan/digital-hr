"""Persist user-owned assistant conversations and idempotent turns."""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("assistant_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_assistant_conversations_user_updated", "assistant_conversations", ["user_id", "updated_at"])
    op.create_table("assistant_turns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("assistant_conversations.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("client_turn_id", sa.String(100), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("source_refs_json", sa.Text(), nullable=False),
        sa.Column("answer_kind", sa.String(20), nullable=False, server_default="rag"),
        sa.Column("escalate_to_hr", sa.Boolean(), nullable=False),
        sa.Column("mode", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "client_turn_id", name="uq_assistant_turn_user_client_id"))
    op.create_index("ix_assistant_turns_conversation_id", "assistant_turns", ["conversation_id"])


def downgrade():
    op.drop_index("ix_assistant_turns_conversation_id", table_name="assistant_turns")
    op.drop_table("assistant_turns")
    op.drop_index("ix_assistant_conversations_user_updated", table_name="assistant_conversations")
    op.drop_table("assistant_conversations")
