"""Atomic, repeatable synthetic learning scenarios for the 30 Jana People.

Run after Academy and workspace setup. Existing assignments and the four core
accounts are preserved. Historical demo events are explicitly labeled.
"""
import json
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.models import AuditEvent, Course, CourseAssignment, CourseMaterial, Employee, KnowledgeFile
from app.modules.academy import assign_course, complete, progress
from app.modules.academy_analytics import reference_date
from app.modules.integrations import DemoZupFixtures
from app.provision_academy_demo import COURSES
from app.schemas import Completion, CourseAssign, Progress

DEPARTMENT_COURSES = {
    "Руководство": ("DEMO-ONB-02", "DEMO-LOG-03", "DEMO-CS-02"),
    "Логистика": ("DEMO-LOG-01", "DEMO-LOG-02", "DEMO-LOG-04"),
    "Складские операции": ("DEMO-SAFE-01", "DEMO-SAFE-02", "DEMO-SAFE-03", "DEMO-LOG-01"),
    "Клиентский сервис": ("DEMO-CS-01", "DEMO-CS-02", "DEMO-LOG-02"),
    "HR": ("DEMO-ONB-02", "DEMO-CS-02"),
    "IT": ("DEMO-CS-02", "DEMO-LOG-03"),
    "Финансы": ("DEMO-CS-02", "DEMO-LOG-03"),
}


def curriculum(person):
    codes = ("DEMO-ONB-01", "DEMO-ONB-03") + DEPARTMENT_COURSES[person.department]
    if person.role == "manager" and "DEMO-ONB-02" not in codes:
        codes += ("DEMO-ONB-02",)
    return codes


def planned_progress(index, position, total):
    cohort = index % 6
    if cohort == 0 or (cohort == 1 and position < total - 1):
        return 100
    if cohort == 1:
        return 85
    if cohort == 2:
        return 100 if position < 2 else 55 if position == 2 else 0
    if cohort == 3:
        return 100 if position == 0 else (25, 45, 70)[position % 3] if position < total - 1 else 0
    if cohort == 4:
        return 100 if position == 0 else 35 if position == 1 else 0
    return (20, 60)[position] if position < 2 else 0


def add_history(db, employee_id, course_id, index, position, saved_progress, as_of):
    if saved_progress == 0:
        return 0
    # Modeled study sessions span the same 14-day window as the HR overview.
    end = 4 + (index * 3 + position) % 10
    offsets = (max(0, end - 4), end - 2, end) if saved_progress >= 55 else (end,)
    for step, offset in enumerate(offsets):
        day = as_of - timedelta(days=13 - offset)
        action = "demo.course.completed" if saved_progress == 100 and step == len(offsets) - 1 else "demo.course.progressed"
        db.add(AuditEvent(actor_id=employee_id, action=action, entity_type="course", entity_id=course_id,
            created_at=datetime.combine(day, time(7 + index % 9, 10 + step * 15), timezone.utc)))
    return len(offsets)


def provision():
    if get_settings().zup_mode != "mock":
        raise RuntimeError("People learning requires ZUP_MODE=mock")
    as_of = reference_date()
    result = {"employees": 30, "new_assignments": 0, "existing_assignments": 0,
              "completed": 0, "in_progress": 0, "not_started": 0, "activity_events": 0}
    # Service-level commits release savepoints, while this outer transaction
    # owns the entire seed. A failure cannot leave half-populated assignments.
    with get_engine().begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(20261018, 34)"))
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            fixtures = [p for p in DemoZupFixtures().employees() if p.zup_id.startswith("people-")]
            people = {p.zup_id: p for p in db.scalars(select(Employee).where(
                Employee.zup_id.in_([p.zup_id for p in fixtures])))}
            if len(people) != 30 or any(
                    (people[p.zup_id].email, people[p.zup_id].full_name, people[p.zup_id].role, people[p.zup_id].department)
                    != (p.email, p.full_name, p.role, p.department) for p in fixtures):
                raise RuntimeError("Provision the exact 30 synthetic Jana People first")
            hr = db.scalar(select(Employee).where(Employee.zup_id == "demo-3",
                Employee.email == "hr@example.com", Employee.role == "hr_admin"))
            if hr is None:
                raise RuntimeError("Synthetic HR identity required")
            courses = {c.demo_code: c for c in db.scalars(select(Course).where(
                Course.demo_code.in_([spec.code for spec in COURSES])))}
            for spec in COURSES:
                course = courses.get(spec.code)
                if course is None or course.status != "published" or not course.description.startswith("DEMO / SYNTHETIC."):
                    raise RuntimeError(f"Published synthetic course required: {spec.code}")
                materials = db.scalars(select(KnowledgeFile.classification).join(CourseMaterial,
                    CourseMaterial.file_id == KnowledgeFile.id).where(CourseMaterial.course_id == course.id)).all()
                if not materials or any(value != "synthetic_demo" for value in materials):
                    raise RuntimeError(f"Only synthetic materials allowed: {spec.code}")
            for index, fixture in enumerate(fixtures):
                employee = people[fixture.zup_id]
                codes = curriculum(employee)
                for position, code in enumerate(codes):
                    course = courses[code]
                    if db.scalar(select(CourseAssignment.id).where(CourseAssignment.employee_id == employee.id,
                            CourseAssignment.course_id == course.id)) is not None:
                        result["existing_assignments"] += 1
                        continue
                    target = planned_progress(index, position, len(codes))
                    deadline_offset = (-9, -4, -1, 4, 8, 14, 21, 28)[(index + position * 3) % 8]
                    assign_course(course.id, CourseAssign(employee_id=employee.id,
                        deadline=as_of + timedelta(days=deadline_offset),
                        learning_track="onboarding" if code in ("DEMO-ONB-01", "DEMO-ONB-03") else "development"), hr, db)
                    if target:
                        progress(course.id, Progress(progress=70 if target == 100 else target), employee, db)
                    if target == 100:
                        complete(course.id, Completion(answer_index=course.correct_index), employee, db)
                    result["new_assignments"] += 1
                    state = "completed" if target == 100 else "in_progress" if target else "not_started"
                    result[state] += 1
                    result["activity_events"] += add_history(db, employee.id, course.id, index, position, target, as_of)
                db.commit()
    return result


if __name__ == "__main__":
    print(json.dumps(provision(), ensure_ascii=False))
