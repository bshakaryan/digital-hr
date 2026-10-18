"""Mock-only leave provisioning through the real request workflow."""
from datetime import date

import pytest
from sqlalchemy import select


def populate(api):
    from app.provision_jana_people import provision as provision_people
    from app.provision_jana_people_leave import provision

    with api.db.session() as db:
        assert provision_people(db) == 30
        db.commit()
        return provision(db, as_of=date(2026, 10, 18))


def test_provisioned_leave_is_valid_and_idempotent(api):
    from app.models import Employee, LeaveDeduction, LeaveRequest, RequestHistory, ZupDelivery
    from app.provision_jana_people_leave import ALL_PLAN, provision

    first = populate(api)
    assert first == {"month": "2026-10", "created": 30, "requests": 30,
        "by_status": {"approved": 17, "submitted": 4, "manager_approved": 5, "rejected": 4},
        "departments": 8, "skipped_overlaps": []}
    with api.db.session() as db:
        rows = db.scalars(select(LeaveRequest).where(LeaveRequest.idempotency_key.like("jana-people-leave-v1-%"))).all()
        assert len(rows) == len(ALL_PLAN) == 30
        by_id = {person.id: person for person in db.scalars(select(Employee)).all()}
        approved_days = {employee_id: sum(item.days_count for item in rows
            if item.employee_id == employee_id and item.status == "approved") for employee_id in by_id}
        for row in rows:
            owner = by_id[row.employee_id]
            assert owner.zup_id.startswith("people-") or owner.zup_id in ("demo-1", "demo-2")
            assert row.days_count > 0 and row.days_count <= owner.leave_balance
            assert row.calendar_version == "kz-statutory-2026-v1"
            assert db.scalar(select(RequestHistory.id).where(RequestHistory.request_id == row.id)) is not None
            if row.status == "approved":
                assert db.scalar(select(LeaveDeduction.id).where(LeaveDeduction.request_id == row.id)) is not None
                assert db.scalar(select(ZupDelivery.id).where(ZupDelivery.request_id == row.id)) is not None
                assert api.db.adapter.balance(owner.zup_id).balance == owner.leave_balance - approved_days[owner.id]
            else:
                assert db.scalar(select(LeaveDeduction.id).where(LeaveDeduction.request_id == row.id)) is None
                assert api.db.adapter.balance(owner.zup_id).balance == owner.leave_balance - approved_days[owner.id]
    before = api.db.snapshot("leave_requests", "request_history", "leave_deductions", "zup_deliveries", "notifications", "audit_events")
    with api.db.session() as db:
        second = provision(db, as_of=date(2026, 10, 18))
    assert second == {**first, "created": 0}
    assert api.db.snapshot("leave_requests", "request_history", "leave_deductions", "zup_deliveries", "notifications", "audit_events") == before


def test_calendar_and_request_access_follow_owner_and_reviewer(api):
    from app.models import Employee, LeaveRequest
    from app.security import issue_token

    populate(api)
    with api.db.session() as db:
        employees = {row.zup_id: row for row in db.scalars(select(Employee))}
        by_id = {person.id: person for person in employees.values()}
        requests = {by_id[row.employee_id].zup_id: row for row in db.scalars(select(LeaveRequest).where(
            LeaveRequest.idempotency_key.like("jana-people-leave-v1-%")))}
        approved_ids = {row.id for row in requests.values() if row.status == "approved" and row.start_date.month == 10}
        pending = requests["people-010"]
        pending_id = pending.id
        hr_pending_id = requests["people-016"].id
        manager_id = employees["people-006"].id
        owner_id = employees["people-010"].id
        unrelated_id = employees["people-007"].id
    def headers(employee_id):
        return {"Authorization": f"Bearer {issue_token(employee_id)}"}

    colleague = api.get("/api/calendar?month=2026-10", "employee")
    assert colleague.status_code == 200
    visible = {row["id"] for row in colleague.json()["absences"]}
    assert approved_ids <= visible and pending_id not in visible
    assert "DEMO / SYNTHETIC" not in colleague.text
    assert api.get(f"/api/requests/{pending_id}", "employee").status_code == 404

    for person_id in (owner_id, manager_id):
        calendar = api.client.get("/api/calendar?month=2026-10", headers=headers(person_id))
        assert pending_id in {row["id"] for row in calendar.json()["absences"]}
        assert api.client.get(f"/api/requests/{pending_id}", headers=headers(person_id)).status_code == 200
    unrelated = api.client.get("/api/calendar?month=2026-10", headers=headers(unrelated_id))
    assert pending_id not in {row["id"] for row in unrelated.json()["absences"]}
    assert api.client.get(f"/api/requests/{pending_id}", headers=headers(unrelated_id)).status_code == 404
    hr_calendar_ids = {row["id"] for row in api.get("/api/calendar?month=2026-10", "hr").json()["absences"]}
    assert pending_id not in hr_calendar_ids and hr_pending_id in hr_calendar_ids
    assert hr_pending_id not in {row["id"] for row in api.client.get(
        "/api/calendar?month=2026-10", headers=headers(unrelated_id)).json()["absences"]}


