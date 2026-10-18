from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (CheckConstraint("role IN ('employee','manager','hr_admin')", name="ck_employee_role"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    company: Mapped[str] = mapped_column(String(120))
    position: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(120))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    hire_date: Mapped[date] = mapped_column(Date)
    leave_balance: Mapped[int] = mapped_column(Integer)
    zup_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    manager: Mapped["Employee | None"] = relationship(remote_side=[id])

    @property
    def manager_name(self) -> str | None:
        return self.manager.full_name if self.manager else None


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        UniqueConstraint("employee_id", "idempotency_key", name="uq_request_idempotency"),
        CheckConstraint("end_date >= start_date", name="ck_request_dates"),
        CheckConstraint("status IN ('submitted','manager_approved','approved','rejected','withdrawn','cancellation_requested','cancelled')", name="ck_request_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    comment: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="submitted")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    days_count: Mapped[int] = mapped_column(Integer, default=0)
    excluded_dates_json: Mapped[str] = mapped_column(Text, default="[]")
    calendar_version: Mapped[str] = mapped_column(String(80), default="legacy-unquoted")


class LeaveDeduction(Base):
    __tablename__ = "leave_deductions"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_leave_deduction_request"),
        CheckConstraint("days > 0", name="ck_leave_deduction_days"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("leave_requests.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    days: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RequestHistory(Base):
    __tablename__ = "request_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("leave_requests.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    status: Mapped[str] = mapped_column(String(30))
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ZupDelivery(Base):
    __tablename__ = "zup_deliveries"
    __table_args__ = (CheckConstraint("status IN ('pending','synced','error')", name="ck_zup_delivery_status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("leave_requests.id"), unique=True)
    command_key: Mapped[str] = mapped_column(String(128), unique=True)
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reference: Mapped[str | None] = mapped_column(String(100))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentologDelivery(Base):
    __tablename__ = "documentolog_deliveries"
    __table_args__ = (
        CheckConstraint("mode IN ('mock','real')", name="ck_documentolog_mode"),
        CheckConstraint("status IN ('prepared','creating','signing','completed_reported','completed','declined','needs_review')", name="ck_documentolog_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("leave_requests.id"), unique=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    command_key: Mapped[str] = mapped_column(String(128), unique=True)
    mode: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(30), default="prepared")
    payload_json: Mapped[str] = mapped_column(Text)
    file_content: Mapped[bytes] = mapped_column(LargeBinary)
    file_sha256: Mapped[str] = mapped_column(String(64))
    file_token: Mapped[str] = mapped_column(String(100), unique=True)
    callback_token: Mapped[str] = mapped_column(String(100), unique=True)
    session_url: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(100))
    view_url: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LeaveCancellation(Base):
    __tablename__ = "leave_cancellations"
    __table_args__ = (CheckConstraint("status IN ('pending','synced','error')", name="ck_leave_cancellation_status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("leave_requests.id"), unique=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    command_key: Mapped[str] = mapped_column(String(128), unique=True)
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reference: Mapped[str | None] = mapped_column(String(100))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RequestCommand(Base):
    __tablename__ = "request_commands"
    __table_args__ = (UniqueConstraint("actor_id", "command_key", name="uq_request_command"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    command_key: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    result_id: Mapped[int] = mapped_column(ForeignKey("leave_requests.id"))


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    entity_type: Mapped[str | None] = mapped_column(String(30))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(String(500))
    options_json: Mapped[str] = mapped_column(Text)
    correct_index: Mapped[int] = mapped_column(Integer)
    objectives: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(String(20), default="published", server_default="published")
    category: Mapped[str] = mapped_column(String(30), default="general", server_default="general")
    self_enrollable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    demo_code: Mapped[str | None] = mapped_column(String(40), unique=True)


class CourseAssignment(Base):
    __tablename__ = "course_assignments"
    __table_args__ = (
        UniqueConstraint("employee_id", "course_id", name="uq_course_assignment"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_course_progress"),
        CheckConstraint("learning_track IN ('onboarding', 'development', 'legacy')", name="ck_course_assignment_learning_track"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    deadline: Mapped[date | None] = mapped_column(Date)
    learning_track: Mapped[str] = mapped_column(String(20), default="legacy", server_default="legacy")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    section: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text)
    keywords: Mapped[str] = mapped_column(Text)
    access_scope: Mapped[str] = mapped_column(String(20), default="all")
    file_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_files.id"), index=True)
    page_number: Mapped[int | None] = mapped_column(Integer)
    chunk_index: Mapped[int | None] = mapped_column(Integer)
    file: Mapped["KnowledgeFile | None"] = relationship()


class KnowledgeFile(Base):
    __tablename__ = "knowledge_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(200))
    document_code: Mapped[str | None] = mapped_column(String(40))
    version: Mapped[str] = mapped_column(String(80))
    language: Mapped[str] = mapped_column(String(10))
    classification: Mapped[str] = mapped_column(String(40))
    source_note: Mapped[str] = mapped_column(Text)
    access_scope: Mapped[str] = mapped_column(String(20))
    media_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    original_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CourseMaterial(Base):
    __tablename__ = "course_materials"
    __table_args__ = (UniqueConstraint("course_id", "file_id", name="uq_course_material"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    file_id: Mapped[int] = mapped_column(ForeignKey("knowledge_files.id"))
    attached_by: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"
    __table_args__ = (Index("ix_assistant_conversations_user_updated", "user_id", "updated_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssistantTurn(Base):
    __tablename__ = "assistant_turns"
    __table_args__ = (UniqueConstraint("user_id", "client_turn_id", name="uq_assistant_turn_user_client_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("assistant_conversations.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    client_turn_id: Mapped[str | None] = mapped_column(String(100))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    source_refs_json: Mapped[str] = mapped_column(Text)
    answer_kind: Mapped[str] = mapped_column(String(20), default="rag", server_default="rag")
    escalate_to_hr: Mapped[bool] = mapped_column(Boolean)
    mode: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DemoSetupState(Base):
    __tablename__ = "demo_setup_state"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
