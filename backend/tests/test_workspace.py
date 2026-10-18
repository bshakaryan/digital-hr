from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from alembic import command
from sqlalchemy import inspect, select, text


def act(api, item, operation, actor="employee", key=None, **changes):
    body = {"version": item["version"], "comment": "Демонстрационный запрос"}
    body.update(changes)
    return api.client.post(f"/api/requests/{item['id']}/{operation}", json=body,
        headers={**api.headers(actor), "Idempotency-Key": key or f"workflow-{operation}-{item['id']}"})


def approved(api):
    return api.decide(api.decide(api.leave()).json(), "hr").json()


def test_review_queue_tracks_only_current_authorized_stage(api):
    item = api.leave()
    for actor in ("employee", "outsider", "hr"):
        assert item["id"] not in {row["id"] for row in api.get("/api/requests/review-queue", actor).json()}
    queue = api.get("/api/requests/review-queue", "manager").json()
    assert item["id"] in {row["id"] for row in queue}
    assert all(row["can_review"] for row in queue)
    item = api.decide(item).json()
    assert item["id"] not in {row["id"] for row in api.get("/api/requests/review-queue", "manager").json()}
    assert item["id"] in {row["id"] for row in api.get("/api/requests/review-queue", "hr").json()}
    assert item["calendar_days"] == 5


def test_linked_notifications_and_read_all_are_private_and_idempotent(api):
    item = api.leave()
    notifications = api.get("/api/notifications", "manager").json()
    linked = next(row for row in notifications if row["entity_id"] == item["id"] and row["entity_type"] == "request")
    assert linked["actor_id"] == 1 and linked["actor_name"]
    other = api.get("/api/notifications").json()
    assert api.patch("/api/notifications/read-all", actor="manager").json()["updated"] > 0
    assert api.get("/api/notifications").json() == other
    before = api.db.snapshot()
    assert api.patch("/api/notifications/read-all", actor="manager").json() == {"updated": 0}
    assert api.db.snapshot() == before


def test_audit_filters_pagination_csv_and_permissions(api):
    item = approved(api)
    for actor in ("employee", "manager", "outsider"):
        for path in ("/api/audit/page", "/api/audit/export"):
            assert api.get(path, actor).status_code == 403
    path = "/api/audit/page?employee_id=1&actor_id=3&action=request.approved&page_size=1"
    result = api.get(path, "hr").json()
    assert result["total"] >= 1 and len(result["items"]) == 1
    row = result["items"][0]
    assert row["actor_name"] == "Алия Демо" and row["employee_name"] == "Айдана Демо"
    assert row["action_label"] == "HR согласовал заявку"
    assert row["entity_id"] == item["id"]
    exported = api.get("/api/audit/export?employee_id=1&actor_id=3&action=request.approved", "hr")
    assert exported.status_code == 200 and "text/csv" in exported.headers["content-type"]
    assert row["actor_name"] in exported.text
    assert "auth.login" not in exported.text
    assert api.get("/api/audit/page?start_date=2028-01-02&end_date=2028-01-01", "hr").status_code == 422
    assert api.get("/api/audit/page?page_size=101", "hr").status_code == 422
    assert api.get("/api/audit/page?end_date=9999-12-31", "hr").status_code == 200


def test_withdraw_preserves_history_frees_period_and_replay_has_no_effect(api):
    item = api.decide(api.leave()).json()
    initial = api.get("/api/me").json()["leave_balance"]
    result = act(api, item, "withdraw")
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "withdrawn"
    before = api.db.snapshot()
    assert act(api, item, "withdraw").status_code == 200
    assert api.db.snapshot() == before
    assert act(api, item, "withdraw", comment="Другое тело").status_code == 409
    assert api.decide(item, "hr").status_code == 409
    assert api.get("/api/me").json()["leave_balance"] == initial
    assert api.create(key="new-after-withdraw").status_code == 201
    assert result.json()["history"][-1]["status"] == "withdrawn"


