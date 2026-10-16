"""Explicit HR delivery after approval. Document status never changes leave accounting."""
import hashlib
import json
import secrets
from datetime import timedelta, timezone
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.documentolog_client import documentolog_client
from app.leave_document import leave_document
from app.models import DocumentologDelivery, Employee, LeaveRequest, utcnow
from app.modules.audit import record
from app.modules.notifications import notify
from app.modules.requests import accessible
from app.security import current_user, require_hr

router = APIRouter(tags=["documentolog"])


class PrepareDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipient: str | None = Field(default=None, min_length=3, max_length=254)


class Webhook(BaseModel):
    # The public API documents extra download fields; do not retain unnecessary PII.
    event: str = Field(max_length=80)
    doc_id: str = Field(min_length=1, max_length=100)
    document: str | None = Field(default=None, max_length=2000)


def present(delivery):
    if delivery is None:
        return {"status": "not_created", "mode": get_settings().documentolog_mode}
    return {"status": delivery.status, "mode": delivery.mode,
        "external_id": delivery.external_id, "view_url": delivery.view_url,
        "file_sha256": delivery.file_sha256, "last_error": delivery.last_error,
        "expires_at": delivery.expires_at}


def find(db, request_id, *, lock=False):
    query = select(DocumentologDelivery).where(DocumentologDelivery.request_id == request_id)
    return db.scalar((query.with_for_update() if lock else query).execution_options(populate_existing=True))


def live(delivery):
    if delivery is None or delivery.expires_at.replace(tzinfo=timezone.utc) <= utcnow():
        raise HTTPException(404, "Ссылка недействительна или истекла")


@router.get("/integrations/documentolog")
def integration_status(user: Employee = Depends(require_hr), db: Session = Depends(get_db)):
    settings = get_settings()
    connected = False
    if settings.documentolog_mode == "mock":
        try:
            with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
                result = client.get(settings.documentolog_base_url.rstrip("/") + "/health")
                connected = result.status_code == 200 and result.json().get("mode") == "mock"
        except (httpx.HTTPError, ValueError):
            pass
    counts = dict(db.execute(select(DocumentologDelivery.status, func.count()).group_by(DocumentologDelivery.status)).all())
    return {"mode": settings.documentolog_mode, "connected": connected,
        "provider": "Documentolog Business public API", "counts": counts,
        "real_connection_verified": False}


