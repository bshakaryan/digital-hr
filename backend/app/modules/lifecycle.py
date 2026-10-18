"""Explicit demo lifecycle; source accounting is reversed by a separate command."""
import hashlib
import json
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, LeaveCancellation, LeaveRequest, RequestCommand, RequestHistory, ZupDelivery
from app.modules.audit import record
from app.modules.notifications import notify
from app.modules.requests import accessible, approval_route, cancellation_block_reason, ensure_no_overlap, final_reviewer_ids, new_request, present, review_allowed
from app.modules.leave_balance import quote_leave
from app.modules.zup_sync import deliver_cancellation
from app.schemas import LeaveCalculation, LifecycleCommand, RequestCreate, RequestDecision, RequestOut, RequestReplacement
from app.security import current_user

router = APIRouter(prefix="/requests", tags=["request lifecycle"])
CommandKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


def begin(db, user, request_id, key, operation, data):
    item = accessible(db, user, request_id)
    # Same lock order as approval/export; the immutable command is checked again
    # after the employee lock, so concurrent retries have one business effect.
    db.scalar(select(Employee).where(Employee.id == item.employee_id).with_for_update())
    db.refresh(item, with_for_update=True)
    digest = hashlib.sha256(f"{request_id}:{operation}:{data.model_dump_json()}".encode()).hexdigest()
    previous = db.scalar(select(RequestCommand).where(RequestCommand.actor_id == user.id, RequestCommand.command_key == key))
    if previous:
        if previous.payload_hash != digest:
            raise HTTPException(409, "Ключ команды использован с другими данными")
        return item, digest, accessible(db, user, previous.result_id)
    if item.version != data.version:
        raise HTTPException(409, "Заявка изменилась. Обновите карточку")
    return item, digest, None


def transition(db, item, user, version, status, comment, action=None):
    result = db.execute(update(LeaveRequest).where(LeaveRequest.id == item.id, LeaveRequest.version == version).values(status=status, version=version + 1).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "Заявка изменилась. Обновите карточку")
    db.add(RequestHistory(request_id=item.id, actor_id=user.id, status=status, comment=comment))
    record(db, user.id, action or f"request.{status}", "request", item.id)
    db.refresh(item)


def save_command(db, user, key, digest, result_id):
    db.add(RequestCommand(actor_id=user.id, command_key=key, payload_hash=digest, result_id=result_id))
    try:
        db.flush()
    except IntegrityError:
        # A key reused concurrently for different employees is not protected by
        # their separate employee locks. The uniqueness constraint rolls back
        # this entire operation rather than allowing a second business effect.
        db.rollback()
        raise HTTPException(409, "Ключ команды уже использован; обновите заявку")


def inform(db, item, user, title, comment, include_final_reviewers=False):
    owner = db.get(Employee, item.employee_id)
    recipients = {owner.id}
    if owner.manager_id and owner.role != "hr_admin":
        recipients.add(owner.manager_id)
    if include_final_reviewers or owner.role == "hr_admin":
        recipients.update(final_reviewer_ids(db, owner))
    for employee_id in recipients:
        notify(db, employee_id, "request_lifecycle", title, f"Заявка №{item.id} · {owner.full_name}. {comment}", entity_type="request", entity_id=item.id, actor_id=user.id)


