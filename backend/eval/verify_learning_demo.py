"""Read-only Compose check of populated Academy metrics, RBAC and course AI."""
import os

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import Course, CourseAssignment, Employee


def main():
    client = httpx.Client(base_url="http://localhost:8000/api", timeout=30)

    def token(email):
        response = client.post("/auth/login", json={"email": email, "password": os.environ["DEMO_PASSWORD"]})
        response.raise_for_status()
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    hr = token("hr@example.com")
    employee = token("employee@example.com")
    manager = token("manager@example.com")
    data_response = client.get("/courses/analytics", headers=hr)
    data_response.raise_for_status()
    data = data_response.json()
    with Session(get_engine()) as db:
        demo_ids = list(db.scalars(select(Employee.id).where(Employee.zup_id.like("demo-%"))))
        published = list(db.scalars(select(Course.id).where(Course.status == "published")))
        pairs = db.execute(select(CourseAssignment, Course).join(Course, Course.id == CourseAssignment.course_id)
            .where(CourseAssignment.employee_id.in_(demo_ids), Course.status == "published")).all()
        completed = sum(assignment.completed for assignment, _ in pairs)
        overdue = sum(bool(assignment.deadline and assignment.deadline.isoformat() < data["as_of"] and not assignment.completed) for assignment, _ in pairs)
        assert data["total_demo_employees"] == len(demo_ids)
        assert data["published_courses"] == len(published)
        assert data["total_assignments"] == len(pairs)
        assert data["completion_rate"] == round(100 * completed / len(pairs), 1)
        assert data["overdue_assignments"] == overdue
        assert sum(data["status_counts"].values()) == len(pairs)
        profile = client.get("/courses/analytics/employees/1", headers=hr).json()
        actual_completed = db.scalar(select(func.count()).select_from(CourseAssignment).where(
            CourseAssignment.employee_id == 1, CourseAssignment.completed.is_(True)))
        assert profile["xp"] == client.get("/courses/rewards", headers=employee).json()["xp"] == actual_completed * 100
        assert profile["total_assigned"] == len(profile["assignments"])
        assert profile["completion_rate"] == round(100 * profile["completed"] / profile["total_assigned"], 1)
        assert client.get("/courses/analytics", headers=employee).status_code == 403
        assert client.get("/courses/analytics/employees/4", headers=employee).status_code == 403
        assert client.get("/courses/analytics/employees/1", headers=manager).status_code == 200
        assert client.get("/courses/analytics/employees/4", headers=manager).status_code == 404
        assert [p["employee_id"] for p in client.get("/courses/analytics/employees", headers=manager).json()] == [1]
        course = db.scalar(select(Course).where(Course.demo_code == "DEMO-LOG-03"))
        answer = client.post(f"/courses/{course.id}/ask", headers=employee,
            json={"question": "Что означает статус отправления?"})
        answer.raise_for_status()
        ai = answer.json()
        assert ai["sources"] and any(source.get("document_code") == "OPS-02" for source in ai["sources"])
        assert client.post(f"/courses/{course.id}/ask", headers=manager,
            json={"question": "Что означает статус отправления?"}).status_code == 404
        print({"demo_employees": len(demo_ids), "published_courses": len(published),
            "assignments": len(pairs), "completed": completed, "overdue": overdue,
            "completion_rate": data["completion_rate"], "course_ai_source": ai["sources"][0].get("document_code"),
            "rbac": "passed", "xp": profile["xp"]})


if __name__ == "__main__":
    main()