@router.get("/requests/{request_id}/documentolog")
def document_status(request_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    accessible(db, user, request_id)
    return present(find(db, request_id))


@router.post("/requests/{request_id}/documentolog")
def create_document(request_id: int, data: PrepareDocument, user: Employee = Depends(require_hr), db: Session = Depends(get_db)):
    item = accessible(db, user, request_id)
    if item.employee_id == user.id:
        raise HTTPException(403, "Нельзя отправлять собственную заявку от имени HR")
    if item.status != "approved":
        raise HTTPException(409, "Документ доступен после финального решения HR")
    settings = get_settings()
    client = documentolog_client()
    # Lock the request before checking uniqueness: concurrent HR commands serialize.
    db.refresh(item, with_for_update=True)
    if item.status != "approved":
        raise HTTPException(409, "Заявка изменилась; документ сейчас недоступен")
    delivery = find(db, request_id, lock=True)
    if delivery is None:
        employee = db.get(Employee, item.employee_id)
        recipient = data.recipient or (employee.email if settings.documentolog_mode == "mock" else None)
        if not recipient or (settings.documentolog_mode == "real" and (not recipient.isascii() or not recipient.isdigit() or len(recipient) != 12)):
            raise HTTPException(422, "Для Documentolog Business укажите ИИН получателя из 12 цифр")
        file_token, callback_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        content = leave_document(item, employee, demo=settings.documentolog_mode == "mock")
        payload = {"aAttachments": [settings.documentolog_public_url.rstrip("/") + f"/api/documentolog/files/{file_token}"],
            "sSetWebhookUrl": settings.documentolog_callback_url.rstrip("/") + f"/api/documentolog/webhook/{callback_token}",
            "iSendToRecipient": 1, "mRecipient": [recipient], "iRecipientSignatureRequired": 1,
            "mAvailableSignatureMethodsForRecipient": ["eds", "egov-qr"],
            "mAvailableSignatureMethods": ["eds", "egov-qr"],
            "sSender": settings.documentolog_sender or "000000000000"}
        delivery = DocumentologDelivery(request_id=request_id, created_by=user.id,
            command_key=f"jana-document-{uuid4()}", mode=settings.documentolog_mode,
            payload_json=json.dumps(payload), file_content=content,
            file_sha256=hashlib.sha256(content).hexdigest(), file_token=file_token, callback_token=callback_token,
            expires_at=utcnow() + timedelta(days=30))
        db.add(delivery)
        db.flush()
        record(db, user.id, "documentolog.prepared", "request", request_id)
    elif data.recipient and json.loads(delivery.payload_json)["mRecipient"] != [data.recipient]:
        raise HTTPException(409, "Документ уже подготовлен для другого получателя")
    if delivery.mode != settings.documentolog_mode:
        raise HTTPException(409, "Режим изменён: документ другого контура нельзя отправить заново")
    if delivery.status != "prepared":
        # This includes a process crash after committing 'creating'. Do not send twice.
        return {**present(delivery), "session_url": delivery.session_url}
    delivery.status = "creating"
    record(db, user.id, "documentolog.creation_started", "request", request_id)
    db.commit()
    try:
        url = client.create_session(json.loads(delivery.payload_json), delivery.command_key)
    except HTTPException as error:
        delivery = find(db, request_id, lock=True)
        # A webhook may already have arrived, even if the HTTP response was lost.
        if delivery.status == "creating":
            delivery.status, delivery.last_error = "needs_review", str(error.detail)
            record(db, user.id, "documentolog.needs_review", "request", request_id)
    else:
        delivery = find(db, request_id, lock=True)
        db.refresh(delivery)
        delivery.session_url = url
        if delivery.status == "creating":
            delivery.status = "signing"
        record(db, user.id, "documentolog.session_created", "request", request_id)
    db.commit()
    return {**present(delivery), "session_url": delivery.session_url}


@router.get("/requests/{request_id}/documentolog/session")
def session_link(request_id: int, user: Employee = Depends(require_hr), db: Session = Depends(get_db)):
    accessible(db, user, request_id)
    delivery = find(db, request_id)
    live(delivery)
    if not delivery.session_url:
        raise HTTPException(409, "Сессия не подтверждена; проверьте Documentolog")
    return {"url": delivery.session_url, "mode": delivery.mode}


@router.get("/documentolog/files/{token}")
def attachment(token: str, db: Session = Depends(get_db)):
    delivery = db.scalar(select(DocumentologDelivery).where(DocumentologDelivery.file_token == token))
    live(delivery)
    return Response(delivery.file_content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="leave-{delivery.request_id}.docx"',
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})


@router.post("/documentolog/webhook/{token}")
def webhook(token: str, data: Webhook, db: Session = Depends(get_db)):
    delivery = db.scalar(select(DocumentologDelivery).where(DocumentologDelivery.callback_token == token).with_for_update())
    live(delivery)
    if data.event not in ("document_sent", "signer_signed", "signer_declined", "document_completed"):
        raise HTTPException(422, "Неизвестное событие")
    if delivery.status == "prepared":
        raise HTTPException(409, "Создание документа не начато")
    if delivery.external_id and delivery.external_id != data.doc_id:
        raise HTTPException(409, "Идентификатор документа не совпадает")
    delivery.external_id = data.doc_id
    previous = delivery.status
    if data.event == "document_completed" and previous not in ("completed", "completed_reported", "declined"):
        delivery.status = "completed" if delivery.mode == "mock" else "completed_reported"
        delivery.view_url = documentolog_client().safe_view_url(data.document)
    elif data.event == "signer_declined" and previous not in ("completed", "completed_reported", "declined"):
        delivery.status = "declined"
    elif data.event in ("document_sent", "signer_signed") and previous in ("creating", "needs_review"):
        delivery.status = "signing"
    if previous != delivery.status:
        delivery.last_error = None
        record(db, delivery.created_by, f"documentolog.{delivery.status}", "request", delivery.request_id)
        item = db.get(LeaveRequest, delivery.request_id)
        notify(db, item.employee_id, "documentolog_status", "Обновлён статус документа",
            f"Заявка №{item.id}: Documentolog — {delivery.status}." + (" Демонстрация, ЭЦП не используется." if delivery.mode == "mock" else ""), entity_type="request", entity_id=item.id, actor_id=delivery.created_by)
    db.commit()
    return {"accepted": True, "status": delivery.status}