def test_first_seven_rows_have_authorized_october_coverage(api):
    from app.models import Employee, LeaveRequest

    populate(api)
    with api.db.session() as db:
        first_seven = db.scalars(select(Employee).order_by(Employee.id).limit(7)).all()
        assert [(person.id, person.full_name, person.leave_balance, person.manager_id) for person in first_seven] == [
            (1, "Айдана Демо", 18, 2), (2, "Арман Демо", 22, None),
            (3, "Алия Демо", 24, None), (4, "Данияр Демо", 12, None),
            (5, "Ерлан Садыков", 20, None), (6, "Мадина Жумабаева", 20, 5),
            (7, "Тимур Абдрахманов", 20, 5),
        ]
        rows = db.scalars(select(LeaveRequest).where(LeaveRequest.employee_id.in_(range(1, 8)),
            LeaveRequest.start_date <= date(2026, 10, 31), LeaveRequest.end_date >= date(2026, 10, 1))).all()
        approved = {person.id: [row for row in rows if row.employee_id == person.id and row.status == "approved"]
            for person in first_seven}
        assert {person.full_name: len(approved[person.id]) for person in first_seven} == {
            "Айдана Демо": 3, "Арман Демо": 2, "Алия Демо": 0,
            "Данияр Демо": 0, "Ерлан Садыков": 2,
            "Мадина Жумабаева": 3, "Тимур Абдрахманов": 2,
        }
        covered = {day for periods in approved.values() for row in periods
            for day in range(row.start_date.day, row.end_date.day + 1)}
        assert set(range(1, 26)) | {28, 29, 30} <= covered
        pending_ids = {row.id for row in rows if row.status in ("submitted", "manager_approved")}
        rejected_ids = {row.id for row in rows if row.status == "rejected"}

    outsider = api.get("/api/calendar?month=2026-10", "outsider")
    assert outsider.status_code == 200
    assert [person["full_name"] for person in outsider.json()["employees"][:7]] == [
        person.full_name for person in first_seven]
    outsider_ids = {row["id"] for row in outsider.json()["absences"]}
    assert {row.id for periods in approved.values() for row in periods} <= outsider_ids
    assert not (pending_ids | rejected_ids) & outsider_ids
    owner_requests = api.get("/api/requests", "employee").json()
    assert any(row["status"] == "submitted" and row["start_date"] == "2026-10-13" for row in owner_requests)
    assert any(row["status"] == "rejected" and row["start_date"] == "2026-10-24" for row in owner_requests)
    hr_events = api.get("/api/calendar?month=2026-10", "hr").json()["absences"]
    assert {row["id"] for row in hr_events if row["status"] == "manager_approved"} >= {
        row.id for row in rows if row.employee_id in (2, 5) and row.status == "manager_approved"}
    assert not {row["id"] for row in hr_events if row["status"] == "submitted" and row["employee_id"] == 1}