def test_replace_is_atomic_and_restarts_both_approval_stages(api):
    item = api.decide(api.leave()).json()
    calculation = api.post(f"/api/requests/{item['id']}/replacement-calculation", {"start_date": "2027-01-12", "end_date": "2027-01-16"})
    assert calculation.status_code == 200
    body = {"start_date": "2027-01-12", "end_date": "2027-01-16"}
    response = act(api, item, "replace", **body)
    assert response.status_code == 201, response.text
    replacement = response.json()
    assert replacement["id"] != item["id"] and replacement["status"] == "submitted"
    assert api.get(f"/api/requests/{item['id']}").json()["status"] == "withdrawn"
    assert api.decide(replacement, "hr").status_code == 409
    before = api.db.snapshot()
    assert act(api, item, "replace", **body).json()["id"] == replacement["id"]
    assert api.db.snapshot() == before


def test_failed_replacement_does_not_withdraw_original(api):
    item = api.leave()
    before = api.db.snapshot()
    result = act(api, item, "replace", start_date="2029-01-01", end_date="2029-01-05")
    assert result.status_code == 422
    assert api.db.snapshot() == before


@pytest.mark.parametrize("operation", ["withdraw", "cancel", "replace"])
def test_lifecycle_is_owner_only_and_checks_visibility_and_version(api, operation):
    item = api.leave()
    changes = {"start_date": "2027-02-01", "end_date": "2027-02-02"} if operation == "replace" else {}
    assert act(api, item, operation, "manager", **changes).status_code == 403
    assert act(api, item, operation, "outsider", **changes).status_code == 404
    assert act(api, item, operation, version=99, **changes).status_code == 409


def test_cancellation_requires_hr_and_refunds_once(api):
    initial = api.get("/api/me").json()["leave_balance"]
    item = approved(api)
    assert item["cancellation_allowed"]
    assert api.get("/api/me").json()["leave_balance"] == initial - 5
    pending = act(api, item, "cancel").json()
    assert pending["status"] == "cancellation_requested"
    assert api.create(key="overlap-cancellation").status_code == 409
    for actor in ("employee", "manager"):
        assert act(api, pending, "cancellation-decision", actor, status="approved").status_code == 403
    result = act(api, pending, "cancellation-decision", "hr", status="approved")
    assert result.status_code == 200, result.text
    cancelled = result.json()
    assert cancelled["status"] == "cancelled" and cancelled["cancellation_sync_status"] == "synced"
    assert cancelled["cancellation_reference"].startswith("ZUP-CANCEL-")
    assert api.get("/api/me").json()["leave_balance"] == initial
    before = api.db.snapshot()
    assert act(api, pending, "cancellation-decision", "hr", status="approved").status_code == 200
    assert api.post(f"/api/requests/{item['id']}/cancellation-sync", {}, "hr").status_code == 200
    assert api.db.snapshot() == before
    assert api.create(key="new-after-cancellation").status_code == 201


def test_hr_leave_cancellation_is_decided_by_manager(api):
    from app.models import Employee

    with api.db.session() as db:
        db.get(Employee, 3).manager_id = 2
        db.get(Employee, 4).role = "manager"
        db.commit()
    initial = api.get("/api/me", "hr").json()["leave_balance"]
    item = api.decide(api.leave("hr", key="hr-one-stage"), "manager").json()
    assert item["status"] == "approved"
    assert api.get("/api/me", "hr").json()["leave_balance"] == initial - 5

    pending = act(api, item, "cancel", "hr", key="hr-cancel-request").json()
    assert pending["approval_route"] == "hr_to_manager"
    assert pending["can_review"] is False
    assert pending["id"] in {row["id"] for row in api.get("/api/requests/review-queue", "manager").json()}
    assert pending["id"] not in {row["id"] for row in api.get("/api/requests/review-queue", "outsider").json()}
    assert act(api, pending, "cancellation-decision", "outsider", key="unrelated-hr-cancel", status="approved").status_code == 404
    assert not [row for row in api.get("/api/notifications", "outsider").json() if row["entity_id"] == pending["id"]]
    assert act(api, pending, "cancellation-decision", "hr", key="hr-self-cancel", status="approved").status_code == 403

    result = act(api, pending, "cancellation-decision", "manager", key="hr-cancel-decision", status="approved")
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "cancelled"
    assert result.json()["history"][-1]["actor_name"] == "Арман Демо"
    assert api.get("/api/me", "hr").json()["leave_balance"] == initial


