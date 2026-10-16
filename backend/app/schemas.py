from datetime import date, datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

UTCDateTime = Annotated[datetime, AfterValidator(lambda value: value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc))]


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
    data_source: Literal["mock_zup"] = "mock_zup"


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


class HistoryOut(BaseModel):
    status: str
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
    comment: str
    status: str
    version: int
    created_at: UTCDateTime
    history: list[HistoryOut]


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    title: str
    body: str
    read: bool
    created_at: UTCDateTime


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


class Progress(Input):
    progress: int = Field(ge=0, le=100, strict=True)


class Completion(Input):
    answer_index: int = Field(ge=0, strict=True)


class Question(Input):
    question: str = Field(min_length=3, max_length=1000)


class Source(BaseModel):
    document_id: int
    title: str
    section: str
    content: str


class AssistantOut(BaseModel):
    answer: str
    sources: list[Source]
    escalate_to_hr: bool
    mode: Literal["extractive_demo"] = "extractive_demo"


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor_id: int
    action: str
    entity_type: str
    entity_id: int
    created_at: UTCDateTime
