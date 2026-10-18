from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee
from app.modules.leave_balance import present_profile
from app.schemas import DirectoryPerson, Profile
from app.security import current_user, visible_employee_ids

router = APIRouter(prefix="/employees", tags=["employees"])
directory_router = APIRouter(prefix="/directory", tags=["directory"])


@directory_router.get("", response_model=list[DirectoryPerson])
def directory(response: Response, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "private, no-store"
    detailed_ids = set(db.scalars(visible_employee_ids(db, user)).all())
    people = db.scalars(select(Employee).order_by(Employee.full_name, Employee.id)).all()
    return [DirectoryPerson(id=person.id, full_name=person.full_name, position=person.position,
        department=person.department, manager_id=person.manager_id,
        can_open_profile=person.id in detailed_ids, is_demo=bool(person.zup_id and person.zup_id.startswith("people-")))
        for person in people]


@router.get("", response_model=list[Profile])
def employees(user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    found = db.scalars(select(Employee).where(Employee.id.in_(visible_employee_ids(db, user))).order_by(Employee.id)).all()
    return [present_profile(db, employee) for employee in found]


@router.get("/{employee_id}", response_model=Profile)
def employee(employee_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    found = db.scalar(select(Employee).where(Employee.id == employee_id, Employee.id.in_(visible_employee_ids(db, user))))
    if found is None:
        raise HTTPException(404, "Профиль не найден")
    return present_profile(db, found)
