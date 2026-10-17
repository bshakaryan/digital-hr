import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import get_settings
from app.models import DocumentologDelivery, Employee, LeaveCancellation, LeaveDeduction, LeaveRequest, RequestHistory, ZupDelivery, utcnow
from app.modules.audit import record
from app.modules.leave_balance import quote_leave
from app.modules.notifications import notify
from app.modules.zup_sync import deliver, enqueue
from app.schemas import HistoryOut, LeaveCalculation, RequestCreate, RequestDecision, RequestOut
from app.security import current_user

router = APIRouter(prefix="/requests", tags=["requests"])


def approval_route(employee: Employee):
    if employee.role == "manager":
        return "manager_to_hr"
    if employee.role == "hr_admin":
        return "hr_to_manager"
    return "standard"


def final_reviewer_ids(db: Session, employee: Employee):
    reviewer_role = "manager" if employee.role == "hr_admin" else "hr_admin"
    return list(db.scalars(select(Employee.id).where(Employee.role == reviewer_role, Employee.id != employee.id)))


def review_allowed(user, employee, item):
    if not user or user.id == item.employee_id:
        return False
    route = approval_route(employee)
    if item.status == "submitted":
        return user.role == "manager" and (
            (route == "standard" and employee.manager_id == user.id) or route == "hr_to_manager")
    if item.status == "manager_approved":
        return user.role == "hr_admin" and route in ("standard", "manager_to_hr")
    if item.status == "cancellation_requested":
        return user.role == ("manager" if route == "hr_to_manager" else "hr_admin")
    return False


def visible_requests(user: Employee):
    if user.role == "hr_admin":
        return True
    if user.role == "manager":
        return or_(
            LeaveRequest.employee_id == user.id,
            LeaveRequest.employee_id.in_(select(Employee.id).where(Employee.manager_id == user.id)),
            LeaveRequest.employee_id.in_(select(Employee.id).where(Employee.role == "hr_admin")),
        )
    return LeaveRequest.employee_id == user.id


def cancellation_block_reason(db, item):
    if get_settings().zup_mode != "mock":
        return "Контракт отмены для реальной 1С ещё не согласован"
    if item.start_date <= utcnow().date():
        return "Демо поддерживает отмену только до начала отпуска"
    if not db.scalar(select(ZupDelivery.id).where(ZupDelivery.request_id == item.id)):
        return "Исторический отпуск требует ручной сверки с источником"
    if db.scalar(select(DocumentologDelivery.id).where(DocumentologDelivery.request_id == item.id)):
        return "Сначала требуется согласовать аннулирование документа Documentolog"
    return None


def present(db: Session, item: LeaveRequest, user=None) -> RequestOut:
    employee = db.get(Employee, item.employee_id)
    history = db.execute(select(RequestHistory, Employee.full_name).join(Employee, Employee.id == RequestHistory.actor_id).where(RequestHistory.request_id == item.id).order_by(RequestHistory.id)).all()
    delivery = db.scalar(select(ZupDelivery).where(ZupDelivery.request_id == item.id))
    cancellation = db.scalar(select(LeaveCancellation).where(LeaveCancellation.request_id == item.id))
    reason = cancellation_block_reason(db, item) if item.status in ("approved", "cancellation_requested") else None
    return RequestOut(
        id=item.id, employee_id=item.employee_id, employee_name=employee.full_name,
        start_date=item.start_date, end_date=item.end_date,
        days_count=item.days_count,
        excluded_dates=[] if item.calendar_version == "legacy-deducted" else json.loads(item.excluded_dates_json),
        calendar_version=item.calendar_version,
        zup_sync_status=delivery.status if delivery else "legacy" if item.status == "approved" else "not_required",
        zup_reference=delivery.reference if delivery else None, comment=item.comment,
        status=item.status, version=item.version, created_at=item.created_at,
        history=[HistoryOut(status=h.status, actor_name=name, comment=h.comment, created_at=h.created_at) for h, name in history],
        calendar_days=(item.end_date - item.start_date).days + 1,
        approval_route=approval_route(employee),
        can_review=review_allowed(user, employee, item),
        cancellation_allowed=item.status == "approved" and reason is None,
        cancellation_block_reason=reason,
        cancellation_sync_status=cancellation.status if cancellation else None,
        cancellation_reference=cancellation.reference if cancellation else None,
    )


def accessible(db: Session, user: Employee, request_id: int):
    item = db.scalar(select(LeaveRequest).where(LeaveRequest.id == request_id, visible_requests(user)))
    if item is None:
        raise HTTPException(404, "Заявка не найдена")
    return item


@router.get("", response_model=list[RequestOut])
def requests(user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(LeaveRequest).where(visible_requests(user)).order_by(LeaveRequest.id.desc())).all()
    return [present(db, item, user) for item in items]


