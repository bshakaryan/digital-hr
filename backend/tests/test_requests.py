"""End-to-end commands and effects; SQLite races do not prove PostgreSQL locking."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import select


def test_idempotent_create_preserves_all_effects_and_rejects_changed_payload(api):
    api.headers("employee")
    profile = api.get("/api/me").json()
    before = api.db.snapshot()
    created = api.leave()
    after = api.db.snapshot()
    assert created["status"] == "submitted"
    assert created["version"] == 1
    assert [item["status"] for item in created["history"]] == ["submitted"]
    assert len(after["leave_requests"]) == len(before["leave_requests"]) + 1
    assert len(after["request_history"]) == len(before["request_history"]) + 1
    assert len(after["audit_events"]) == len(before["audit_events"]) + 1
    # Author, direct manager, HR each receive exactly one notification.
    assert len(after["notifications"]) == len(before["notifications"]) + 3
    replay = api.create()
    assert replay.status_code == 201
    assert replay.json() == created
    assert api.db.snapshot() == after
    for changes in ({"comment": "changed"}, {"start_date": "2027-01-12"}, {"end_date": "2027-01-16"}):
        response = api.create(**changes)
        assert response.status_code == 409
        assert api.db.snapshot() == after
    assert api.get("/api/me").json() == profile
    for actor, kind in (("employee", "request_submitted"), ("manager", "request_review"), ("hr", "request_review")):
        matching = [item for item in api.get("/api/notifications", actor).json() if item["kind"] == kind]
        assert len(matching) == 1


def test_idempotency_keys_are_scoped_to_author(api):
    first = api.leave()
    second = api.leave("outsider")
    assert first["id"] != second["id"]
    assert (first["employee_id"], second["employee_id"]) == (1, 4)


@pytest.mark.parametrize(
    "actor,owners",
    [("employee", {1}), ("manager", {1, 2}), ("hr", {1, 2, 3, 4}), ("outsider", {4})],
)
def test_request_lists_and_details_share_object_permissions(api, actor, owners):
    created = [api.leave(owner) for owner in ("employee", "manager", "hr", "outsider")]
    response = api.get("/api/requests", actor)
    assert response.status_code == 200
    items = response.json()
    assert {item["employee_id"] for item in items} == owners
    ids = [item["id"] for item in items]
    assert ids == sorted(ids, reverse=True)
    for item in created:
        detail = api.get(f"/api/requests/{item['id']}", actor)
        assert detail.status_code == (200 if item["employee_id"] in owners else 404)
    assert api.get("/api/requests/999999", actor).status_code == 404


@pytest.mark.parametrize("actor", ["employee", "manager", "hr"])
def test_every_role_is_forbidden_to_approve_its_own_request(api, actor):
    item = api.leave(actor)
    before = api.db.snapshot()
    assert api.decide(item, actor).status_code == 403
    assert api.db.snapshot() == before


def test_unrelated_manager_cannot_see_or_decide_outsider_request(api):
    from app.models import Employee

    # A matching department label does not make somebody a direct report.
    with api.db.session() as db:
        db.get(Employee, 4).department = db.get(Employee, 2).department
        db.commit()
    outsider = api.leave("outsider")
    employee = api.leave("employee")
    api.headers("manager")
    before = api.db.snapshot()
    assert api.decide(outsider, "manager").status_code == 404
    assert api.decide(employee, "outsider").status_code == 404
    assert api.db.snapshot() == before


@pytest.mark.parametrize("actor,status", [("manager", "approved"), ("hr", "rejected")])
def test_human_decision_is_final_and_has_one_history_audit_and_notification(api, actor, status):
    from app.models import AuditEvent, Notification, RequestHistory

    item = api.leave()
    api.headers(actor)
    before = api.db.snapshot()
    response = api.decide(item, actor, status)
    assert response.status_code == 200, response.text
    decided = response.json()
    assert decided["status"] == status
    assert decided["version"] == item["version"] + 1
    assert [entry["status"] for entry in decided["history"]] == ["submitted", status]
    assert decided["history"][-1]["comment"] == "Human decision"
    after = api.db.snapshot()
    for table in ("request_history", "audit_events", "notifications"):
        assert len(after[table]) == len(before[table]) + 1
    with api.db.session() as db:
        history = db.scalars(select(RequestHistory).where(RequestHistory.request_id == item["id"])).all()
        assert [entry.actor_id for entry in history] == [1, 2 if actor == "manager" else 3]
        events = db.scalars(select(AuditEvent).where(AuditEvent.entity_type == "request", AuditEvent.entity_id == item["id"])).all()
        assert sorted(event.action for event in events) == sorted(["request.created", f"request.{status}"])
        notifications = db.scalars(select(Notification).where(Notification.employee_id == 1, Notification.kind == "request_status")).all()
        assert len(notifications) == len([n for n in before["notifications"] if n.employee_id == 1 and n.kind == "request_status"]) + 1
    assert api.decide(item, actor, status).status_code == 409
    assert api.decide(decided, actor, "rejected" if status == "approved" else "approved").status_code == 409
    assert api.db.snapshot() == after
    assert api.get(f"/api/requests/{item['id']}").json() == decided


def test_stale_version_cannot_change_even_a_submitted_request(api):
    item = api.leave()
    api.headers("manager")
    before = api.db.snapshot()
    assert api.decide(item, version=item["version"] + 1).status_code == 409
    assert api.db.snapshot() == before
    assert api.decide(item).status_code == 200


def test_two_concurrent_decisions_have_one_winner_and_one_set_of_effects(api):
    item = api.leave()
    for actor in ("manager", "hr"):
        api.headers(actor)
    before = api.db.snapshot()
    barrier = Barrier(2)

    def decide(actor, status):
        barrier.wait(timeout=10)
        return api.decide(item, actor, status)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(decide, "manager", "approved"), pool.submit(decide, "hr", "rejected")]
        responses = [future.result(timeout=20) for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 409], [r.text for r in responses]
    winner = next(response.json() for response in responses if response.status_code == 200)
    assert winner["version"] == item["version"] + 1
    assert len(winner["history"]) == 2
    assert api.get(f"/api/requests/{item['id']}").json() == winner
    after = api.db.snapshot()
    for table in ("request_history", "audit_events", "notifications"):
        assert len(after[table]) == len(before[table]) + 1


@pytest.mark.parametrize(
    "body,key",
    [
        ({"start_date": "2027-02-02", "end_date": "2027-02-01"}, "valid-test-key"),
        ({"employee_id": 4}, "valid-test-key"),
        ({"status": "approved"}, "valid-test-key"),
        ({"version": 42}, "valid-test-key"),
        ({}, None),
        ({}, "short"),
        ({}, "x" * 129),
    ],
)
def test_invalid_create_and_mass_assignment_cannot_write(api, body, key):
    headers = api.headers()
    if key is not None:
        headers["Idempotency-Key"] = key
    payload = {"start_date": "2027-02-01", "end_date": "2027-02-02", "comment": "validation"} | body
    before = api.db.snapshot()
    response = api.client.post("/api/requests", headers=headers, json=payload)
    assert response.status_code == 422
    assert api.db.snapshot() == before


def test_create_rolls_back_all_effects_when_notification_fails(api, monkeypatch):
    from app.modules import requests

    api.headers()
    before = api.db.snapshot()

    def fail(*args, **kwargs):
        raise RuntimeError("simulated notification storage failure")

    with monkeypatch.context() as patch:
        patch.setattr(requests, "notify", fail)
        with pytest.raises(RuntimeError, match="simulated notification storage failure"):
            api.create()
    assert api.db.snapshot() == before
    assert api.create().status_code == 201
