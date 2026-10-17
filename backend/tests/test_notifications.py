from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from alembic import command
from sqlalchemy import inspect, select, text


def test_clear_read_is_private_durable_and_idempotent(api):
    from app.models import AuditEvent, Notification

    api.leave()
    owner = api.get("/api/notifications").json()
    target = owner[0]
    assert len(owner) >= 2
    assert api.patch(f"/api/notifications/{target['id']}/read").status_code == 200
    for actor in ("manager", "hr", "outsider"):
        assert api.patch("/api/notifications/read-all", actor=actor).status_code == 200
    others = {actor: api.get("/api/notifications", actor).json() for actor in ("manager", "hr", "outsider")}
    before = api.db.snapshot()

    response = api.patch("/api/notifications/clear-read")
    assert response.status_code == 200
    assert response.json() == {"updated": 1}
    remaining = api.get("/api/notifications").json()
    assert {item["id"] for item in remaining} == {item["id"] for item in owner} - {target["id"]}
    assert all(not item["read"] for item in remaining)
    for actor, notifications in others.items():
        assert api.get("/api/notifications", actor).json() == notifications
    with api.db.session() as db:
        retained = db.get(Notification, target["id"])
        assert retained.cleared_at is not None and retained.read
        assert retained.body == target["body"] and retained.entity_id == target["entity_id"]
        cleared = db.scalars(select(AuditEvent).where(AuditEvent.action == "notification.cleared")).all()
        assert [(event.actor_id, event.entity_id) for event in cleared] == [(1, target["id"])]
    after = api.db.snapshot()
    for table in before.keys() - {"notifications", "audit_events"}:
        assert after[table] == before[table]
    assert api.patch("/api/notifications/clear-read").json() == {"updated": 0}
    # A delayed read command cannot bring a cleared notification back.
    assert api.patch(f"/api/notifications/{target['id']}/read").status_code == 200
    assert api.db.snapshot() == after
    assert api.get("/api/notifications").json() == remaining
    # The new audit action has a human-readable label for HR.
    audit = api.get("/api/audit/page?action=notification.cleared", "hr").json()
    assert audit["total"] == 1
    assert audit["items"][0]["action_label"] == "Прочитанное уведомление убрано из списка"


def test_clear_read_allows_new_events_and_preserves_unread(api):
    assert api.patch("/api/notifications/clear-read").json() == {"updated": 0}
    original = api.get("/api/notifications").json()
    assert original and all(not item["read"] for item in original)
    assert api.patch("/api/notifications/read-all").json() == {"updated": len(original)}
    assert api.patch("/api/notifications/clear-read").json() == {"updated": len(original)}
    assert api.get("/api/notifications").json() == []
    before = api.db.snapshot()
    assert api.patch("/api/notifications/read-all").json() == {"updated": 0}
    assert api.patch("/api/notifications/clear-read").json() == {"updated": 0}
    assert api.db.snapshot() == before
    item = api.leave()
    events = api.get("/api/notifications").json()
    assert len(events) == 1 and not events[0]["read"]
    assert events[0]["entity_id"] == item["id"]


def test_clearing_rolls_back_if_audit_fails(api, monkeypatch):
    from app.modules import notifications

    api.patch("/api/notifications/read-all")
    before = api.db.snapshot()
    def fail(*args):
        raise RuntimeError("audit storage failed")
    monkeypatch.setattr(notifications, "record", fail)
    with pytest.raises(RuntimeError, match="audit storage failed"):
        api.patch("/api/notifications/clear-read")
    assert api.db.snapshot() == before
    assert api.get("/api/notifications").json()


def test_notification_migration_preserves_populated_0006(api):
    api.leave()
    target = api.get("/api/notifications").json()[0]
    target = api.patch(f"/api/notifications/{target['id']}/read").json()
    command.downgrade(api.db.config, "0006")
    with api.db.engine.connect() as connection:
        inspector = inspect(connection)
        columns = {table: [column["name"] for column in inspector.get_columns(table)] for table in inspector.get_table_names() if table != "alembic_version"}
        before = {table: connection.execute(text(f'SELECT {",".join(names)} FROM {table} ORDER BY id')).all() for table, names in columns.items()}
    assert before["notifications"] and before["audit_events"] and before["request_history"]
    command.upgrade(api.db.config, "head")
    with api.db.engine.connect() as connection:
        after = {table: connection.execute(text(f'SELECT {",".join(names)} FROM {table} ORDER BY id')).all() for table, names in columns.items()}
        assert connection.execute(text("SELECT count(*) FROM notifications WHERE cleared_at IS NOT NULL")).scalar() == 0
    assert after == before
    command.check(api.db.config)
    assert target in api.get("/api/notifications").json()


def test_concurrent_clear_records_each_effect_once(api):
    from app.models import AuditEvent

    total = api.patch("/api/notifications/read-all").json()["updated"]
    assert total > 0
    barrier = Barrier(2)
    def clear(_):
        barrier.wait()
        response = api.patch("/api/notifications/clear-read")
        assert response.status_code == 200
        return response.json()["updated"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(clear, [1, 2])) == [0, total]
    assert api.get("/api/notifications").json() == []
    with api.db.session() as db:
        events = db.scalars(select(AuditEvent).where(AuditEvent.action == "notification.cleared")).all()
        assert len(events) == len({event.entity_id for event in events}) == total
