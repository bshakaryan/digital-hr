"""Migration reapplication and provisioning preserve populated PostgreSQL schemas."""
from datetime import datetime, timezone
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text
import pytest
from alembic import command


def test_sequential_approval_migration_preserves_populated_0001_database(postgres_schema):
    backend = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0001"], cwd=backend,
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with postgres_schema.engine.begin() as connection:
        connection.execute(text("INSERT INTO employees VALUES (2,'manager@example.com','hash','Manager','manager','Demo','Manager','Team',NULL,'2020-01-01',10)"))
        connection.execute(text("INSERT INTO employees VALUES (1,'employee@example.com','hash','Employee','employee','Demo','Role','Team',2,'2024-01-01',10)"))
        connection.execute(text("INSERT INTO leave_requests VALUES (10,1,'2027-01-01','2027-01-02','keep me','submitted',1,'2026-10-16T00:00:00Z','legacy-key','legacy-hash')"))
        connection.execute(text("INSERT INTO request_history VALUES (10,10,1,'submitted','keep history','2026-10-16T00:00:00Z')"))
        connection.execute(text("INSERT INTO leave_requests VALUES (12,1,'2026-10-01','2026-10-03','old approval','approved',3,'2026-10-16T00:00:00Z','old-approved','legacy-hash')"))

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend,
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with postgres_schema.engine.begin() as connection:
        assert connection.execute(text("SELECT status, comment FROM leave_requests WHERE id=10")).one() == ("submitted", "keep me")
        assert connection.execute(text("SELECT status, comment FROM request_history WHERE id=10")).one() == ("submitted", "keep history")
        assert connection.execute(text("SELECT leave_balance FROM employees WHERE id=1")).one() == (10,)
        assert connection.scalar(text("SELECT COUNT(*) FROM leave_deductions")) == 0
        assert connection.execute(text("SELECT status,days_count FROM leave_requests WHERE id=12")).one() == ("approved", 3)
        assert connection.scalar(text("SELECT COUNT(*) FROM zup_deliveries")) == 0
        connection.execute(text("INSERT INTO leave_requests (id,employee_id,start_date,end_date,comment,status,version,created_at,idempotency_key,payload_hash,days_count,excluded_dates_json,calendar_version) VALUES (11,1,'2027-02-01','2027-02-02','new stage','manager_approved',2,'2026-10-16T00:00:00Z','new-stage-key','new-stage-hash',2,'[]','legacy-unquoted')"))
        connection.execute(text("INSERT INTO leave_deductions (request_id,employee_id,actor_id,days,created_at) VALUES (10,1,2,2,'2026-10-16T00:00:00Z')"))
        assert connection.execute(text("SELECT request_id, employee_id, actor_id, days FROM leave_deductions")).one() == (10, 1, 2, 2)


def test_seed_rerun_preserves_existing_data_password_and_course_progress(api, monkeypatch):
    from app.config import get_settings
    from app.models import Course, Employee, KnowledgeDocument
    from app.security import password_hash

    api.headers()
    api.headers("manager")
    item = api.leave()
    manager_approved = api.decide(item).json()
    assert manager_approved["status"] == "manager_approved"
    assert api.decide(manager_approved, "hr").status_code == 200
    assert api.post("/api/courses/1/progress", {"progress": 67}).status_code == 200
    with api.db.session() as db:
        employee = db.get(Employee, 1)
        employee.full_name = "Retained profile name"
        employee.leave_balance = 7
        employee.password_hash = password_hash.hash("changed-existing-password-2026")
        db.get(Course, 1).content = "Retained edited course material"
        db.get(KnowledgeDocument, 1).content = "Retained edited knowledge material"
        db.commit()
    before = api.db.snapshot()
    monkeypatch.setenv("DEMO_PASSWORD", "different-provisioning-password-2026")
    get_settings.cache_clear()
    api.db.seed()
    api.db.seed()
    assert api.db.snapshot() == before
    assert api.get("/api/me").json()["full_name"] == "Retained profile name"
    assert api.get("/api/courses/1").json()["progress"] == 67
    for password, status in (("changed-existing-password-2026", 200), (api.db.password, 401), ("different-provisioning-password-2026", 401)):
        response = api.client.post("/api/auth/login", json={"email": "employee@example.com", "password": password})
        assert response.status_code == status


