"""Operator-requested synthetic demo setup, run before API/worker startup.

Only exact mock identities and a local mock ZUP store are accepted. Checkpoints
live in PostgreSQL; a restart restores the source baseline, never grants 25 again.
"""
import hashlib
import json
import os
import sqlite3
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.models import (AuditEvent, Course, CourseAssignment, DemoSetupState, Employee,
                        LeaveCancellation, LeaveRequest, Notification, RequestHistory, ZupDelivery, utcnow)
from app.mock_zup import CancellationInput, DocumentInput
from app.modules.audit import record
from app.modules.integrations import DemoZupFixtures
from app.modules.leave_balance import available_leave_balance
from app.modules.academy_analytics import reference_date
from app.modules.zup_sync import deliver_cancellation
from app.provision_jana_people_leave import ALL_PLAN, DemoLeave, provision as provision_leave

# Longer, staggered periods complement the short breaks in the existing plan.
EXTRA_PLAN = tuple(DemoLeave(zup_id, "approved", offset, day, "workspace-week", duration)
    for zup_id, offset, day, duration in (
        ("people-004", 0, 5, 7), ("people-005", 1, 9, 5),
        ("people-006", 0, 19, 7), ("people-007", 1, 2, 10),
        ("people-008", 0, 12, 5), ("people-011", 0, 5, 7),
        ("people-012", 1, 16, 7), ("people-013", 0, 19, 10),
        ("people-015", 1, 9, 5), ("people-018", 0, 12, 7),
        ("people-019", 1, 16, 5), ("people-022", 0, 5, 7),
        ("people-025", 1, 2, 7), ("people-028", 0, 19, 5)))


def checkpoint(db, key, value):
    db.add(DemoSetupState(key=key, value_json=json.dumps(value)))
    db.commit()


def restore_source(db, source, people):
    """Rebuild only confirmed mock receipts from PostgreSQL after Free restart."""
    ids = {person.id for person in people}
    for delivery in db.scalars(select(ZupDelivery).join(LeaveRequest,
            LeaveRequest.id == ZupDelivery.request_id).where(
                LeaveRequest.employee_id.in_(ids), ZupDelivery.status == "synced")):
        body = DocumentInput.model_validate_json(delivery.payload_json)
        source.execute("INSERT OR IGNORE INTO documents VALUES (?,?,?,?,?,?,?)", (
            delivery.command_key, hashlib.sha256(body.model_dump_json().encode()).hexdigest(),
            body.employee_id, body.days_count, delivery.reference,
            body.start_date.isoformat(), body.end_date.isoformat()))
    for cancellation in db.scalars(select(LeaveCancellation).join(LeaveRequest,
            LeaveRequest.id == LeaveCancellation.request_id).where(
                LeaveRequest.employee_id.in_(ids), LeaveCancellation.status == "synced")):
        body = CancellationInput.model_validate_json(cancellation.payload_json)
        source.execute("INSERT OR IGNORE INTO cancellations VALUES (?,?,?,?)", (
            cancellation.command_key, hashlib.sha256(body.model_dump_json().encode()).hexdigest(),
            body.original_command_key, cancellation.reference))
    source.commit()


def clear_manual_calendar(db, employee, hr):
    """One-time operator reset of Aidana's active demo absences, with history."""
    changed = []
    for item in db.scalars(select(LeaveRequest).where(LeaveRequest.employee_id == employee.id,
            LeaveRequest.status.in_(("submitted", "manager_approved", "approved", "cancellation_requested")))):
        item.status = "cancelled" if item.status in ("approved", "cancellation_requested") else "withdrawn"
        item.version += 1
        db.add(RequestHistory(request_id=item.id, actor_id=hr.id, status=item.status,
            comment="DEMO / SYNTHETIC · Календарь освобождён оператором для ручной демонстрации"))
        record(db, hr.id, "demo.request_cleared", "request", item.id)
        delivery = db.scalar(select(ZupDelivery).where(ZupDelivery.request_id == item.id))
        if delivery and db.scalar(select(LeaveCancellation).where(LeaveCancellation.request_id == item.id)) is None:
            db.add(LeaveCancellation(request_id=item.id, actor_id=hr.id,
                command_key=f"demo-workspace-clear-{item.id}", payload_json=json.dumps({
                    "employee_id": employee.zup_id, "original_command_key": delivery.command_key})))
        changed.append(item.id)
    db.commit()
    for request_id in changed:
        deliver_cancellation(db, request_id)
    for notification in db.scalars(select(Notification).where(Notification.entity_type == "request",
            Notification.entity_id.in_(changed))):
        notification.read, notification.cleared_at = True, utcnow()
    checkpoint(db, "workspace-v1-aidana-cleared", changed)
    return changed


