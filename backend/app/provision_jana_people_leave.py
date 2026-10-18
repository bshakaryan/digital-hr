"""Explicit, idempotent mock leave scenarios for the synthetic Jana People directory.

Run after ``app.provision_jana_people``. Dates follow the current month; the
existing request and decision services perform every business transition.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.models import Employee, LeaveRequest
from app.modules.requests import create_request, decide
from app.schemas import RequestCreate, RequestDecision
from app.zup_calendar import SUPPORTED_YEARS


@dataclass(frozen=True)
class DemoLeave:
    zup_id: str
    status: str
    month_offset: int
    day: int
    code: str | None = None


# Seven final approvals make every department visible in the current calendar.
# Other stages demonstrate the distinct owner, manager and HR views.
PLAN = (
    DemoLeave("people-002", "approved", 0, 3),
    DemoLeave("people-009", "approved", 0, 6),
    DemoLeave("people-014", "approved", 0, 9),
    DemoLeave("people-020", "approved", 0, 12),
    DemoLeave("people-023", "approved", 0, 15),
    DemoLeave("people-026", "approved", 0, 18),
    DemoLeave("people-029", "approved", 0, 21),
    DemoLeave("people-010", "submitted", 0, 24),
    DemoLeave("people-016", "manager_approved", 0, 25),
    DemoLeave("people-021", "submitted", 0, 26),
    DemoLeave("people-003", "manager_approved", 1, 3),
    DemoLeave("people-017", "rejected", 1, 6),
    DemoLeave("people-024", "rejected", 1, 9),
    DemoLeave("people-027", "submitted", 1, 12),
    DemoLeave("people-030", "manager_approved", 1, 15),
)

# These are the first visible rows in the shared calendar. The two core demo
# accounts without manager_id (HR and customer service) cannot submit through
# the authorized workflow, so no reviewer relationship is invented for them.
VISIBLE_PLAN = (
    DemoLeave("demo-1", "approved", 0, 7, "visible-approved-a"),
    DemoLeave("demo-1", "approved", 0, 19, "visible-approved-b"),
    DemoLeave("demo-1", "submitted", 0, 13, "visible-submitted"),
    DemoLeave("demo-1", "rejected", 0, 24, "visible-rejected"),
    DemoLeave("demo-2", "approved", 0, 4, "visible-approved-a"),
    DemoLeave("demo-2", "approved", 0, 16, "visible-approved-b"),
    DemoLeave("demo-2", "manager_approved", 0, 24, "visible-pending-hr"),
    DemoLeave("demo-2", "rejected", 0, 10, "visible-rejected"),
    DemoLeave("people-001", "approved", 0, 8, "visible-approved-a"),
    DemoLeave("people-001", "approved", 0, 22, "visible-approved-b"),
    DemoLeave("people-001", "manager_approved", 0, 25, "visible-pending-hr"),
    DemoLeave("people-002", "approved", 0, 13, "visible-approved-a"),
    DemoLeave("people-002", "approved", 0, 23, "visible-approved-b"),
    DemoLeave("people-003", "approved", 0, 11, "visible-approved-a"),
    DemoLeave("people-003", "approved", 0, 28, "visible-approved-b"),
)
ALL_PLAN = PLAN + VISIBLE_PLAN


def next_month(first: date) -> date:
    return (first.replace(day=28) + timedelta(days=4)).replace(day=1)


def provision(db: Session, *, as_of: date | None = None) -> dict:
    if get_settings().zup_mode != "mock":
        raise RuntimeError("Synthetic leave provisioning requires ZUP_MODE=mock")
    today = as_of or datetime.now(ZoneInfo("Asia/Qyzylorda")).date()
    months = (today.replace(day=1), next_month(today.replace(day=1)))
    if any(month.year not in SUPPORTED_YEARS for month in months):
        raise RuntimeError("Current and following month must be supported by the mock ZUP calendar")

    ids = {spec.zup_id for spec in ALL_PLAN}
    people = {person.zup_id: person for person in db.scalars(select(Employee).where(Employee.zup_id.in_(ids))).all()}
    hr = db.scalar(select(Employee).where(Employee.zup_id == "demo-3", Employee.role == "hr_admin"))
    if len(people) != len(ids) or hr is None:
        raise RuntimeError("Provision Jana People and the demo HR identity before leave scenarios")

    prepared = []
    skipped_overlaps = []
    planned_periods = {}
    for spec in ALL_PLAN:
        owner = people[spec.zup_id]
        if owner.zup_id != spec.zup_id or owner.role not in ("employee", "manager"):
            raise RuntimeError(f"Synthetic leave author has changed: {spec.zup_id}")
        manager = db.get(Employee, owner.manager_id) if owner.manager_id is not None else None
        if owner.role == "employee" and (manager is None or manager.role != "manager"):
            raise RuntimeError(f"No authorized reporting manager: {spec.zup_id}")
        if owner.role == "manager" and hr.id == owner.id:
            raise RuntimeError(f"No independent HR reviewer: {spec.zup_id}")
        start = months[spec.month_offset].replace(day=spec.day)
        end = start + timedelta(days=2)
        if end.month != start.month:
            raise RuntimeError(f"Demo leave crosses the calendar month: {spec.zup_id}")
        if any(start <= prior_end and end >= prior_start for prior_start, prior_end in planned_periods.get(owner.id, ())):
            raise RuntimeError(f"Demo leave periods overlap for {spec.zup_id}")
        planned_periods.setdefault(owner.id, []).append((start, end))
        key = f"jana-people-leave-v1-{months[0]:%Y-%m}-{spec.zup_id}"
        if spec.code:
            key += f"-{spec.code}"
        existing = db.scalar(select(LeaveRequest).where(LeaveRequest.employee_id == owner.id,
            LeaveRequest.idempotency_key == key))
        if existing is not None:
            if (existing.start_date, existing.end_date) != (start, end):
                raise RuntimeError(f"Demo request key has conflicting dates: {spec.zup_id}")
            prepared.append((spec, owner, manager, start, end, key, True))
            continue
        overlap = db.scalar(select(LeaveRequest.id).where(LeaveRequest.employee_id == owner.id,
            LeaveRequest.status.in_(("submitted", "manager_approved", "approved", "cancellation_requested")),
            LeaveRequest.start_date <= end, LeaveRequest.end_date >= start).order_by(LeaveRequest.id).limit(1))
        if overlap is not None:
            skipped_overlaps.append({"zup_id": spec.zup_id, "start_date": start.isoformat(),
                "end_date": end.isoformat(), "existing_request_id": overlap})
            continue
        prepared.append((spec, owner, manager, start, end, key, False))

    keys = [row[5] for row in prepared]
    if len(set(keys)) != len(keys):
        raise RuntimeError("Duplicate synthetic leave command keys")

    created = 0
    for spec, owner, manager, start, end, key, exists in prepared:
        if exists:
            continue
        item = create_request(RequestCreate(start_date=start, end_date=end,
            comment="DEMO / SYNTHETIC · Учебная заявка на отпуск"), key, owner, db)
        created += 1
        if item.status == "submitted" and spec.status in ("manager_approved", "approved", "rejected"):
            reviewer = hr if owner.role == "manager" else manager
            decision = "rejected" if spec.status == "rejected" else "approved"
            item = decide(item.id, RequestDecision(status=decision, version=item.version,
                comment="DEMO / SYNTHETIC · Решение согласующего"), reviewer, db)
        if spec.status == "approved" and item.status == "manager_approved":
            item = decide(item.id, RequestDecision(status="approved", version=item.version,
                comment="DEMO / SYNTHETIC · Финальное решение HR"), hr, db)
        if spec.status == "rejected" and item.status == "manager_approved":
            item = decide(item.id, RequestDecision(status="rejected", version=item.version,
                comment="DEMO / SYNTHETIC · Решение HR"), hr, db)
        if item.status != spec.status:
            raise RuntimeError(f"Unexpected workflow state for {spec.zup_id}: {item.status}")

    rows = db.execute(select(LeaveRequest.status, Employee.department).join(Employee,
        Employee.id == LeaveRequest.employee_id).where(LeaveRequest.idempotency_key.in_(keys))).all()
    return {"month": months[0].strftime("%Y-%m"), "created": created,
        "requests": len(rows), "by_status": {status: sum(row.status == status for row in rows)
            for status in ("approved", "submitted", "manager_approved", "rejected")},
        "departments": len({row.department for row in rows}), "skipped_overlaps": skipped_overlaps}


def main() -> None:
    with Session(get_engine()) as db:
        result = provision(db)
    print(result)


if __name__ == "__main__":
    main()
