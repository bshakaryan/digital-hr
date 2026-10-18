"""Company directory visibility and synthetic hierarchy on isolated PostgreSQL."""

from collections import Counter

from sqlalchemy import select


def test_directory_requires_authentication(api):
    assert api.client.get("/api/directory").status_code == 401


def test_directory_is_work_only_and_detailed_profiles_stay_restricted(api):
    from app.models import Employee
    allowed = {"id", "full_name", "position", "department", "manager_id", "can_open_profile", "is_demo"}
    for actor in ("employee", "manager", "hr"):
        response = api.get("/api/directory", actor)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
        people = response.json()
        assert len(people) == 4
        assert all(set(person) == allowed for person in people)
        assert {person["id"] for person in people} == {1, 2, 3, 4}
        assert all("@" not in str(person) for person in people)
        authorized = {person["id"] for person in api.get("/api/employees", actor).json()}
        assert {person["id"] for person in people if person["can_open_profile"]} == authorized
    assert api.get("/api/employees/2", "employee").status_code == 404
    assert api.get("/api/employees/1", "manager").status_code == 200
    with api.db.session() as db:
        assert db.scalar(select(Employee).where(Employee.zup_id == "people-001")) is None


def test_demo_provisioning_is_idempotent_with_real_reporting_links(api):
    from app.models import CourseAssignment, Employee
    from app.provision_jana_people import provision

    with api.db.session() as db:
        before = {person.zup_id: (person.id, person.password_hash) for person in db.scalars(select(Employee))}
        assert provision(db) == 30
        db.commit()
    with api.db.session() as db:
        assert provision(db) == 0
        db.commit()
        people = db.scalars(select(Employee)).all()
        by_id = {person.id: person for person in people}
        synthetic = [person for person in people if person.zup_id and person.zup_id.startswith("people-")]
        assert len(synthetic) == 30
        assert len({person.zup_id for person in synthetic}) == 30
        assert len({person.email for person in people}) == len(people)
        assert {person.zup_id: (person.id, person.password_hash) for person in people if person.zup_id in before} == before
        assert {person.department for person in synthetic} == {"Руководство", "Логистика", "Складские операции", "Клиентский сервис", "HR", "IT", "Финансы"}
        assert all(person.manager_id is None or person.manager_id in by_id for person in synthetic)
        for person in synthetic:
            seen = set()
            current = person
            while current.manager_id is not None:
                assert current.id not in seen
                seen.add(current.id)
                current = by_id[current.manager_id]
            assert len(seen) <= 3  # CEO plus at most three further levels.
        assert db.scalar(select(CourseAssignment.id).where(CourseAssignment.employee_id == synthetic[0].id)) is None
    api.db.seed()
    with api.db.session() as db:
        assert db.scalar(select(CourseAssignment.id).where(CourseAssignment.employee_id == synthetic[0].id)) is None
    hr = api.get("/api/directory", "hr").json()
    employee = api.get("/api/directory", "employee").json()
    assert len(hr) == len(employee) == 34
    assert Counter(person["department"] for person in hr)["Логистика"] >= 5
    assert {person["manager_id"] for person in hr if person["manager_id"] is not None} <= {person["id"] for person in hr}
    synthetic_id = next(person["id"] for person in hr if person["is_demo"])
    assert api.get(f"/api/employees/{synthetic_id}", "hr").status_code == 200
    assert api.get(f"/api/employees/{synthetic_id}", "employee").status_code == 404
    assert api.get("/api/requests", "employee").status_code == 200
    assert api.get("/api/courses", "employee").status_code == 200
