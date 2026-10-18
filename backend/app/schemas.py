from datetime import date, datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

UTCDateTime = Annotated[datetime, AfterValidator(lambda value: value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc))]
RequestStatus = Literal["submitted", "manager_approved", "approved", "rejected", "withdrawn", "cancellation_requested", "cancelled"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class Profile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: Literal["employee", "manager", "hr_admin"]
    company: str
    position: str
    department: str
    manager_id: int | None
    manager_name: str | None
    hire_date: date
    leave_balance: int
    data_source: Literal["mock_zup", "zup"] = "mock_zup"


class DirectoryPerson(BaseModel):
    id: int
    full_name: str
    position: str
    department: str
    manager_id: int | None
    can_open_profile: bool
    is_demo: bool


class CalendarEmployee(BaseModel):
    id: int
    full_name: str
    department: str
    can_open_profile: bool


class CalendarAbsence(BaseModel):
    id: int
    employee_id: int
    start_date: date
    end_date: date
    status: Literal["submitted", "manager_approved", "approved", "cancellation_requested"]
    can_open_request: bool


class EmployeeCalendar(BaseModel):
    month: str
    employees: list[CalendarEmployee]
    absences: list[CalendarAbsence]


class RequestCreate(Input):
    start_date: date
    end_date: date
    comment: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("Дата окончания должна быть не раньше даты начала")
        return self


class RequestDecision(Input):
    status: Literal["approved", "rejected"]
    version: int = Field(ge=1)
    comment: str = Field(default="", max_length=2000)


class LifecycleCommand(Input):
    version: int = Field(ge=1)
    comment: str = Field(min_length=1, max_length=2000)

    @field_validator("comment")
    @classmethod
    def reason_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Укажите причину")
        return value


class RequestReplacement(RequestCreate):
    version: int = Field(ge=1)


class LeaveCalculation(BaseModel):
    start_date: date
    end_date: date
    days_count: int
    calendar_days: int
    excluded_dates: list[date]
    calendar_version: str
    available_balance: int
    balance_after: int
    sufficient_balance: bool
    source: Literal["mock_zup_http", "zup_http"] = "mock_zup_http"


class HistoryOut(BaseModel):
    status: RequestStatus
    actor_name: str
    comment: str
    created_at: UTCDateTime


class RequestOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    type: Literal["leave"] = "leave"
    start_date: date
    end_date: date
    days_count: int
    excluded_dates: list[date]
    calendar_version: str
    zup_sync_status: Literal["not_required", "pending", "synced", "error", "legacy"]
    zup_reference: str | None
    comment: str
    status: RequestStatus
    version: int
    created_at: UTCDateTime
    history: list[HistoryOut]
    calendar_days: int
    approval_route: Literal["standard", "manager_to_hr", "hr_to_manager"]
    can_review: bool = False
    cancellation_sync_status: Literal["pending", "synced", "error"] | None = None
    cancellation_reference: str | None = None
    cancellation_allowed: bool = False
    cancellation_block_reason: str | None = None


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    title: str
    body: str
    read: bool
    created_at: UTCDateTime
    entity_type: str | None = None
    entity_id: int | None = None
    actor_id: int | None = None
    actor_name: str | None = None


LearningTrack = Literal["onboarding", "development", "legacy"]


class CourseOut(BaseModel):
    id: int
    title: str
    description: str
    content: str
    duration_minutes: int
    progress: int
    completed: bool
    question: str
    options: list[str]
    objectives: str = ""
    status: Literal["draft", "published"] = "published"
    category: str = "general"
    is_demo: bool = False
    self_enrollable: bool = False
    learning_track: LearningTrack = "legacy"
    deadline: date | None = None
    learning_status: Literal["completed", "in_progress", "not_started"] = "not_started"
    overdue: bool = False


class CourseDraft(Input):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    objectives: str = Field(min_length=1, max_length=2000)
    duration_minutes: int = Field(default=10, ge=1, le=480, strict=True)
    category: Literal["general", "onboarding", "logistics", "warehouse_safety", "customer_service"] | None = None
    self_enrollable: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def nonempty(self):
        if not all((self.title.strip(), self.description.strip(), self.objectives.strip())):
            raise ValueError("Название, описание и цели обучения обязательны")
        return self


class CourseQuiz(Input):
    question: str = Field(min_length=3, max_length=500)
    options: list[str] = Field(min_length=2, max_length=4)
    correct_index: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def valid_answers(self):
        cleaned = [option.strip() for option in self.options]
        if not self.question.strip() or any(not option or len(option) > 300 for option in cleaned):
            raise ValueError("Заполните вопрос и варианты ответов (до 300 символов)")
        if len(set(cleaned)) != len(cleaned) or self.correct_index >= len(cleaned):
            raise ValueError("Варианты должны различаться; выберите существующий правильный ответ")
        return self


class CourseAssign(Input):
    employee_id: int = Field(gt=0, strict=True)
    deadline: date | None = None
    learning_track: LearningTrack = "legacy"


class CourseTrackChange(Input):
    learning_track: Literal["onboarding", "development"]


class RewardsOut(BaseModel):
    xp: int
    level: int
    next_level_xp: int
    badges: list[str]


class Progress(Input):
    progress: int = Field(ge=0, le=100, strict=True)


class Completion(Input):
    answer_index: int = Field(ge=0, strict=True)


class Question(Input):
    question: str = Field(min_length=3, max_length=1000)
    conversation_id: int | None = Field(default=None, gt=0, strict=True)
    client_turn_id: str | None = Field(default=None, min_length=1, max_length=100)


class Source(BaseModel):
    document_id: int
    title: str
    section: str
    content: str
    source_type: Literal["knowledge", "course"] = "knowledge"
    file_id: int | None = None
    source_filename: str | None = None
    page_number: int | None = None
    document_code: str | None = None
    version: str | None = None
    language: str | None = None
    classification: str | None = None
    source_note: str | None = None


class KnowledgeFileOut(BaseModel):
    id: int
    filename: str
    title: str
    document_code: str | None
    version: str
    language: str
    classification: Literal["synthetic_demo", "external_legal_snapshot", "external_reference"]
    source_note: str
    access_scope: Literal["all", "employee", "manager", "hr_admin"]
    sha256: str
    size_bytes: int
    chunk_count: int
    duplicate: bool = False


class CourseCatalogItem(BaseModel):
    id: int
    title: str
    description: str
    objectives: str = ""
    duration_minutes: int = 10
    status: Literal["draft", "published"] = "published"
    question: str = ""
    options: list[str] = Field(default_factory=list)
    correct_index: int = 0
    category: str = "general"
    is_demo: bool = False
    self_enrollable: bool = False


class PublicCourseItem(BaseModel):
    id: int
    title: str
    description: str
    objectives: str
    duration_minutes: int
    category: str
    is_demo: bool
    self_enrollable: bool = False


class LearningAssignmentOut(BaseModel):
    employee_id: int
    employee_name: str
    department: str
    course_id: int
    course_title: str
    category: str
    learning_track: LearningTrack = "legacy"
    progress: int
    deadline: date | None
    status: Literal["completed", "in_progress", "not_started"]
    overdue: bool
    completed_at: UTCDateTime | None
    last_activity_at: UTCDateTime | None


class EmployeeLearningOut(BaseModel):
    employee_id: int
    employee_name: str
    department: str
    position: str
    manager_name: str | None
    total_assigned: int
    completed: int
    in_progress: int
    not_started: int
    overdue: int
    completion_rate: float
    xp: int
    level: int
    badges: list[str]
    assignments: list[LearningAssignmentOut]


class LearningAnalyticsOut(BaseModel):
    as_of: date
    total_demo_employees: int
    published_courses: int
    total_assignments: int
    completion_rate: float
    overdue_assignments: int
    status_counts: dict[str, int]
    course_completion: list[dict]
    activity_includes_demo: bool = False
    daily_activity: list[dict]
    overdue_by_department: list[dict]
    assignments: list[LearningAssignmentOut]
    employees: list[EmployeeLearningOut]


class AttachMaterial(Input):
    file_id: int = Field(gt=0)


class AssistantOut(BaseModel):
    answer: str
    sources: list[Source]
    escalate_to_hr: bool
    mode: Literal["extractive_demo"] = "extractive_demo"
    conversation_id: int | None = None
    turn_id: int | None = None
    client_turn_id: str | None = None


class ConversationSummary(BaseModel):
    id: int
    course_id: int | None
    title: str
    created_at: UTCDateTime
    updated_at: UTCDateTime


class ConversationPage(BaseModel):
    items: list[ConversationSummary]
    total: int
    page: int
    page_size: int


class ConversationMessage(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    text: str
    sources: list[Source] = Field(default_factory=list)
    escalate_to_hr: bool | None = None
    mode: Literal["extractive_demo"] | None = None
    client_turn_id: str | None = None
    created_at: UTCDateTime


class ConversationDetail(BaseModel):
    id: int
    course_id: int | None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    messages: list[ConversationMessage]
    total_turns: int
    page: int
    page_size: int


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor_id: int
    action: str
    entity_type: str
    entity_id: int
    created_at: UTCDateTime
    actor_name: str = ""
    action_label: str = ""
    employee_id: int | None = None
    employee_name: str | None = None


class AuditPage(BaseModel):
    items: list[AuditOut]
    total: int
    page: int
    page_size: int