def test_cancellation_rejection_keeps_accounting_and_can_be_requested_again(api):
    item = approved(api)
    pending = act(api, item, "cancel").json()
    balance = api.get("/api/me").json()["leave_balance"]
    result = act(api, pending, "cancellation-decision", "hr", status="rejected").json()
    assert result["status"] == "approved"
    assert api.get("/api/me").json()["leave_balance"] == balance
    assert not api.db.snapshot("leave_cancellations")["leave_cancellations"]
    assert act(api, result, "cancel", key="request-cancel-again").status_code == 200


def test_lost_refund_receipt_and_worker_retry_do_not_add_days_twice(api, monkeypatch):
    from app.zup_worker import run_once
    from app.models import LeaveCancellation, utcnow
    initial = api.get("/api/me").json()["leave_balance"]
    pending = act(api, approved(api), "cancel").json()
    original = api.db.adapter.cancel
    def lost_receipt(body, key):
        original(body, key)
        from fastapi import HTTPException
        raise HTTPException(503, "Response lost")
    monkeypatch.setattr(api.db.adapter, "cancel", lost_receipt)
    result = act(api, pending, "cancellation-decision", "hr", status="approved").json()
    assert result["cancellation_sync_status"] == "error"
    assert api.get("/api/me").json()["leave_balance"] == initial
    monkeypatch.setattr(api.db.adapter, "cancel", original)
    with api.db.session() as db:
        row = db.scalar(select(LeaveCancellation))
        row.next_attempt_at = utcnow()
        db.commit()
    run_once()
    assert api.get(f"/api/requests/{pending['id']}").json()["cancellation_sync_status"] == "synced"
    assert api.get("/api/me").json()["leave_balance"] == initial


def test_refund_failure_does_not_expose_unreturned_days(api, monkeypatch):
    from fastapi import HTTPException
    initial = api.get("/api/me").json()["leave_balance"]
    pending = act(api, approved(api), "cancel").json()
    def offline(*args):
        raise HTTPException(503, "offline")
    monkeypatch.setattr(api.db.adapter, "cancel", offline)
    result = act(api, pending, "cancellation-decision", "hr", status="approved").json()
    assert result["status"] == "cancelled" and result["cancellation_sync_status"] == "error"
    assert api.get("/api/me").json()["leave_balance"] == initial - 5
    assert api.post(f"/api/requests/{pending['id']}/cancellation-sync", {}).status_code == 403


def test_cancellation_rolls_back_when_notification_storage_fails(api, monkeypatch):
    from app.modules import lifecycle
    pending = act(api, approved(api), "cancel").json()
    api.headers("hr")
    before = api.db.snapshot()
    def fail(*args, **kwargs):
        raise RuntimeError("notification storage failed")
    with monkeypatch.context() as patch:
        patch.setattr(lifecycle, "notify", fail)
        with pytest.raises(RuntimeError, match="notification storage failed"):
            act(api, pending, "cancellation-decision", "hr", status="approved")
    assert api.db.snapshot() == before
    assert act(api, pending, "cancellation-decision", "hr", status="approved").status_code == 200