def test_existing_synthetic_decisions_survive_plan_extension(api, monkeypatch):
    from app.models import AuditEvent, LeaveRequest, Notification, RequestHistory
    from app.provision_jana_people import provision as provision_people
    from app import provision_jana_people_leave as demo

    def frozen(rows):
        return [tuple(getattr(row, column.name) for column in row.__table__.columns) for row in rows]

    def existing_effects(db, old_ids):
        return (
            frozen(db.scalars(select(LeaveRequest).where(LeaveRequest.id.in_(old_ids)).order_by(LeaveRequest.id)).all()),
            frozen(db.scalars(select(RequestHistory).where(RequestHistory.request_id.in_(old_ids)).order_by(RequestHistory.id)).all()),
            frozen(db.scalars(select(AuditEvent).where(AuditEvent.entity_type == "request",
                AuditEvent.entity_id.in_(old_ids)).order_by(AuditEvent.id)).all()),
            frozen(db.scalars(select(Notification).where(Notification.entity_type == "request",
                Notification.entity_id.in_(old_ids)).order_by(Notification.id)).all()),
        )

    with api.db.session() as db:
        provision_people(db)
        db.commit()
        monkeypatch.setattr(demo, "ALL_PLAN", demo.PLAN)
        assert demo.provision(db, as_of=date(2026, 10, 18))["created"] == 15
        old_ids = set(db.scalars(select(LeaveRequest.id).where(
            LeaveRequest.idempotency_key.like("jana-people-leave-v1-%"))).all())
        before = existing_effects(db, old_ids)
        monkeypatch.setattr(demo, "ALL_PLAN", demo.PLAN + demo.VISIBLE_PLAN)
        assert demo.provision(db, as_of=date(2026, 10, 18))["created"] == 15
        assert existing_effects(db, old_ids) == before


def test_provision_requires_mock_and_existing_synthetic_people(api, monkeypatch):
    from app.config import get_settings
    from app.provision_jana_people_leave import provision

    with api.db.session() as db:
        with pytest.raises(RuntimeError, match="Provision Jana People"):
            provision(db, as_of=date(2026, 10, 18))
        monkeypatch.setenv("ZUP_MODE", "real")
        monkeypatch.setenv("ZUP_BASE_URL", "https://zup.example.test/hs/jana/v1")
        get_settings.cache_clear()
        try:
            with pytest.raises(RuntimeError, match="ZUP_MODE=mock"):
                provision(db, as_of=date(2026, 10, 18))
        finally:
            get_settings.cache_clear()


def test_existing_leave_overlap_skips_period_without_rewriting_it(api):
    from app.models import Employee, LeaveRequest
    from app.provision_jana_people import provision as provision_people
    from app import provision_jana_people_leave as demo

    with api.db.session() as db:
        provision_people(db)
        db.commit()
        original_plan = demo.ALL_PLAN
        demo.ALL_PLAN = demo.PLAN
        try:
            assert demo.provision(db, as_of=date(2026, 10, 18))["created"] == 15
        finally:
            demo.ALL_PLAN = original_plan

    existing = api.leave(key="existing-demo-1-october", start_date="2026-10-07", end_date="2026-10-09")
    manager = api.decide(existing, "manager")
    assert manager.status_code == 200, manager.text
    final = api.decide(manager.json(), "hr")
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "approved"
    before = api.db.snapshot("leave_requests", "request_history", "leave_deductions",
        "zup_deliveries", "notifications", "audit_events")
    original_balance = api.db.adapter.balance("demo-1").balance

    with api.db.session() as db:
        first = demo.provision(db, as_of=date(2026, 10, 18))
    assert first["created"] == 14
    assert first["requests"] == 29
    assert first["departments"] >= 7
    assert first["skipped_overlaps"] == [{"zup_id": "demo-1", "start_date": "2026-10-07",
        "end_date": "2026-10-09", "existing_request_id": existing["id"]}]
    with api.db.session() as db:
        owner = db.scalar(select(Employee).where(Employee.zup_id == "demo-1"))
        assert db.scalar(select(LeaveRequest.id).where(LeaveRequest.employee_id == owner.id,
            LeaveRequest.idempotency_key.like("%-demo-1-visible-approved-a"))) is None
        other_approved = db.scalar(select(LeaveRequest).where(LeaveRequest.employee_id == owner.id,
            LeaveRequest.idempotency_key.like("%-demo-1-visible-approved-b")))
        assert other_approved is not None and other_approved.status == "approved"
        assert db.scalar(select(LeaveRequest.id).where(
            LeaveRequest.idempotency_key.like("%-demo-2-visible-approved-a"))) is not None
    assert api.get("/api/calendar?month=2026-10", "outsider").json()["absences"]
    after = api.db.snapshot(*before)
    for table, original in before.items():
        assert after[table][:len(original)] == original
    assert api.db.adapter.balance("demo-1").balance == original_balance - other_approved.days_count
    with api.db.session() as db:
        second = demo.provision(db, as_of=date(2026, 10, 18))
    assert second == {**first, "created": 0}
    assert api.db.snapshot(*before) == after