def learning_activity(db, people):
    """Explicitly modeled history: never edit timestamps of real audit events."""
    if db.get(DemoSetupState, "workspace-v1-activity"):
        return 0
    as_of = reference_date()
    rows = db.execute(select(CourseAssignment, Course).join(Course,
        Course.id == CourseAssignment.course_id).where(
            CourseAssignment.employee_id.in_([p.id for p in people]),
            Course.demo_code.is_not(None), CourseAssignment.progress > 0)
        .order_by(CourseAssignment.employee_id, Course.id)).all()
    count = 0
    for index, (assignment, course) in enumerate(rows):
        # Three modeled sessions per active course, staggered over the window.
        final_day = 7 + index % 7
        offsets = (index % 4, 4 + index % 3, final_day)
        for step, offset in enumerate(offsets):
            day = as_of - timedelta(days=13 - offset)
            action = "demo.course.completed" if step == 2 and assignment.completed else "demo.course.progressed"
            db.add(AuditEvent(actor_id=assignment.employee_id, action=action, entity_type="course",
                entity_id=course.id, created_at=datetime.combine(day, time(8 + index % 8, 10 + step * 15), timezone.utc)))
            count += 1
    checkpoint(db, "workspace-v1-activity", {"as_of": as_of.isoformat(), "events": count})
    return count


def provision(db: Session, mock_path: str, *, as_of=None):
    if get_settings().zup_mode != "mock":
        raise RuntimeError("Workspace setup requires ZUP_MODE=mock")
    if not Path(mock_path).is_file():
        raise RuntimeError("Existing local mock ZUP database required")
    fixtures = {p.zup_id: p for p in DemoZupFixtures().employees()}
    people = db.scalars(select(Employee).where(Employee.zup_id.in_(fixtures)).order_by(Employee.id)).all()
    if len(people) != len(fixtures) or any(
        (p.email, p.full_name, p.role) != (fixtures[p.zup_id].email, fixtures[p.zup_id].full_name, fixtures[p.zup_id].role)
            for p in people):
        raise RuntimeError("Workspace setup requires the exact 34 synthetic identities")
    # Dedicated connection holds a session-level lock across service commits.
    with db.get_bind().connect() as lock:
        lock.execute(text("SELECT pg_advisory_lock(20261018, 25)"))
        try:
            return _provision(db, mock_path, people, as_of)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(20261018, 25)"))
            lock.commit()


def _provision(db, mock_path, people, as_of):
    hr = next(p for p in people if p.zup_id == "demo-3")
    aidana = next(p for p in people if p.zup_id == "demo-1")
    with sqlite3.connect(mock_path, timeout=20) as source:
        restore_source(db, source, people)
        # Restore the persisted allowance only; confirmed/pending deductions still
        # determine today's balance, including manual actions after setup.
        for person in people:
            saved = db.get(DemoSetupState, f"workspace-v1-balance-{person.zup_id}")
            if saved:
                source.execute("UPDATE balances SET initial_days=? WHERE employee_id=?",
                    (json.loads(saved.value_json)["initial_days"], person.zup_id))
        source.commit()
        cleared = []
        if not db.get(DemoSetupState, "workspace-v1-aidana-cleared"):
            cleared = clear_manual_calendar(db, aidana, hr)
        calendar = None
        if not db.get(DemoSetupState, "workspace-v1-calendar"):
            # Give enough temporary synthetic source days to prepare scenarios.
            source.execute("UPDATE balances SET initial_days=100 WHERE employee_id IN (%s)" %
                ",".join("?" for _ in people), [p.zup_id for p in people])
            source.commit()
            calendar = provision_leave(db, as_of=as_of, plan=ALL_PLAN + EXTRA_PLAN, exclude_zup_ids={"demo-1"})
            checkpoint(db, "workspace-v1-calendar", calendar)
        balances = 0
        for person in people:
            key = f"workspace-v1-balance-{person.zup_id}"
            if db.get(DemoSetupState, key):
                continue
            current = available_leave_balance(db, person)
            initial = source.execute("SELECT initial_days FROM balances WHERE employee_id=?", (person.zup_id,)).fetchone()[0]
            initial += 25 - current
            # Persist intent first: retry after interruption sets the same baseline.
            record(db, hr.id, "demo.leave_balance_set", "employee", person.id)
            checkpoint(db, key, {"initial_days": initial, "available_after_setup": 25})
            source.execute("UPDATE balances SET initial_days=? WHERE employee_id=?", (initial, person.zup_id))
            source.commit()
            balances += 1
        activity = learning_activity(db, people)
    return {"balances_set": balances, "aidana_cleared": cleared, "calendar": calendar, "activity_events": activity}


def main():
    with Session(get_engine()) as db:
        print(json.dumps(provision(db, os.environ["ZUP_MOCK_DATABASE"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
