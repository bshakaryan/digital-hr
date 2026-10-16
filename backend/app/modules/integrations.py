from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class EmployeeSnapshot:
    id: int
    email: str
    full_name: str
    role: str
    position: str
    department: str
    manager_id: int | None
    hire_date: date
    leave_balance: int
    company: str = "Jana Post · демо"


class HRISAdapter(Protocol):
    def employees(self) -> list[EmployeeSnapshot]: ...


class MockZupAdapter:
    def employees(self):
        return [
            EmployeeSnapshot(1, "employee@example.com", "Айдана Демо", "employee", "Координатор логистики", "Операционный отдел", 2, date(2024, 3, 15), 18),
            EmployeeSnapshot(2, "manager@example.com", "Арман Демо", "manager", "Руководитель отдела", "Операционный отдел", None, date(2022, 6, 1), 22),
            EmployeeSnapshot(3, "hr@example.com", "Алия Демо", "hr_admin", "HR-партнёр", "HR", None, date(2023, 1, 10), 24),
            EmployeeSnapshot(4, "outsider@example.com", "Данияр Демо", "employee", "Специалист поддержки", "Клиентский сервис", None, date(2025, 2, 1), 12),
        ]


class DocumentWorkflowAdapter(Protocol):
    """Future boundary. Delivery must use a stable idempotency key + outbox."""
    def submit_leave(self, request_id: int, idempotency_key: str) -> str: ...


class UnconfiguredDocumentologAdapter:
    def submit_leave(self, request_id: int, idempotency_key: str) -> str:
        raise NotImplementedError("Documentolog не подключён; заявки обрабатываются только внутри MVP")
