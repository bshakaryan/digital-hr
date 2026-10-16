import csv
import io
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from app.database import get_db
from app.models import AuditEvent, Employee, LeaveRequest
from app.schemas import AuditOut, AuditPage
from app.security import require_hr

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_hr)])

ACTION_LABELS = {
    "auth.login": "Вход в систему", "request.created": "Заявка отправлена",
    "request.manager_approved": "Руководитель согласовал заявку", "request.approved": "HR согласовал заявку",
    "request.rejected": "Заявка отклонена", "request.withdrawn": "Заявка отозвана",
    "request.replaced": "Период заменён новой заявкой", "request.cancellation_requested": "Запрошена отмена отпуска",
    "request.cancelled": "HR подтвердил отмену", "request.cancellation_rejected": "HR отклонил отмену",
    "leave.deducted": "Учтены дни отпуска", "zup.leave_registered": "Отпуск передан в 1С",
    "zup.leave_cancelled": "Возврат дней подтверждён 1С", "notification.read": "Уведомление прочитано",
    "notification.cleared": "Прочитанное уведомление убрано из списка",
    "course.assigned": "Назначен курс", "course.progressed": "Обновлён прогресс курса", "course.completed": "Завершён курс",
    "documentolog.prepared": "Подготовлен документ", "documentolog.creation_started": "Начата отправка документа",
    "documentolog.session_created": "Создана сессия подписания", "documentolog.needs_review": "Документ требует сверки",
    "documentolog.signing": "Документ ожидает подписи", "documentolog.completed": "Имитация подписи завершена",
    "documentolog.completed_reported": "Сервис сообщил о подписании", "documentolog.declined": "Подписант отказал",
}


def record(db: Session, actor_id: int, action: str, entity_type: str, entity_id: int):
    db.add(AuditEvent(actor_id=actor_id, action=action, entity_type=entity_type, entity_id=entity_id))


def filtered_query(employee_id=None, actor_id=None, action=None, start_date=None, end_date=None):
    if start_date and end_date and end_date < start_date:
        raise HTTPException(422, "Конец периода раньше начала")
    actor, owner = aliased(Employee), aliased(Employee)
    query = select(AuditEvent, actor.full_name, owner.id, owner.full_name).join(actor, actor.id == AuditEvent.actor_id).outerjoin(
        LeaveRequest, (AuditEvent.entity_type == "request") & (LeaveRequest.id == AuditEvent.entity_id)
    ).outerjoin(owner, owner.id == case((AuditEvent.entity_type == "employee", AuditEvent.entity_id), else_=func.coalesce(LeaveRequest.employee_id, actor.id)))
    if employee_id is not None:
        query = query.where(func.coalesce(owner.id, actor.id) == employee_id)
    if actor_id is not None:
        query = query.where(actor.id == actor_id)
    if action:
        query = query.where(AuditEvent.action == action)
    if start_date:
        query = query.where(AuditEvent.created_at >= datetime.combine(start_date, time.min, timezone.utc))
    if end_date:
        query = query.where(AuditEvent.created_at <= datetime.combine(end_date, time.max, timezone.utc))
    return query


def filters(employee_id: int | None = None, actor_id: int | None = None, action: str | None = Query(None, max_length=80), start_date: date | None = None, end_date: date | None = None):
    return filtered_query(employee_id, actor_id, action, start_date, end_date)


def present(row):
    event, actor_name, employee_id, employee_name = row
    return AuditOut.model_validate(event).model_copy(update={"actor_name": actor_name,
        "action_label": ACTION_LABELS.get(event.action, event.action), "employee_id": employee_id, "employee_name": employee_name})


@router.get("", response_model=list[AuditOut])
def events(query=Depends(filters), db: Session = Depends(get_db)):
    return [present(row) for row in db.execute(query.order_by(AuditEvent.id.desc()).limit(200))]


@router.get("/page", response_model=AuditPage)
def page(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), query=Depends(filters), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(AuditEvent.id.desc()).offset((page - 1) * page_size).limit(page_size))
    return AuditPage(items=[present(row) for row in rows], total=total, page=page, page_size=page_size)


@router.get("/export")
def export(query=Depends(filters), db: Session = Depends(get_db)):
    rows = db.execute(query.order_by(AuditEvent.id.desc()).limit(10001)).all()
    if len(rows) > 10000:
        raise HTTPException(422, "Более 10 000 событий: сузьте период экспорта")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Событие", "Действие", "Пользователь", "Сотрудник", "Объект", "ID", "Время UTC"])
    def safe(value):
        value = str(value or "")
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
    for row in rows:
        item = present(row)
        writer.writerow([item.id, safe(item.action_label), safe(item.actor_name), safe(item.employee_name), safe(item.entity_type), item.entity_id, item.created_at.isoformat()])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="jana-audit.csv"', "Cache-Control": "no-store"})