@router.post("/{request_id}/replacement-calculation", response_model=LeaveCalculation)
def replacement_calculation(request_id: int, data: RequestCreate, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    item = accessible(db, user, request_id)
    if item.employee_id != user.id:
        raise HTTPException(403, "Заменить заявку может только её автор")
    if item.status not in ("submitted", "manager_approved"):
        raise HTTPException(409, "Заявка больше не доступна для замены")
    ensure_no_overlap(db, user.id, data.start_date, data.end_date, excluding=item.id)
    quote, available = quote_leave(db, user, data.start_date, data.end_date)
    return LeaveCalculation(start_date=data.start_date, end_date=data.end_date,
        **quote.model_dump(exclude={"employee_id", "balance", "applied_commands"}), available_balance=available,
        balance_after=available - quote.days_count, sufficient_balance=available >= quote.days_count)


@router.post("/{request_id}/withdraw", response_model=RequestOut)
def withdraw(request_id: int, data: LifecycleCommand, idempotency_key: CommandKey, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    item, digest, previous = begin(db, user, request_id, idempotency_key, "withdraw", data)
    if previous:
        return present(db, previous, user)
    if item.employee_id != user.id:
        raise HTTPException(403, "Отозвать заявку может только её автор")
    if item.status not in ("submitted", "manager_approved"):
        raise HTTPException(409, "Можно отозвать только ожидающую заявку")
    old_status = item.status
    transition(db, item, user, data.version, "withdrawn", data.comment)
    owner = db.get(Employee, item.employee_id)
    inform(db, item, user, "Заявка отозвана", data.comment, old_status == "manager_approved" or approval_route(owner) == "hr_to_manager")
    save_command(db, user, idempotency_key, digest, item.id)
    db.commit()
    return present(db, item, user)


@router.post("/{request_id}/replace", response_model=RequestOut, status_code=201)
def replace(request_id: int, data: RequestReplacement, idempotency_key: CommandKey, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    item, digest, previous = begin(db, user, request_id, idempotency_key, "replace", data)
    if previous:
        return present(db, previous, user)
    if item.employee_id != user.id:
        raise HTTPException(403, "Заменить заявку может только её автор")
    if item.status not in ("submitted", "manager_approved"):
        raise HTTPException(409, "Для одобренного отпуска сначала подтвердите отмену")
    old_status = item.status
    transition(db, item, user, data.version, "withdrawn", "Замена периода новой заявкой", "request.replaced")
    draft = RequestCreate(**data.model_dump(exclude={"version"}))
    replacement = new_request(db, user, draft, "replace-" + hashlib.sha256(f"{user.id}:{idempotency_key}".encode()).hexdigest(), hashlib.sha256(draft.model_dump_json().encode()).hexdigest())
    # Both records, histories, notifications and the replay key share one commit.
    owner = db.get(Employee, item.employee_id)
    inform(db, item, user, "Заявка заменена", f"Новая заявка №{replacement.id}; требуется повторное согласование.", old_status == "manager_approved" or approval_route(owner) == "hr_to_manager")
    db.add(RequestHistory(request_id=item.id, actor_id=user.id, status="withdrawn", comment=f"Создана новая заявка №{replacement.id}"))
    save_command(db, user, idempotency_key, digest, replacement.id)
    db.commit()
    return present(db, replacement, user)


@router.post("/{request_id}/cancel", response_model=RequestOut)
def request_cancel(request_id: int, data: LifecycleCommand, idempotency_key: CommandKey, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    item, digest, previous = begin(db, user, request_id, idempotency_key, "cancel", data)
    if previous:
        return present(db, previous, user)
    if item.employee_id != user.id:
        raise HTTPException(403, "Запросить отмену может только автор")
    if item.status != "approved":
        raise HTTPException(409, "Отмену можно запросить для одобренного отпуска")
    reason = cancellation_block_reason(db, item)
    if reason:
        raise HTTPException(409, reason)
    transition(db, item, user, data.version, "cancellation_requested", data.comment)
    inform(db, item, user, "Запрошена отмена отпуска", data.comment, True)
    save_command(db, user, idempotency_key, digest, item.id)
    db.commit()
    return present(db, item, user)


@router.post("/{request_id}/cancellation-decision", response_model=RequestOut)
def cancel_decision(request_id: int, data: RequestDecision, idempotency_key: CommandKey, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    item, digest, previous = begin(db, user, request_id, idempotency_key, "cancel-decision", data)
    if previous:
        return present(db, previous, user)
    if item.status != "cancellation_requested":
        raise HTTPException(409, "Заявка не ожидает отмены")
    owner = db.get(Employee, item.employee_id)
    if not review_allowed(user, owner, item):
        raise HTTPException(403, "Отмену подтверждает независимый согласующий, кроме автора заявки")
    if not data.comment.strip():
        raise HTTPException(422, "Укажите комментарий к решению об отмене")
    accepted = data.status == "approved"
    if accepted:
        reason = cancellation_block_reason(db, item)
        if reason:
            raise HTTPException(409, reason)
        original = db.scalar(select(ZupDelivery).where(ZupDelivery.request_id == item.id))
        owner = db.get(Employee, item.employee_id)
        db.add(LeaveCancellation(request_id=item.id, actor_id=user.id, command_key=f"jana-cancel-{uuid4()}", payload_json=json.dumps({"employee_id": owner.zup_id, "original_command_key": original.command_key})))
    manager_route = approval_route(owner) == "hr_to_manager"
    transition(db, item, user, data.version, "cancelled" if accepted else "approved", data.comment,
               ("request.cancelled_by_manager" if manager_route else "request.cancelled") if accepted else
               ("request.cancellation_rejected_by_manager" if manager_route else "request.cancellation_rejected"))
    inform(db, item, user, "Отмена отпуска подтверждена" if accepted else "Отмена отпуска отклонена", data.comment, True)
    save_command(db, user, idempotency_key, digest, item.id)
    db.commit()
    if accepted:
        deliver_cancellation(db, item.id)
    return present(db, item, user)


@router.post("/{request_id}/cancellation-sync", response_model=RequestOut)
def cancel_sync(request_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "hr_admin":
        raise HTTPException(403, "Повтор возврата доступен только HR")
    item = accessible(db, user, request_id)
    if not db.scalar(select(LeaveCancellation.id).where(LeaveCancellation.request_id == item.id)):
        raise HTTPException(409, "Команда отмены отсутствует")
    deliver_cancellation(db, item.id)
    return present(db, item, user)
