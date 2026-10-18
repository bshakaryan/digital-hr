from datetime import date

import pytest


@pytest.mark.parametrize("actor", ["employee", "manager", "hr", "outsider"])
def test_shared_calendar_shows_colleagues_but_keeps_private_records_scoped(api, actor):
    from app.models import LeaveRequest

    with api.db.session() as db:
        rows = [LeaveRequest(employee_id=employee_id, start_date=date(2028, 2, 1), end_date=date(2028, 2, 3),
            status="approved", comment="Private calendar comment", idempotency_key=f"calendar-{employee_id}", payload_hash="test")
            for employee_id in (1, 2, 3, 4)]
        db.add_all(rows)
        db.commit()
        request_ids = {row.employee_id: row.id for row in rows}

    headers = api.headers(actor)
    allowed_profiles = {row["id"] for row in api.get("/api/employees", actor).json()}
    allowed_requests = {row["id"] for row in api.get("/api/requests", actor).json()}
    before = api.db.snapshot()
    response = api.client.get("/api/calendar?month=2028-02", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    result = response.json()
    assert set(result) == {"month", "employees", "absences"}
    assert result["month"] == "2028-02"
    assert {row["id"] for row in result["employees"]} == {1, 2, 3, 4}
    assert {row["employee_id"] for row in result["absences"]} == {1, 2, 3, 4}
    for row in result["employees"]:
        assert set(row) == {"id", "full_name", "department", "can_open_profile"}
        assert row["can_open_profile"] == (row["id"] in allowed_profiles)
        if not row["can_open_profile"]:
            assert api.get(f"/api/employees/{row['id']}", actor).status_code == 404
    for row in result["absences"]:
        assert set(row) == {"id", "employee_id", "start_date", "end_date", "status", "can_open_request"}
        assert row["can_open_request"] == (row["id"] in allowed_requests)
        if not row["can_open_request"]:
            assert api.get(f"/api/requests/{row['id']}", actor).status_code == 404
    assert request_ids[4] in {row["id"] for row in result["absences"]}
    assert "Private calendar comment" not in response.text
    assert api.db.snapshot() == before


def test_calendar_filters_active_statuses_and_inclusive_month_boundaries(api):
    from app.models import LeaveRequest

    periods = [
        ("approved", "2027-12-31", "2028-01-01"),
        ("submitted", "2028-01-31", "2028-02-01"),
        ("manager_approved", "2028-02-29", "2028-03-01"),
        ("cancellation_requested", "2028-01-01", "2028-03-31"),
        ("rejected", "2028-02-01", "2028-02-01"),
        ("withdrawn", "2028-02-02", "2028-02-02"),
        ("cancelled", "2028-02-03", "2028-02-03"),
    ]
    with api.db.session() as db:
        rows = [LeaveRequest(employee_id=4, start_date=date.fromisoformat(start), end_date=date.fromisoformat(end),
            status=status, idempotency_key=f"calendar-{status}", payload_hash="test") for status, start, end in periods]
        db.add_all(rows)
        db.commit()
        ids = {row.status: row.id for row in rows}
    expected = {
        "2027-12": ["approved"],
        "2028-01": ["approved", "submitted", "cancellation_requested"],
        "2028-02": ["submitted", "manager_approved", "cancellation_requested"],
        "2028-03": ["manager_approved", "cancellation_requested"],
        "2028-04": [],
    }
    for month, statuses in expected.items():
        response = api.get(f"/api/calendar?month={month}", "outsider")
        assert response.status_code == 200
        actual = {row["id"] for row in response.json()["absences"] if row["employee_id"] == 4}
        assert actual == {ids[status] for status in statuses}
        assert len(response.json()["employees"]) == 4


def test_colleague_pending_leave_is_hidden_but_owner_and_reviewer_can_see_it(api):
    from app.models import LeaveRequest

    with api.db.session() as db:
        pending = LeaveRequest(employee_id=1, start_date=date(2028, 4, 10), end_date=date(2028, 4, 12),
            status="submitted", comment="Private pending reason", idempotency_key="calendar-private-pending", payload_hash="test")
        approved = LeaveRequest(employee_id=4, start_date=date(2028, 4, 15), end_date=date(2028, 4, 17),
            status="approved", idempotency_key="calendar-public-approved", payload_hash="test")
        db.add_all([pending, approved])
        db.commit()
        pending_id, approved_id = pending.id, approved.id

    colleague = api.get("/api/calendar?month=2028-04", "outsider")
    assert colleague.status_code == 200
    assert {row["id"] for row in colleague.json()["absences"]} == {approved_id}
    assert str(pending_id) not in [str(row["id"]) for row in colleague.json()["absences"]]
    assert "Private pending reason" not in colleague.text
    assert pending_id in {row["id"] for row in api.get("/api/calendar?month=2028-04", "employee").json()["absences"]}
    reviewer_rows = api.get("/api/calendar?month=2028-04", "manager").json()["absences"]
    assert pending_id in {row["id"] for row in reviewer_rows}
    assert next(row for row in reviewer_rows if row["id"] == pending_id)["can_open_request"]


def test_calendar_requires_authentication_and_valid_month(api):
    assert api.client.get("/api/calendar?month=2028-02").status_code == 401
    for query in ("", "?month=", "?month=2028-00", "?month=2028-13", "?month=0000-01", "?month=2028-2", "?month=2028-02-01", "?month=10000-01"):
        assert api.get(f"/api/calendar{query}").status_code == 422
    for month in ("1000-01", "9999-12"):
        assert api.get(f"/api/calendar?month={month}").status_code == 200
