import json
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Employee, LeaveCancellation, LeaveDeduction, LeaveRequest, ZupDelivery, utcnow
from app.modules import integrations
from app.modules.audit import record
from app.modules.notifications import notify


def enqueue(db: Session, item: LeaveRequest, employee: Employee):
    body = {"employee_id": employee.zup_id, "start_date": item.start_date.isoformat(),
            "end_date": item.end_date.isoformat(), "days_count": item.days_count,
            "calendar_version": item.calendar_version}
    db.add(ZupDelivery(request_id=item.id, command_key=f"jana-leave-{uuid4()}", payload_json=json.dumps(body)))


def deliver(db: Session, request_id: int):
    # Same employee lock as HR approval: exporting a committed deduction cannot
    # race a balance check that subtracts not-yet-exported local deductions.
    employee_id = db.scalar(select(LeaveRequest.employee_id).where(LeaveRequest.id == request_id))
    db.scalar(select(Employee).where(Employee.id == employee_id).with_for_update())
    delivery = db.scalar(select(ZupDelivery).where(ZupDelivery.request_id == request_id).with_for_update())
    if delivery is None or delivery.status == "synced":
        db.rollback()
        return
    delivery.attempts += 1
    try:
        receipt = integrations.zup_adapter().register(json.loads(delivery.payload_json), delivery.command_key)
    except HTTPException as error:
        delivery.status = "error"
        delivery.last_error = str(error.detail)[:500]
        delivery.next_attempt_at = utcnow() + timedelta(seconds=min(300, 2 ** min(delivery.attempts, 8)))
    else:
        delivery.status, delivery.reference, delivery.last_error = "synced", receipt.reference, None
        actor_id = db.scalar(select(LeaveDeduction.actor_id).where(LeaveDeduction.request_id == request_id))
        record(db, actor_id, "zup.leave_registered", "request", request_id)
    db.commit()


def deliver_cancellation(db: Session, request_id: int):
    # Register first if its response was lost; both commands keep permanent keys.
    deliver(db, request_id)
    employee_id = db.scalar(select(LeaveRequest.employee_id).where(LeaveRequest.id == request_id))
    db.scalar(select(Employee).where(Employee.id == employee_id).with_for_update())
    cancellation = db.scalar(select(LeaveCancellation).where(LeaveCancellation.request_id == request_id).with_for_update())
    if cancellation is None or cancellation.status == "synced":
        db.rollback()
        return
    cancellation.attempts += 1
    try:
        receipt = integrations.zup_adapter().cancel(json.loads(cancellation.payload_json), cancellation.command_key)
    except HTTPException as error:
        cancellation.status = "error"
        cancellation.last_error = str(error.detail)[:500]
        cancellation.next_attempt_at = utcnow() + timedelta(seconds=min(300, 2 ** min(cancellation.attempts, 8)))
    else:
        cancellation.status, cancellation.reference, cancellation.last_error = "synced", receipt.reference, None
        record(db, cancellation.actor_id, "zup.leave_cancelled", "request", request_id)
        notify(db, employee_id, "request_refunded", "Дни отпуска возвращены", f"Возврат по заявке №{request_id} подтверждён источником.", entity_type="request", entity_id=request_id, actor_id=cancellation.actor_id)
    db.commit()
