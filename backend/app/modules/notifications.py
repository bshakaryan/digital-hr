from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, Notification
from app.modules.audit import record
from app.schemas import NotificationOut
from app.security import current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


def notify(db: Session, employee_id: int, kind: str, title: str, body: str, *, entity_type=None, entity_id=None, actor_id=None):
    db.add(Notification(employee_id=employee_id, kind=kind, title=title, body=body,
                        entity_type=entity_type, entity_id=entity_id, actor_id=actor_id))


def present(db, item):
    actor = db.get(Employee, item.actor_id) if item.actor_id else None
    return NotificationOut.model_validate(item).model_copy(update={"actor_name": actor.full_name if actor else None})


@router.get("", response_model=list[NotificationOut])
def notifications(user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    return [present(db, item) for item in db.scalars(select(Notification).where(Notification.employee_id == user.id).order_by(Notification.id.desc())).all()]


@router.patch("/read-all")
def mark_all_read(user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    ids = db.scalars(update(Notification).where(Notification.employee_id == user.id, Notification.read.is_(False)).values(read=True).returning(Notification.id)).all()
    for notification_id in ids:
        record(db, user.id, "notification.read", "notification", notification_id)
    db.commit()
    return {"updated": len(ids)}


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.employee_id == user.id))
    if item is None:
        raise HTTPException(404, "Уведомление не найдено")
    changed = db.execute(update(Notification).where(Notification.id == item.id, Notification.read.is_(False)).values(read=True).execution_options(synchronize_session=False))
    if changed.rowcount:
        record(db, user.id, "notification.read", "notification", item.id)
    db.commit()
    db.refresh(item)
    return present(db, item)
