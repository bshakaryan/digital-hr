"""Add source files, citable chunks and course material links without rewriting legacy KB rows."""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("knowledge_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("document_code", sa.String(40), nullable=True),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("classification", sa.String(40), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=False),
        sa.Column("access_scope", sa.String(20), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("original_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("classification IN ('synthetic_demo','external_legal_snapshot','external_reference')", name="ck_knowledge_file_classification"),
        sa.CheckConstraint("access_scope IN ('all','employee','manager','hr_admin')", name="ck_knowledge_file_scope"))
    with op.batch_alter_table("knowledge_documents") as batch:
        batch.add_column(sa.Column("file_id", sa.Integer(), sa.ForeignKey("knowledge_files.id", name="fk_knowledge_documents_file_id"), nullable=True))
        batch.add_column(sa.Column("page_number", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("chunk_index", sa.Integer(), nullable=True))
    op.create_index("ix_knowledge_documents_file_id", "knowledge_documents", ["file_id"])
    op.create_table("course_materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("file_id", sa.Integer(), sa.ForeignKey("knowledge_files.id"), nullable=False),
        sa.Column("attached_by", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("course_id", "file_id", name="uq_course_material"))


def downgrade():
    op.drop_table("course_materials")
    op.drop_index("ix_knowledge_documents_file_id", table_name="knowledge_documents")
    with op.batch_alter_table("knowledge_documents") as batch:
        batch.drop_column("chunk_index")
        batch.drop_column("page_number")
        batch.drop_column("file_id")
    op.drop_table("knowledge_files")