def test_http_migration_preserves_existing_0003_deduction_without_reexport(postgres_schema):
    backend = Path(__file__).resolve().parents[1]
    for revision in ("0003", "head"):
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision], cwd=backend,
            capture_output=True, text=True, timeout=30, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
        if revision == "0003":
            with postgres_schema.engine.begin() as connection:
                connection.execute(text("INSERT INTO employees VALUES (1,'employee@example.com','hash','Retained','employee','Demo','Role','Team',NULL,'2024-01-01',18)"))
                connection.execute(text("INSERT INTO leave_requests VALUES (10,1,'2027-01-01','2027-01-05','keep approval','approved',3,'2026-10-16T00:00:00Z','kept-key','kept-hash')"))
                connection.execute(text("INSERT INTO leave_deductions VALUES (7,10,1,1,5,'2026-10-16T00:00:00Z')"))
                connection.execute(text("INSERT INTO request_history VALUES (8,10,1,'approved','keep history','2026-10-16T00:00:00Z')"))
    with postgres_schema.engine.connect() as connection:
        assert connection.execute(text("SELECT * FROM leave_deductions")).one() == (7, 10, 1, 1, 5, datetime(2026, 10, 16, tzinfo=timezone.utc))
        assert connection.execute(text("SELECT status,version,days_count,calendar_version FROM leave_requests")).one() == ("approved", 3, 5, "legacy-deducted")
        assert connection.execute(text("SELECT full_name,leave_balance,zup_id FROM employees")).one() == ("Retained", 18, "demo-1")
        assert connection.execute(text("SELECT comment FROM request_history")).one() == ("keep history",)
        assert connection.scalar(text("SELECT COUNT(*) FROM zup_deliveries")) == 0


def test_seed_rerun_preserves_completed_course_and_does_not_notify_again(api):
    from app.models import Course

    with api.db.session() as db:
        right = db.get(Course, 1).correct_index
    assert api.post("/api/courses/1/progress", {"progress": 70}).status_code == 200
    assert api.post("/api/courses/1/complete", {"answer_index": right}).status_code == 200
    before = api.db.snapshot()
    api.db.seed()
    assert api.db.snapshot() == before
    assert api.get("/api/courses/1").json()["completed"] is True


def test_alembic_upgrade_preserves_populated_database_and_check_has_no_drift(api):
    from app.models import Course

    item = api.leave()
    manager_approved = api.decide(item).json()
    assert api.decide(manager_approved, "hr").status_code == 200
    with api.db.session() as db:
        right = db.get(Course, 1).correct_index
    assert api.post("/api/courses/1/progress", {"progress": 70}).status_code == 200
    assert api.post("/api/courses/1/complete", {"answer_index": right}).status_code == 200
    notification = api.get("/api/notifications").json()[0]
    assert api.patch(f"/api/notifications/{notification['id']}/read").status_code == 200
    before = api.db.snapshot()
    backend = Path(__file__).resolve().parents[1]
    for arguments in (("upgrade", "head"), ("check",)):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *arguments], cwd=backend,
            capture_output=True, text=True, timeout=30, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert api.db.snapshot() == before
    assert api.get(f"/api/requests/{item['id']}").json()["status"] == "approved"
    assert api.get("/api/courses/1").json()["completed"] is True


@pytest.mark.parametrize("repair", ["migration", "seed"])
def test_explicit_seed_ids_do_not_collide_or_rewind_sequences(api, repair):
    tables = ("employees", "courses", "knowledge_documents")
    before = api.db.snapshot()

    def run_repair():
        if repair == "migration":
            command.downgrade(api.db.config, "0007")
            command.upgrade(api.db.config, "head")
        else:
            api.db.seed()

    with api.db.engine.begin() as connection:
        for table in tables:
            connection.execute(text(f"SELECT setval('{table}_id_seq', 1, false)"))
    run_repair()
    assert api.db.snapshot() == before
    with api.db.engine.begin() as connection:
        for table in tables:
            maximum = connection.scalar(text(f"SELECT MAX(id) FROM {table}"))
            assert connection.scalar(text(f"SELECT nextval('{table}_id_seq')")) > maximum
            connection.execute(text(f"SELECT setval('{table}_id_seq', 10000, true)"))
    run_repair()
    assert api.db.snapshot() == before
    with api.db.engine.begin() as connection:
        for table in tables:
            assert connection.scalar(text(f"SELECT nextval('{table}_id_seq')")) == 10001
