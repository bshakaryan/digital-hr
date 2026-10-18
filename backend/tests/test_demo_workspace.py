"""Synthetic setup against migrated PostgreSQL and an independent HTTP mock."""
from datetime import date
import sqlite3

import pytest
from alembic import command
from sqlalchemy import select, text


def prepare(api):
    from app.provision_jana_people import provision
    from app.models import Course, CourseAssignment
    with api.db.session() as db:
        provision(db)
        # Small synthetic course fixture; activity must not alter assignments/XP.
        course = db.get(Course, 1)
        course.demo_code = "DEMO-TEST-01"
        assignment = db.scalar(select(CourseAssignment).where(CourseAssignment.employee_id == 2))
        assignment.progress, assignment.completed = 100, True
        assignment = db.scalar(select(CourseAssignment).where(CourseAssignment.employee_id == 4))
        assignment.progress = 70
        db.commit()


def setup(api):
    from app.provision_demo_workspace import provision
    with api.db.session() as db:
        return provision(db, str(api.db.zup_path), as_of=date(2026, 10, 18))


def test_setup_balances_calendar_history_activity_and_repeat(api):
    from app.models import AuditEvent, Employee, LeaveRequest, RequestHistory
    prepare(api)
    # Include a registered approval and an open request in Aidana's reset.
    item = api.leave(key="aidana-before-demo", start_date="2026-12-01", end_date="2026-12-05")
    staged = api.decide(item).json()
    assert api.decide(staged, "hr").status_code == 200
    assignments = api.db.snapshot("course_assignments")
    first = setup(api)
    assert first["balances_set"] == 34
    assert first["calendar"]["created"] == 40
    assert first["activity_events"] == 6
    assert item["id"] in first["aidana_cleared"]
    with api.db.session() as db:
        from app.modules.leave_balance import available_leave_balance
        assert {available_leave_balance(db, p) for p in db.scalars(select(Employee))} == {25}
        assert db.get(LeaveRequest, item["id"]).status == "cancelled"
        assert db.scalar(select(RequestHistory.id).where(RequestHistory.request_id == item["id"],
            RequestHistory.status == "cancelled"))
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == "demo.request_cleared"))
    for month in ("2026-10", "2026-11", "2026-12"):
        calendar = api.get(f"/api/calendar?month={month}", "hr").json()
        assert not any(row["employee_id"] == 1 for row in calendar["absences"])
    analytics = api.get("/api/courses/analytics", "hr").json()
    assert analytics["activity_includes_demo"] is True
    assert sum(day["count"] for day in analytics["daily_activity"]) == 6
    assert api.db.snapshot("course_assignments") == assignments
    # A new manual request and a consumed balance must survive subsequent startup.
    manual = api.leave(key="aidana-manual-after-demo", start_date="2026-12-10", end_date="2026-12-12")
    staged = api.decide(manual).json()
    assert api.decide(staged, "hr").status_code == 200
    assert api.get("/api/me").json()["leave_balance"] == 22
    before = api.db.snapshot()
    assert setup(api) == {"balances_set": 0, "aidana_cleared": [], "calendar": None, "activity_events": 0}
    assert api.db.snapshot() == before
    assert api.get("/api/me").json()["leave_balance"] == 22
    # Render Free replaces mock files: reconstruct receipts/baselines without
    # granting days again or losing the manual period's source overlap check.
    with sqlite3.connect(api.db.zup_path) as source:
        source.execute("DELETE FROM cancellations")
        source.execute("DELETE FROM documents")
        source.execute("UPDATE balances SET initial_days=1")
    setup(api)
    assert api.get("/api/me").json()["leave_balance"] == 22
    assert api.db.snapshot() == before
    assert api.post("/api/requests/calculate", {"start_date":"2026-12-10", "end_date":"2026-12-12"}).status_code == 409


def test_setup_refuses_real_or_changed_identities(api, monkeypatch):
    from app.config import get_settings
    from app.models import Employee
    prepare(api)
    with api.db.session() as db:
        db.get(Employee, 1).full_name = "Changed identity"
        db.commit()
    before = api.db.snapshot()
    with pytest.raises(RuntimeError, match="exact 34"):
        setup(api)
    assert api.db.snapshot() == before
    monkeypatch.setenv("ZUP_MODE", "real")
    monkeypatch.setenv("ZUP_BASE_URL", "https://zup.example.test/hs/jana/v1")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="ZUP_MODE=mock"):
            setup(api)
    finally:
        get_settings.cache_clear()


def test_new_migration_preserves_populated_database(postgres_schema):
    command.upgrade(postgres_schema.config, "0014")
    with postgres_schema.engine.begin() as db:
        db.execute(text("INSERT INTO employees (id,email,password_hash,full_name,role,company,position,department,hire_date,leave_balance) VALUES (1,'test@example.com','hash','Existing','employee','Demo','Role','Dept','2024-01-01',18)"))
        before = db.execute(text("SELECT * FROM employees")).all()
    command.upgrade(postgres_schema.config, "head")
    with postgres_schema.engine.connect() as db:
        assert db.execute(text("SELECT * FROM employees")).all() == before
        assert db.scalar(text("SELECT count(*) FROM demo_setup_state")) == 0
    command.check(postgres_schema.config)