def test_cancellation_finishes_unsent_registration_before_refund(api, monkeypatch):
    from fastapi import HTTPException
    initial = api.get("/api/me").json()["leave_balance"]
    original = api.db.adapter.register
    def offline(*args):
        raise HTTPException(503, "offline before original registration")
    monkeypatch.setattr(api.db.adapter, "register", offline)
    item = approved(api)
    assert item["zup_sync_status"] == "error"
    assert api.get("/api/me").json()["leave_balance"] == initial - 5
    pending = act(api, item, "cancel").json()
    monkeypatch.setattr(api.db.adapter, "register", original)
    result = act(api, pending, "cancellation-decision", "hr", status="approved").json()
    assert result["zup_sync_status"] == result["cancellation_sync_status"] == "synced"
    assert api.get("/api/me").json()["leave_balance"] == initial


def test_real_mode_blocks_demo_cancellation(api, monkeypatch):
    from app.config import get_settings
    item = approved(api)
    monkeypatch.setenv("ZUP_MODE", "real")
    monkeypatch.setenv("ZUP_BASE_URL", "https://zup.example.test/hs/jana/v1")
    get_settings.cache_clear()
    assert act(api, item, "cancel").status_code == 409
    get_settings.cache_clear()


def test_legacy_and_started_leave_cannot_be_cancelled(api):
    from datetime import date
    from app.models import LeaveRequest
    item = approved(api)
    with api.db.session() as db:
        db.get(LeaveRequest, item["id"]).start_date = date(2026, 1, 1)
        db.commit()
    assert act(api, item, "cancel").status_code == 409
    historical = next(row for row in api.get("/api/requests").json() if row["status"] == "approved" and row["zup_sync_status"] == "legacy")
    assert not historical["cancellation_allowed"]
    assert act(api, historical, "cancel").status_code == 409


def test_blank_reason_and_missing_command_key_are_rejected(api):
    item = api.leave()
    assert act(api, item, "withdraw", comment="  ").status_code == 422
    assert api.post(f"/api/requests/{item['id']}/withdraw", {"version": 1, "comment": "reason"}).status_code == 422


def test_audit_csv_escapes_spreadsheet_formulas(api):
    from app.models import Employee
    api.headers("hr")
    with api.db.session() as db:
        db.get(Employee, 3).full_name = "=1+1"
        db.commit()
    response = api.get("/api/audit/export?actor_id=3", "hr")
    assert "'=1+1" in response.text


def test_workspace_migration_preserves_populated_0005(database):
    # Exercise the new revision on every old table, on SQLite and isolated PG.
    command.downgrade(database.config, "0005")
    with database.engine.connect() as connection:
        inspector = inspect(connection)
        columns = {table: [column["name"] for column in inspector.get_columns(table)] for table in inspector.get_table_names() if table != "alembic_version"}
        before = {table: connection.execute(text(f'SELECT {",".join(names)} FROM {table} ORDER BY id')).all() for table, names in columns.items()}
    command.upgrade(database.config, "head")
    with database.engine.connect() as connection:
        after = {table: connection.execute(text(f'SELECT {",".join(names)} FROM {table} ORDER BY id')).all() for table, names in columns.items()}
    assert before == after
    command.check(database.config)


def test_concurrent_cancellation_decisions_create_one_refund(api):
    pending = act(api, approved(api), "cancel").json()
    api.headers("hr")
    barrier = Barrier(2)
    def decide(index):
        barrier.wait()
        return act(api, pending, "cancellation-decision", "hr", key=f"concurrent-cancel-{index}", status="approved").status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, [1, 2]))
    assert sorted(results) == [200, 409]
    assert len(api.db.snapshot("leave_cancellations")["leave_cancellations"]) == 1


def test_concurrent_identical_cancellation_commands_replay_success(api):
    pending = act(api, approved(api), "cancel").json()
    api.headers("hr")
    barrier = Barrier(2)
    def decide(_):
        barrier.wait()
        return act(api, pending, "cancellation-decision", "hr", key="same-cancellation-key", status="approved").status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, [1, 2]))
    assert results == [200, 200]
    assert len(api.db.snapshot("leave_cancellations")["leave_cancellations"]) == 1
