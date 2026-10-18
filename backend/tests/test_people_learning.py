"""Whole-directory learning, preservation, permissions and atomic retry."""
import pytest
from sqlalchemy import select


def prepared(api):
    from app.models import KnowledgeDocument, KnowledgeFile
    from app.provision_academy_demo import COURSES, provision as academy
    from app.provision_jana_people import provision as people
    with api.db.session() as db:
        people(db)
        files = {}
        for index, code in enumerate(sorted({code for spec in COURSES for code in spec.files})):
            file = KnowledgeFile(sha256=f"{index + 1:064x}", filename=f"{code}.docx", title=code,
                document_code=code, version="test", language="ru", classification="synthetic_demo",
                source_note="DEMO / SYNTHETIC", access_scope="all",
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                size_bytes=1, original_bytes=b"x", uploaded_by=3)
            db.add(file)
            db.flush()
            files[code] = file
        for spec in COURSES:
            db.add(KnowledgeDocument(title=spec.title, section=spec.section, content=spec.evidence,
                keywords="", access_scope="all", file_id=files[spec.files[0]].id, chunk_index=0))
        db.commit()
    academy()


def test_whole_directory_learning_preserves_old_data_and_repeats(api):
    from app import provision_people_learning as demo
    from app.models import Course, CourseAssignment, Employee
    from app.security import issue_token
    prepared(api)
    with api.db.session() as db:
        person = db.scalar(select(Employee).where(Employee.zup_id == "people-001"))
        course_id = db.scalar(select(Course.id).where(Course.demo_code == "DEMO-ONB-01"))
        db.add(CourseAssignment(employee_id=person.id, course_id=course_id,
            progress=45, completed=False, deadline=None, learning_track="legacy"))
        db.commit()
    before = api.db.snapshot("course_assignments", "audit_events", "notifications", "employees", "leave_requests")
    result = demo.provision()
    assert result["employees"] == 30
    assert result["new_assignments"] > 140 and result["existing_assignments"] == 1
    assert min(result[k] for k in ("completed", "in_progress", "not_started")) > 20
    after = api.db.snapshot(*before)
    for name, original in before.items():
        assert after[name][:len(original)] == original
    overview = api.get("/api/courses/analytics", "hr").json()
    assert overview["total_demo_employees"] == len(overview["employees"]) == 34
    assert all(p["total_assigned"] >= 4 for p in overview["employees"] if p["employee_id"] > 4)
    assert overview["total_assignments"] == sum(p["total_assigned"] for p in overview["employees"])
    assert overview["status_counts"]["completed"] == sum(p["completed"] for p in overview["employees"])
    assert 30 < overview["completion_rate"] < 70
    assert len(overview["overdue_by_department"]) >= 6
    assert all(day["count"] > 0 for day in overview["daily_activity"])
    assert overview["activity_includes_demo"] is True
    with api.db.session() as db:
        warehouse = db.scalar(select(Employee).where(Employee.zup_id == "people-016"))
        person_id, manager_id = warehouse.id, warehouse.manager_id
        codes = set(db.scalars(select(Course.demo_code).join(CourseAssignment,
            CourseAssignment.course_id == Course.id).where(CourseAssignment.employee_id == person_id)))
        assert {"DEMO-SAFE-01", "DEMO-SAFE-02", "DEMO-SAFE-03"} <= codes
    own_headers = {"Authorization": "Bearer " + issue_token(person_id)}
    manager_headers = {"Authorization": "Bearer " + issue_token(manager_id)}
    rewards = api.client.get("/api/courses/rewards", headers=own_headers).json()
    profile = api.client.get(f"/api/courses/analytics/employees/{person_id}", headers=manager_headers)
    assert profile.status_code == 200 and profile.json()["xp"] == rewards["xp"]
    assert api.get(f"/api/courses/analytics/employees/{person_id}", "employee").status_code == 403
    assert api.get(f"/api/courses/analytics/employees/{person_id}", "manager").status_code == 404
    assert api.get("/api/courses/analytics", "manager").status_code == 403
    courses = api.client.get("/api/courses", headers=own_headers).json()
    active = next(c for c in courses if not c["completed"])
    assert api.client.post(f"/api/courses/{active['id']}/progress", headers=own_headers,
        json={"progress":90}).status_code == 200
    snapshot = api.db.snapshot()
    repeated = demo.provision()
    assert repeated["new_assignments"] == repeated["activity_events"] == 0
    assert api.db.snapshot() == snapshot


def test_learning_setup_rolls_back_partial_services_and_can_retry(api, monkeypatch):
    from app import provision_people_learning as demo
    prepared(api)
    before = api.db.snapshot()
    original, calls = demo.complete, 0
    def interrupted(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("Simulated interruption")
        return original(*args, **kwargs)
    monkeypatch.setattr(demo, "complete", interrupted)
    with pytest.raises(RuntimeError, match="Simulated interruption"):
        demo.provision()
    assert api.db.snapshot() == before
    monkeypatch.setattr(demo, "complete", original)
    assert demo.provision()["new_assignments"] > 140


def test_learning_setup_refuses_real_and_changed_materials_or_identities(api, monkeypatch):
    from app import provision_people_learning as demo
    from app.config import get_settings
    from app.models import Employee, KnowledgeFile
    prepared(api)
    with api.db.session() as db:
        db.scalar(select(Employee).where(Employee.zup_id == "people-001")).full_name = "Edited identity"
        db.commit()
    before = api.db.snapshot()
    with pytest.raises(RuntimeError, match="exact 30"):
        demo.provision()
    assert api.db.snapshot() == before
    with api.db.session() as db:
        db.scalar(select(Employee).where(Employee.zup_id == "people-001")).full_name = "Ерлан Садыков"
        db.scalar(select(KnowledgeFile).limit(1)).classification = "external_legal_snapshot"
        db.commit()
    before = api.db.snapshot()
    with pytest.raises(RuntimeError, match="Only synthetic materials"):
        demo.provision()
    assert api.db.snapshot() == before
    monkeypatch.setenv("ZUP_MODE", "real")
    monkeypatch.setenv("ZUP_BASE_URL", "https://zup.example.test/hs/jana/v1")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="ZUP_MODE=mock"):
            demo.provision()
    finally:
        get_settings.cache_clear()
