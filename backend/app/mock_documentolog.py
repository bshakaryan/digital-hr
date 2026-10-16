"""Separate persistent mock of the published Documentolog Business session API.

Signing here is a deliberate human-triggered simulation, never an EDS signature.
"""
from contextlib import asynccontextmanager
import hashlib
from html import escape
import json
import os
import secrets
import sqlite3
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field


class SessionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aAttachments: list[str] = Field(min_length=1, max_length=1)
    sSetWebhookUrl: str
    iSendToRecipient: int = Field(ge=0, le=1)
    mRecipient: list[str] = Field(min_length=1, max_length=1)
    iRecipientSignatureRequired: int = Field(ge=0, le=1)
    mAvailableSignatureMethodsForRecipient: list[str]
    mAvailableSignatureMethods: list[str]
    sSender: str


def create_mock_app(database: str, api_key: str, backend_url: str, browser_url: str, *, transport=None):
    if len(api_key) < 32:
        raise ValueError("DOCUMENTOLOG_API_KEY: минимум 32 символа")

    def connect():
        return sqlite3.connect(database, timeout=10)

    @asynccontextmanager
    async def lifespan(app):
        with connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS documents (command_key TEXT PRIMARY KEY, payload TEXT NOT NULL, token TEXT UNIQUE NOT NULL, reference TEXT UNIQUE NOT NULL, file_sha256 TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'signing', delivered INTEGER NOT NULL DEFAULT 0)")
        yield

    app = FastAPI(title="Mock Documentolog Business · подпись имитируется", lifespan=lifespan)

    def authorize(key: str | None = Header(default=None, alias="api-key")):
        if not key or not secrets.compare_digest(key, api_key):
            raise HTTPException(401, "Неверный сервисный ключ")

    def internal_url(value, path_prefix):
        url, allowed = urlparse(value), urlparse(backend_url)
        if url.scheme != allowed.scheme or url.netloc != allowed.netloc or not url.path.startswith(path_prefix) or url.username or url.password or url.query or url.fragment:
            raise HTTPException(422, "URL вне разрешённого тестового backend")
        return value

    def document(token):
        with connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM documents WHERE token=?", (token,)).fetchone()
        if row is None:
            raise HTTPException(404, "Демонстрационная сессия не найдена")
        return dict(row)

    @app.get("/health")
    def health():
        with connect() as db:
            db.execute("SELECT COUNT(*) FROM documents")
        return {"status": "ok", "mode": "mock"}

    @app.post("/json/external/oauth/token", dependencies=[Depends(authorize)])
    def create(data: SessionPayload, idempotency_key: str = Header(min_length=8, max_length=128)):
        payload = data.model_dump_json()
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT payload,token FROM documents WHERE command_key=?", (idempotency_key,)).fetchone()
            if old:
                if old[0] != payload:
                    raise HTTPException(409, "Ключ уже использован с другими данными")
                return {"status": 1, "data": {"access_token": old[1], "scope": "document-create|document-sign|document-show", "token_type": "Bearer"}}
            attachment = internal_url(data.aAttachments[0], "/api/documentolog/files/")
            internal_url(data.sSetWebhookUrl, "/api/documentolog/webhook/")
            try:
                with httpx.Client(timeout=5, transport=transport, trust_env=False, follow_redirects=False) as client:
                    result = client.get(attachment)
                    result.raise_for_status()
                    if not result.content.startswith(b"PK") or len(result.content) > 2_000_000:
                        raise ValueError("Expected DOCX")
            except (httpx.HTTPError, ValueError) as error:
                raise HTTPException(503, "Не удалось получить документ JanaМен") from error
            token, reference = secrets.token_urlsafe(32), "MOCK-DOC-" + secrets.token_hex(8)
            db.execute("INSERT INTO documents (command_key,payload,token,reference,file_sha256) VALUES (?,?,?,?,?)",
                (idempotency_key, payload, token, reference, hashlib.sha256(result.content).hexdigest()))
        return {"status": 1, "data": {"access_token": token, "scope": "document-create|document-sign|document-show", "token_type": "Bearer"}}

    @app.get("/external/sign/embedded", response_class=HTMLResponse)
    def embedded(sParams: str):
        row = document(sParams)
        # Fixed script only; token is URL-encoded by the browser, never interpolated.
        return HTMLResponse(f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mock Documentolog</title><style>body{{font:16px system-ui;max-width:680px;margin:8vh auto;padding:24px;color:#18382f;background:#f4f7f5}}main{{background:white;border-radius:20px;padding:32px}}button{{padding:14px;margin:8px 8px 8px 0;cursor:pointer}}code{{word-break:break-all}}a{{color:#17634e}}</style><main><h1>Mock Documentolog</h1><p><strong>Демонстрация. ЭЦП и юридически значимая подпись не используются.</strong></p><p>Документ: {escape(row['reference'])}</p><p>Получатель: {escape(json.loads(row['payload'])['mRecipient'][0])}</p><p>SHA-256 полученного DOCX: <code>{row['file_sha256']}</code></p><p>Статус: <strong id="status">{escape(row['status'])}</strong></p><a href="/external/mock/file?sParams={escape(sParams, quote=True)}">Скачать проект заявления</a><p><button data-action="complete">Имитировать подписание</button><button data-action="decline">Имитировать отказ</button></p><p id="result" aria-live="polite"></p><p>После действия обновите карточку заявки в JanaМен.</p></main><script>document.querySelectorAll('button').forEach(button=>button.onclick=async()=>{{document.querySelectorAll('button').forEach(b=>b.disabled=true);try{{const response=await fetch('/external/mock/'+button.dataset.action+location.search,{{method:'POST'}});const data=await response.json();if(!response.ok)throw Error(data.detail||'Ошибка');document.getElementById('status').textContent=data.status;document.getElementById('result').textContent='Результат принят JanaМен';}}catch(error){{document.getElementById('result').textContent=error.message;}}finally{{document.querySelectorAll('button').forEach(b=>b.disabled=false);}}}});</script></html>''',
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"})

    @app.get("/external/mock/file")
    def file(sParams: str):
        from fastapi import Response
        row = document(sParams)
        with httpx.Client(timeout=5, transport=transport, trust_env=False, follow_redirects=False) as client:
            result = client.get(internal_url(json.loads(row["payload"])["aAttachments"][0], "/api/documentolog/files/"))
        if result.status_code != 200:
            raise HTTPException(503, "Документ недоступен")
        return Response(result.content, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": 'attachment; filename="demo-leave.docx"', "Cache-Control": "no-store"})

    def finish(sParams, target):
        row = document(sParams)
        # Persist outcome before callback. A repeated click retries only the same event.
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            status = db.execute("SELECT status FROM documents WHERE token=?", (sParams,)).fetchone()[0]
            if status not in ("signing", target):
                raise HTTPException(409, "Решение уже принято")
            db.execute("UPDATE documents SET status=? WHERE token=?", (target, sParams))
        payload = json.loads(row["payload"])
        body = {"event": "document_completed" if target == "completed" else "signer_declined", "doc_id": row["reference"]}
        if target == "completed":
            body["document"] = browser_url.rstrip("/") + "/external/sign/embedded?sParams=" + sParams
        try:
            with httpx.Client(timeout=5, transport=transport, trust_env=False, follow_redirects=False) as client:
                response = client.post(internal_url(payload["sSetWebhookUrl"], "/api/documentolog/webhook/"), json=body)
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise HTTPException(503, "Результат сохранён, но webhook не доставлен. Повторите то же действие.") from error
        with connect() as db:
            db.execute("UPDATE documents SET delivered=1 WHERE token=?", (sParams,))
        return {"status": target, "mode": "mock", "callback_delivered": True}

    @app.post("/external/mock/complete")
    def complete(sParams: str):
        return finish(sParams, "completed")

    @app.post("/external/mock/decline")
    def decline(sParams: str):
        return finish(sParams, "declined")

    return app


def app_factory():
    return create_mock_app(os.environ.get("DOCUMENTOLOG_MOCK_DATABASE", "/data/documentolog.sqlite3"),
        os.environ["DOCUMENTOLOG_API_KEY"], os.environ["DOCUMENTOLOG_MOCK_BACKEND_URL"],
        os.environ.get("DOCUMENTOLOG_BROWSER_URL", "http://localhost:8400"))
