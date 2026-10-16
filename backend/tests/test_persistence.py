"""Migration reapplication and provisioning preserve populated databases.

This verifies SQLite only; it does not establish PostgreSQL migration/lock behavior.
"""
import subprocess
import sys
from pathlib import Path


def test_seed_rerun_preserves_existing_data_password_and_course_progress(api, monkeypatch):
    from app.config import get_settings
    from app.models import Course, Employee, KnowledgeDocument
    from app.security import password_hash

    api.headers()
    api.headers("manager")
    item = api.leave()
    assert api.decide(item).status_code == 200
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


def test_seed_rerun_preserves_completed_course_and_does_not_notify_again(api):
    from app.models import Course

    with api.db.session() as db:
        right = db.get(Course, 1).correct_index
    assert api.post("/api/courses/1/complete", {"answer_index": right}).status_code == 200
    before = api.db.snapshot()
    api.db.seed()
    assert api.db.snapshot() == before
    assert api.get("/api/courses/1").json()["completed"] is True


def test_alembic_upgrade_preserves_populated_database_and_check_has_no_drift(api):
    from app.models import Course

    item = api.leave()
    assert api.decide(item).status_code == 200
    with api.db.session() as db:
        right = db.get(Course, 1).correct_index
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
