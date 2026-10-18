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
    from app.provision_jana_people_leave import PLAN, provision

    first = populate(api)
    assert first == {"month": "2026-10", "created": 15, "requests": 15,
        "by_status": {"approved": 7, "submitted": 3, "manager_approved": 3, "rejected": 2},
        "departments": 7}
    with api.db.session() as db:
        rows = db.scalars(select(LeaveRequest).where(LeaveRequest.idempotency_key.like("jana-people-leave-v1-%"))).all()
        assert len(rows) == len(PLAN) == 15
        by_id = {person.id: person for person in db.scalars(select(Employee)).all()}
        for row in rows:
            owner = by_id[row.employee_id]
            assert owner.zup_id.startswith("people-")
            assert row.days_count > 0 and row.days_count <= owner.leave_balance
            assert row.calendar_version == "kz-statutory-2026-v1"
            assert db.scalar(select(RequestHistory.id).where(RequestHistory.request_id == row.id)) is not None
            if row.status == "approved":
                assert db.scalar(select(LeaveDeduction.id).where(LeaveDeduction.request_id == row.id)) is not None
                assert db.scalar(select(ZupDelivery.id).where(ZupDelivery.request_id == row.id)) is not None
                assert api.db.adapter.balance(owner.zup_id).balance == owner.leave_balance - row.days_count
            else:
                assert db.scalar(select(LeaveDeduction.id).where(LeaveDeduction.request_id == row.id)) is None
                assert api.db.adapter.balance(owner.zup_id).balance == owner.leave_balance
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
        employees = {row.zup_id: row for row in db.scalars(select(Employee).where(Employee.zup_id.like("people-%")))}
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


def test_existing_leave_overlap_stops_provision_without_rewriting_it(api):
    from app.models import Employee, LeaveRequest
    from app.provision_jana_people import provision as provision_people
    from app.provision_jana_people_leave import provision

    with api.db.session() as db:
        provision_people(db)
        owner = db.scalar(select(Employee).where(Employee.zup_id == "people-002"))
        legacy = LeaveRequest(employee_id=owner.id, start_date=date(2026, 10, 3), end_date=date(2026, 10, 5),
            status="approved", idempotency_key="preexisting-legacy-leave", payload_hash="legacy")
        db.add(legacy)
        db.commit()
    before = api.db.snapshot("leave_requests", "notifications", "audit_events")
    with api.db.session() as db:
        with pytest.raises(RuntimeError, match="Existing leave overlaps"):
            provision(db, as_of=date(2026, 10, 18))
    assert api.db.snapshot("leave_requests", "notifications", "audit_events") == before
