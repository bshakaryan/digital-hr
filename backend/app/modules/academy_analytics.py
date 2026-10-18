"""Read-only learning metrics from assignments and existing audit events."""
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditEvent, Course, CourseAssignment, Employee
from app.modules.integrations import DemoZupFixtures


def activity_actions() -> tuple[str, ...]:
    actions = ("course.progressed", "course.completed")
    if get_settings().zup_mode == "mock":
        actions += ("demo.course.progressed", "demo.course.completed")
    return actions


def reference_date() -> date:
    settings = get_settings()
    return settings.academy_demo_as_of if settings.zup_mode == "mock" else date.today()


def assignment_status(assignment: CourseAssignment, as_of: date) -> tuple[str, bool]:
    status = "completed" if assignment.completed else "in_progress" if assignment.progress > 0 else "not_started"
    return status, bool(assignment.deadline and assignment.deadline < as_of and not assignment.completed)


def rows_for(db: Session, employees: list[Employee], as_of: date) -> list[dict]:
    ids = [employee.id for employee in employees]
    if not ids:
        return []
    people = {employee.id: employee for employee in employees}
    pairs = db.execute(select(CourseAssignment, Course).join(Course, Course.id == CourseAssignment.course_id)
        .where(CourseAssignment.employee_id.in_(ids), Course.status == "published")
        .order_by(CourseAssignment.employee_id, Course.id)).all()
    events = db.scalars(select(AuditEvent).where(AuditEvent.actor_id.in_(ids), AuditEvent.entity_type == "course",
        AuditEvent.action.in_(activity_actions()))).all()
    activity: dict[tuple[int, int], list[AuditEvent]] = defaultdict(list)
    for event in events:
        activity[(event.actor_id, event.entity_id)].append(event)
    rows = []
    for assignment, course in pairs:
        employee = people[assignment.employee_id]
        status, overdue = assignment_status(assignment, as_of)
        history = activity[(employee.id, course.id)]
        completion = [event.created_at for event in history if event.action in ("course.completed", "demo.course.completed")]
        rows.append({"employee_id": employee.id, "employee_name": employee.full_name,
            "department": employee.department, "course_id": course.id, "course_title": course.title,
            "category": course.category, "learning_track": assignment.learning_track,
            "progress": assignment.progress, "deadline": assignment.deadline,
            "status": status, "overdue": overdue,
            "completed_at": min(completion) if completion else None,
            "last_activity_at": max((event.created_at for event in history), default=None)})
    return rows


def employee_profile(employee: Employee, rows: list[dict]) -> dict:
    own = [row for row in rows if row["employee_id"] == employee.id]
    counts = Counter(row["status"] for row in own)
    completed = counts["completed"]
    xp = completed * 100  # Same unique-completion rule as /courses/rewards.
    return {"employee_id": employee.id, "employee_name": employee.full_name,
        "department": employee.department, "position": employee.position,
        "manager_name": employee.manager_name, "total_assigned": len(own),
        "completed": completed, "in_progress": counts["in_progress"],
        "not_started": counts["not_started"], "overdue": sum(row["overdue"] for row in own),
        "completion_rate": round(completed * 100 / len(own), 1) if own else 0.0,
        "xp": xp, "level": 1 + xp // 100,
        "badges": (["Первый курс"] if completed >= 1 else []) + (["Три курса"] if completed >= 3 else []),
        "assignments": own}


def overview(db: Session, as_of: date) -> dict:
    employees = db.scalars(select(Employee).where(Employee.zup_id.in_([p.zup_id for p in DemoZupFixtures().employees()])).order_by(Employee.full_name)).all()
    rows = rows_for(db, employees, as_of)
    counts = Counter(row["status"] for row in rows)
    course_totals: dict[int, dict] = {}
    for row in rows:
        bucket = course_totals.setdefault(row["course_id"], {"course_id": row["course_id"],
            "course_title": row["course_title"], "total": 0, "completed": 0})
        bucket["total"] += 1
        bucket["completed"] += row["status"] == "completed"
    for bucket in course_totals.values():
        bucket["rate"] = round(bucket["completed"] * 100 / bucket["total"], 1)
    overdue_departments = Counter(row["department"] for row in rows if row["overdue"])
    ids = [employee.id for employee in employees]
    events = db.scalars(select(AuditEvent).where(AuditEvent.actor_id.in_(ids),
        AuditEvent.entity_type == "course", AuditEvent.action.in_(activity_actions()))).all() if ids else []
    daily = Counter(event.created_at.date() for event in events)
    return {"as_of": as_of, "total_demo_employees": len(employees),
        "published_courses": len(db.scalars(select(Course.id).where(Course.status == "published")).all()),
        "total_assignments": len(rows), "completion_rate": round(counts["completed"] * 100 / len(rows), 1) if rows else 0.0,
        "overdue_assignments": sum(row["overdue"] for row in rows),
        "status_counts": {key: counts[key] for key in ("completed", "in_progress", "not_started")},
        "course_completion": sorted(course_totals.values(), key=lambda bucket: (-bucket["total"], bucket["course_title"])),
        "activity_includes_demo": any(event.action.startswith("demo.") and as_of - timedelta(days=13) <= event.created_at.date() <= as_of for event in events),
        "daily_activity": [{"date": as_of - timedelta(days=day), "count": daily[as_of - timedelta(days=day)]} for day in range(13, -1, -1)],
        "overdue_by_department": [{"department": name, "count": count} for name, count in sorted(overdue_departments.items())],
        "assignments": rows, "employees": [employee_profile(employee, rows) for employee in employees]}
