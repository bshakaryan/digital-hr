import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, LeaveRequest, RequestHistory
from app.modules.audit import record
from app.modules.notifications import notify
from app.schemas import HistoryOut, RequestCreate, RequestDecision, RequestOut
from app.security import current_user, visible_employee_ids

router = APIRouter(prefix="/requests", tags=["requests"])


def present(db: Session, item: LeaveRequest) -> RequestOut:
    employee = db.get(Employee, item.employee_id)
    history = db.execute(select(RequestHistory, Employee.full_name).join(Employee, Employee.id == RequestHistory.actor_id).where(RequestHistory.request_id == item.id).order_by(RequestHistory.id)).all()
    return RequestOut(
        id=item.id, employee_id=item.employee_id, employee_name=employee.full_name,
        start_date=item.start_date, end_date=item.end_date, comment=item.comment,
        status=item.status, version=item.version, created_at=item.created_at,
        history=[HistoryOut(status=h.status, actor_name=name, comment=h.comment, created_at=h.created_at) for h, name in history],
    )


def accessible(db: Session, user: Employee, request_id: int):
    item = db.scalar(select(LeaveRequest).where(LeaveRequest.id == request_id, LeaveRequest.employee_id.in_(visible_employee_ids(db, user))))
    if item is None:
        raise HTTPException(404, "Заявка не найдена")
    return item


@router.get("", response_model=list[RequestOut])
def requests(user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(LeaveRequest).where(LeaveRequest.employee_id.in_(visible_employee_ids(db, user))).order_by(LeaveRequest.id.desc())).all()
    return [present(db, item) for item in items]


@router.post("", response_model=RequestOut, status_code=201)
def create_request(data: RequestCreate, idempotency_key: Annotated[str, Header(min_length=8, max_length=128)], user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    digest = hashlib.sha256(data.model_dump_json().encode()).hexdigest()

    def previous():
        return db.scalar(select(LeaveRequest).where(LeaveRequest.employee_id == user.id, LeaveRequest.idempotency_key == idempotency_key))

    item = previous()
    if item:
        if item.payload_hash != digest:
            raise HTTPException(409, "Этот ключ уже использован с другими данными")
        return present(db, item)
    item = LeaveRequest(employee_id=user.id, start_date=data.start_date, end_date=data.end_date, comment=data.comment, idempotency_key=idempotency_key, payload_hash=digest)
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        # Unique constraint is the final protection against concurrent retries.
        db.rollback()
        item = previous()
        if item is None or item.payload_hash != digest:
            raise HTTPException(409, "Конфликт повторной команды")
        return present(db, item)
    db.add(RequestHistory(request_id=item.id, actor_id=user.id, status="submitted", comment=data.comment))
    record(db, user.id, "request.created", "request", item.id)
    notify(db, user.id, "request_submitted", "Заявка отправлена", f"Заявка №{item.id} ожидает решения человека.")
    approvers = db.scalars(select(Employee).where(or_(Employee.role == "hr_admin", Employee.id == user.manager_id), Employee.id != user.id)).all()
    for approver in approvers:
        notify(db, approver.id, "request_review", "Новая заявка на отпуск", f"{user.full_name}: заявка №{item.id} ожидает рассмотрения.")
    db.commit()
    return present(db, item)


@router.get("/{request_id}", response_model=RequestOut)
def get_request(request_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    return present(db, accessible(db, user, request_id))


@router.patch("/{request_id}/status", response_model=RequestOut)
def decide(request_id: int, data: RequestDecision, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    item = accessible(db, user, request_id)
    owner = db.get(Employee, item.employee_id)
    if user.id == item.employee_id or not (user.role == "hr_admin" or (user.role == "manager" and owner.manager_id == user.id)):
        raise HTTPException(403, "Нельзя принять решение по этой заявке")
    result = db.execute(update(LeaveRequest).where(LeaveRequest.id == request_id, LeaveRequest.version == data.version, LeaveRequest.status == "submitted").values(status=data.status, version=LeaveRequest.version + 1).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Заявка уже изменена. Обновите список")
    db.add(RequestHistory(request_id=request_id, actor_id=user.id, status=data.status, comment=data.comment))
    record(db, user.id, f"request.{data.status}", "request", request_id)
    label = "одобрена" if data.status == "approved" else "отклонена"
    notify(db, item.employee_id, "request_status", f"Заявка {label}", f"Заявка №{item.id}: решение принял(а) {user.full_name}. {data.comment}")
    db.commit()
    db.refresh(item)
    return present(db, item)
