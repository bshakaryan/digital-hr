from calendar import monthrange
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, LeaveRequest
from app.modules.requests import visible_requests
from app.schemas import CalendarAbsence, CalendarEmployee, EmployeeCalendar
from app.security import current_user, visible_employee_ids

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("", response_model=EmployeeCalendar)
def calendar(
    month: Annotated[str, Query(pattern=r"^[1-9]\d{3}-(0[1-9]|1[0-2])$")],
    response: Response,
    user: Employee = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Shared leave dates for authenticated colleagues, without private request fields."""
    year, number = map(int, month.split("-"))
    first = date(year, number, 1)
    last = date(year, number, monthrange(year, number)[1])
    profiles = set(db.scalars(visible_employee_ids(db, user)))
    request_ids = set(db.scalars(select(LeaveRequest.id).where(
        visible_requests(user), LeaveRequest.start_date <= last, LeaveRequest.end_date >= first,
    )))
    people = db.execute(select(Employee.id, Employee.full_name, Employee.department).order_by(Employee.id)).all()
    absences = db.execute(select(
        LeaveRequest.id, LeaveRequest.employee_id, LeaveRequest.start_date, LeaveRequest.end_date, LeaveRequest.status,
    ).where(
        LeaveRequest.status.in_(("submitted", "manager_approved", "approved", "cancellation_requested")),
        LeaveRequest.start_date <= last, LeaveRequest.end_date >= first,
    ).order_by(LeaveRequest.id.desc())).all()
    response.headers["Cache-Control"] = "private, no-store"
    return EmployeeCalendar(
        month=month,
        employees=[CalendarEmployee(**person._mapping, can_open_profile=person.id in profiles) for person in people],
        absences=[CalendarAbsence(**item._mapping, can_open_request=item.id in request_ids) for item in absences],
    )