@router.get("/review-queue", response_model=list[RequestOut])
def review_queue(user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    items = requests(user, db)
    return sorted((item for item in items if item.can_review), key=lambda item: item.history[-1].created_at if item.history else item.created_at)


@router.post("/calculate", response_model=LeaveCalculation)
def calculate(data: RequestCreate, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    ensure_no_overlap(db, user.id, data.start_date, data.end_date)
    quote, available = quote_leave(db, user, data.start_date, data.end_date)
    return LeaveCalculation(start_date=data.start_date, end_date=data.end_date,
        **quote.model_dump(exclude={"employee_id", "balance", "applied_commands"}),
        available_balance=available, balance_after=available - quote.days_count,
        sufficient_balance=available >= quote.days_count)


def ensure_no_overlap(db: Session, employee_id: int, start, end, excluding=None, statuses=("submitted", "manager_approved", "approved", "cancellation_requested")):
    query = select(LeaveRequest.id).where(LeaveRequest.employee_id == employee_id,
        LeaveRequest.status.in_(statuses), LeaveRequest.start_date <= end, LeaveRequest.end_date >= start)
    if excluding is not None:
        query = query.where(LeaveRequest.id != excluding)
    if db.scalar(query.limit(1)) is not None:
        raise HTTPException(409, "Период пересекается с действующей заявкой на отпуск")


@router.post("", response_model=RequestOut, status_code=201)
def create_request(data: RequestCreate, idempotency_key: Annotated[str, Header(min_length=8, max_length=128)], user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    digest = hashlib.sha256(data.model_dump_json().encode()).hexdigest()

    def previous():
        return db.scalar(select(LeaveRequest).where(LeaveRequest.employee_id == user.id, LeaveRequest.idempotency_key == idempotency_key))

    item = previous()
    if item:
        if item.payload_hash != digest:
            raise HTTPException(409, "Этот ключ уже использован с другими данными")
        return present(db, item, user)
    user = db.scalar(select(Employee).where(Employee.id == user.id).with_for_update())
    # Recheck after acquiring the employee lock for simultaneous creations.
    item = previous()
    if item:
        if item.payload_hash != digest:
            raise HTTPException(409, "Этот ключ уже использован с другими данными")
        return present(db, item, user)
    try:
        item = new_request(db, user, data, idempotency_key, digest)
    except IntegrityError:
        db.rollback()
        item = previous()
        if item is None or item.payload_hash != digest:
            raise HTTPException(409, "Конфликт повторной команды")
    db.commit()
    return present(db, item, user)


def new_request(db, user, data, idempotency_key, digest):
    route = approval_route(user)
    if route == "standard":
        manager = db.get(Employee, user.manager_id) if user.manager_id is not None else None
        if manager is None or manager.role != "manager":
            raise HTTPException(409, "Для сотрудника не настроен маршрут согласования с непосредственным руководителем")
        reviewers = [manager]
    else:
        reviewers = list(db.scalars(select(Employee).where(
            Employee.role == ("hr_admin" if route == "manager_to_hr" else "manager"), Employee.id != user.id)))
        if not reviewers:
            raise HTTPException(409, "Для одноэтапной заявки не настроен независимый согласующий")
    ensure_no_overlap(db, user.id, data.start_date, data.end_date)
    quote, available = quote_leave(db, user, data.start_date, data.end_date)
    if quote.days_count > available:
        raise HTTPException(409, f"Недостаточно дней отпуска: запрошено {quote.days_count}, доступно {available}")
    item = LeaveRequest(employee_id=user.id, start_date=data.start_date, end_date=data.end_date, comment=data.comment,
        status="manager_approved" if route == "manager_to_hr" else "submitted", idempotency_key=idempotency_key, payload_hash=digest,
        days_count=quote.days_count, excluded_dates_json=json.dumps([day.isoformat() for day in quote.excluded_dates]), calendar_version=quote.calendar_version)
    db.add(item)
    db.flush()
    db.add(RequestHistory(request_id=item.id, actor_id=user.id, status="submitted", comment=data.comment))
    record(db, user.id, "request.created", "request", item.id)
    reviewer_title = "HR" if route == "manager_to_hr" else "руководителя"
    notify(db, user.id, "request_submitted", "Заявка отправлена", f"Заявка №{item.id} ожидает решения {reviewer_title}.", entity_type="request", entity_id=item.id, actor_id=user.id)
    kind = "request_hr_review" if route == "manager_to_hr" else "request_manager_review"
    for reviewer in reviewers:
        notify(db, reviewer.id, kind, "Новая заявка на отпуск", f"{user.full_name}: заявка №{item.id} ожидает вашего решения.", entity_type="request", entity_id=item.id, actor_id=user.id)
    return item


@router.get("/{request_id}", response_model=RequestOut)
def get_request(request_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    return present(db, accessible(db, user, request_id), user)


@router.patch("/{request_id}/status", response_model=RequestOut)
def decide(request_id: int, data: RequestDecision, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    item = accessible(db, user, request_id)
    owner = db.scalar(select(Employee).where(Employee.id == item.employee_id).with_for_update())
    db.refresh(item)
    if user.id == item.employee_id:
        raise HTTPException(403, "Нельзя принять решение по этой заявке")
    current_status = item.status
    route = approval_route(owner)
    if current_status == "submitted":
        if not review_allowed(user, owner, item):
            if user.role == "hr_admin":
                raise HTTPException(409, "Сначала заявку должен согласовать непосредственный руководитель")
            raise HTTPException(403, "Нельзя принять решение по этой заявке")
        next_status = "manager_approved" if route == "standard" and data.status == "approved" else data.status
    elif current_status == "manager_approved":
        if not review_allowed(user, owner, item):
            if user.role == "manager" and owner.manager_id == user.id:
                raise HTTPException(409, "Решение руководителя сохранено; заявка ожидает решения HR")
            raise HTTPException(403, "Нельзя принять решение по этой заявке")
        next_status = data.status
    else:
        raise HTTPException(409, "Заявка уже получила окончательное решение")
    result = db.execute(update(LeaveRequest).where(LeaveRequest.id == request_id, LeaveRequest.version == data.version, LeaveRequest.status == current_status).values(status=next_status, version=LeaveRequest.version + 1).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Заявка уже изменена. Обновите список")
    remaining_balance = None
    if next_status == "approved":
        # Every balance writer locks the employee row. This serializes approvals of
        # different requests for one employee in PostgreSQL; SQLite tests cannot
        # establish that locking guarantee.
        owner = db.scalar(select(Employee).where(Employee.id == item.employee_id).with_for_update())
        ensure_no_overlap(db, owner.id, item.start_date, item.end_date, excluding=item.id, statuses=("approved", "cancellation_requested"))
        quote, available = quote_leave(db, owner, item.start_date, item.end_date)
        if not item.calendar_version.startswith("legacy-") and (item.days_count != quote.days_count or item.calendar_version != quote.calendar_version or json.loads(item.excluded_dates_json) != [day.isoformat() for day in quote.excluded_dates]):
            db.rollback()
            raise HTTPException(409, "Календарь 1С:ЗУП изменился. Требуется новая заявка с актуальным расчётом")
        item.days_count, item.calendar_version = quote.days_count, quote.calendar_version
        item.excluded_dates_json = json.dumps([day.isoformat() for day in quote.excluded_dates])
        requested_days = quote.days_count
        if requested_days > available:
            db.rollback()
            raise HTTPException(409, f"Недостаточно дней отпуска: требуется {requested_days}, доступно {available}")
        db.add(LeaveDeduction(request_id=request_id, employee_id=owner.id, actor_id=user.id, days=requested_days))
        db.flush()
        enqueue(db, item, owner)
        remaining_balance = available - requested_days
        record(db, user.id, "leave.deducted", "request", request_id)
    db.add(RequestHistory(request_id=request_id, actor_id=user.id, status=next_status, comment=data.comment))
    action = "request.approved_by_manager" if next_status == "approved" and route == "hr_to_manager" else f"request.{next_status}"
    record(db, user.id, action, "request", request_id)
    if next_status == "manager_approved":
        notify(db, item.employee_id, "request_manager_approved", "Руководитель согласовал заявку", f"Заявка №{item.id} передана на финальную проверку HR. {data.comment}", entity_type="request", entity_id=item.id, actor_id=user.id)
        for hr in db.scalars(select(Employee).where(Employee.role == "hr_admin", Employee.id != item.employee_id)).all():
            notify(db, hr.id, "request_hr_review", "Заявка ожидает решения HR", f"{owner.full_name}: заявка №{item.id} согласована руководителем.", entity_type="request", entity_id=item.id, actor_id=user.id)
    else:
        label = "одобрена" if next_status == "approved" else "отклонена"
        balance_text = "" if remaining_balance is None else f" Списано {item.days_count} календ. дн. без праздников; доступный остаток — {remaining_balance}."
        notify(db, item.employee_id, "request_status", f"Заявка {label}", f"Заявка №{item.id}: решение принял(а) {user.full_name}.{balance_text} {data.comment}", entity_type="request", entity_id=item.id, actor_id=user.id)
    db.commit()
    if remaining_balance is not None:
        deliver(db, request_id)
    db.refresh(item)
    return present(db, item, user)


@router.post("/{request_id}/sync", response_model=RequestOut)
def retry_sync(request_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "hr_admin":
        raise HTTPException(403, "Повтор передачи доступен только HR")
    item = accessible(db, user, request_id)
    if not db.scalar(select(ZupDelivery.id).where(ZupDelivery.request_id == request_id)):
        raise HTTPException(409, "Для этой заявки нет команды передачи в 1С:ЗУП")
    deliver(db, request_id)
    return present(db, item, user)
