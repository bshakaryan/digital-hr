import hashlib
from io import BytesIO
import json
import sqlite3
from urllib.parse import parse_qs, urlparse
from zipfile import ZipFile

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select


@pytest.fixture
def docs(api, monkeypatch, tmp_path):
    from app.config import get_settings
    from app.documentolog_client import DocumentologClient
    from app.mock_documentolog import create_mock_app
    from app.modules import documentolog

    for key, value in {"DOCUMENTOLOG_MODE": "mock", "DOCUMENTOLOG_API_KEY": api.db.secret,
        "DOCUMENTOLOG_BASE_URL": "http://docs.test", "DOCUMENTOLOG_BROWSER_URL": "http://docs.test",
        "DOCUMENTOLOG_PUBLIC_URL": "http://api.test", "DOCUMENTOLOG_CALLBACK_URL": "http://api.test"}.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()

    def backend_transport(request):
        return api.client.request(request.method, request.url.path, content=request.content, headers=dict(request.headers))

    path = tmp_path / "documentolog.sqlite3"
    app = create_mock_app(str(path), api.db.secret, "http://api.test", "http://docs.test", transport=httpx.MockTransport(backend_transport))
    with TestClient(app) as client:
        def provider_transport(request):
            return client.request(request.method, request.url.path, content=request.content, headers=dict(request.headers))
        adapter = DocumentologClient("http://docs.test", "http://docs.test", api.db.secret, mode="mock", transport=httpx.MockTransport(provider_transport))
        monkeypatch.setattr(documentolog, "documentolog_client", lambda: adapter)
        yield client, path
    get_settings.cache_clear()


def approved(api):
    item = api.leave()
    item = api.decide(item).json()
    return api.decide(item, "hr").json()


def delivery(api, request_id):
    from app.models import DocumentologDelivery
    with api.db.session() as db:
        return db.scalar(select(DocumentologDelivery).where(DocumentologDelivery.request_id == request_id))


def test_full_http_document_received_and_callback_does_not_deduct_again(api, docs):
    client, path = docs
    item = approved(api)
    accounting = api.db.snapshot("leave_deductions", "zup_deliveries", "request_history", "leave_requests")
    url = f"/api/requests/{item['id']}/documentolog"
    result = api.post(url, {}, "hr")
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "signing"
    row = delivery(api, item["id"])
    file = api.client.get(f"/api/documentolog/files/{row.file_token}")
    assert hashlib.sha256(file.content).hexdigest() == result.json()["file_sha256"]
    with ZipFile(BytesIO(file.content)) as document:
        assert "Демонстрационный документ" in document.read("word/document.xml").decode()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT file_sha256 FROM documents").fetchone()[0] == row.file_sha256
    assert api.post(url, {}, "hr").json()["session_url"] == result.json()["session_url"]
    parsed = urlparse(result.json()["session_url"])
    token = parse_qs(parsed.query)["sParams"][0]
    page = client.get(parsed.path, params={"sParams": token})
    assert "ЭЦП и юридически значимая подпись не используются" in page.text
    done = client.post("/external/mock/complete", params={"sParams": token})
    assert done.status_code == 200, done.text
    assert api.get(url).json()["status"] == "completed"
    before_repeat = api.db.snapshot()
    assert client.post("/external/mock/complete", params={"sParams": token}).status_code == 200
    assert api.db.snapshot() == before_repeat
    assert client.post("/external/mock/decline", params={"sParams": token}).status_code == 409
    assert api.db.snapshot(*accounting.keys()) == accounting
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1


def test_permissions_and_redaction(api, docs):
    item = approved(api)
    url = f"/api/requests/{item['id']}/documentolog"
    for actor in ("employee", "manager", "outsider"):
        assert api.post(url, {}, actor).status_code == 403
    assert api.get(url, "outsider").status_code == 404
    assert api.get("/api/integrations/documentolog").status_code == 403
    assert api.client.get(url).status_code == 401
    result = api.post(url, {}, "hr").json()
    assert api.get(url).json()["status"] == "signing"
    assert "session_url" not in api.get(url).json()
    assert api.db.secret not in json.dumps(result)
    assert api.get(url + "/session").status_code == 403
    assert api.get(url + "/session", "hr").status_code == 200
    assert api.client.get("/api/documentolog/files/unknown").status_code == 404
    assert api.client.post("/api/documentolog/webhook/unknown", json={"event": "document_completed", "doc_id": "fake"}).status_code == 404


def test_submission_requires_hr_approval(api, docs):
    item = api.leave()
    url = f"/api/requests/{item['id']}/documentolog"
    assert api.post(url, {}, "hr").status_code == 409
    api.decide(item)
    assert api.post(url, {}, "hr").status_code == 409


def test_existing_document_blocks_cancellation_without_changing_accounting(api, docs):
    item = approved(api)
    assert api.post(f"/api/requests/{item['id']}/documentolog", {}, "hr").status_code == 200
    before = api.db.snapshot()
    response = api.client.post(f"/api/requests/{item['id']}/cancel", json={"version": item["version"], "comment": "Cancel"}, headers={**api.headers(), "Idempotency-Key": "cancel-with-document"})
    assert response.status_code == 409
    assert api.db.snapshot() == before
    assert not api.get(f"/api/requests/{item['id']}").json()["cancellation_allowed"]


def test_partial_signature_out_of_order_and_external_id(api, docs):
    item = approved(api)
    url = f"/api/requests/{item['id']}/documentolog"
    api.post(url, {}, "hr")
    row = delivery(api, item["id"])
    callback = f"/api/documentolog/webhook/{row.callback_token}"
    for event in ("document_sent", "signer_signed"):
        assert api.client.post(callback, json={"event": event, "doc_id": "same-doc"}).json()["status"] == "signing"
    assert api.client.post(callback, json={"event": "document_completed", "doc_id": "other-doc"}).status_code == 409
    result = api.client.post(callback, json={"event": "document_completed", "doc_id": "same-doc", "document": "https://evil.test/file"})
    assert result.json()["status"] == "completed"
    assert api.get(url).json()["view_url"] is None
    for event in ("signer_signed", "document_sent", "signer_declined"):
        assert api.client.post(callback, json={"event": event, "doc_id": "same-doc"}).json()["status"] == "completed"


def test_unknown_response_is_not_automatically_replayed(api, docs, monkeypatch):
    from app.modules import documentolog
    item = approved(api)
    url = f"/api/requests/{item['id']}/documentolog"
    adapter = documentolog.documentolog_client()
    calls = []
    def lost_response(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret upstream data must not escape")
    adapter.transport = httpx.MockTransport(lost_response)
    result = api.post(url, {}, "hr")
    assert result.json()["status"] == "needs_review"
    assert "secret upstream" not in result.text
    assert api.post(url, {}, "hr").json()["status"] == "needs_review"
    assert len(calls) == 1


def test_mock_service_auth_idempotency_and_ssrf_guard(api, docs):
    client, path = docs
    item = approved(api)
    api.post(f"/api/requests/{item['id']}/documentolog", {}, "hr")
    row = delivery(api, item["id"])
    payload = json.loads(row.payload_json)
    headers = {"api-key": api.db.secret, "Idempotency-Key": row.command_key}
    assert client.post("/json/external/oauth/token", json=payload).status_code == 401
    assert client.post("/json/external/oauth/token", json=payload, headers=headers).status_code == 200
    payload["mRecipient"] = ["another@example.com"]
    assert client.post("/json/external/oauth/token", json=payload, headers=headers).status_code == 409
    payload["aAttachments"] = ["http://169.254.169.254/latest/meta-data"]
    headers["Idempotency-Key"] = "another-command"
    assert client.post("/json/external/oauth/token", json=payload, headers=headers).status_code == 422


def test_real_client_uses_published_path_and_no_assumed_idempotency():
    from app.documentolog_client import DocumentologClient
    def transport(request):
        assert str(request.url) == "https://apibusiness.documentolog.com/json/external/oauth/token"
        assert request.headers["api-key"] == "test-key"
        assert "Idempotency-Key" not in request.headers
        return httpx.Response(200, json={"status": 1, "data": {"access_token": "limited-scope-token"}})
    client = DocumentologClient("https://apibusiness.documentolog.com", "https://apibusiness.documentolog.com", "test-key", transport=httpx.MockTransport(transport))
    assert "sParams=limited-scope-token" in client.create_session({}, "stable-command")
    assert client.safe_view_url("https://[invalid") is None


def test_real_settings_require_https_and_sender():
    from app.config import Settings
    fields = {"_env_file": None, "database_url": "postgresql+psycopg://user@localhost/settings_test", "jwt_secret": "test-settings-secret-at-least-32-chars", "zup_mode": "mock", "documentolog_mode": "real", "documentolog_api_key": "x" * 32,
        "documentolog_base_url": "https://apibusiness.documentolog.com", "documentolog_browser_url": "https://apibusiness.documentolog.com",
        "documentolog_public_url": "https://hr.test", "documentolog_callback_url": "https://hr.test", "documentolog_sender": "000000000000"}
    assert Settings(**fields).documentolog_mode == "real"
    for values in ({"documentolog_callback_url": "http://hr.test"}, {"documentolog_sender": None}, {"documentolog_api_key": None}):
        with pytest.raises(ValidationError):
            Settings(**(fields | values))


def test_decline_and_retry_after_callback_failure(api, docs, monkeypatch):
    client, path = docs
    item = approved(api)
    url = f"/api/requests/{item['id']}/documentolog"
    result = api.post(url, {}, "hr").json()
    token = parse_qs(urlparse(result["session_url"]).query)["sParams"][0]
    original = api.client.request
    def unavailable(method, url, **kwargs):
        if "/webhook/" in url:
            return httpx.Response(503, request=httpx.Request(method, "http://api.test" + url))
        return original(method, url, **kwargs)
    monkeypatch.setattr(api.client, "request", unavailable)
    assert client.post("/external/mock/decline", params={"sParams": token}).status_code == 503
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT status,delivered FROM documents").fetchone() == ("declined", 0)
    monkeypatch.setattr(api.client, "request", original)
    assert client.post("/external/mock/decline", params={"sParams": token}).status_code == 200
    assert api.get(url).json()["status"] == "declined"
    before = api.db.snapshot()
    assert client.post("/external/mock/decline", params={"sParams": token}).status_code == 200
    assert api.db.snapshot() == before
    assert api.get(f"/api/requests/{item['id']}").json()["status"] == "approved"


def test_expired_capability_links(api, docs):
    from datetime import timedelta
    from app.models import DocumentologDelivery, utcnow
    item = approved(api)
    url = f"/api/requests/{item['id']}/documentolog"
    api.post(url, {}, "hr")
    row = delivery(api, item["id"])
    with api.db.session() as db:
        db.get(DocumentologDelivery, row.id).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert api.client.get(f"/api/documentolog/files/{row.file_token}").status_code == 404
    assert api.client.post(f"/api/documentolog/webhook/{row.callback_token}", json={"event": "document_completed", "doc_id": "doc"}).status_code == 404
    assert api.get(url + "/session", "hr").status_code == 404


def test_real_completion_is_only_reported_not_verified(api, docs):
    from app.models import DocumentologDelivery
    item = approved(api)
    url = f"/api/requests/{item['id']}/documentolog"
    api.post(url, {}, "hr")
    row = delivery(api, item["id"])
    with api.db.session() as db:
        db.get(DocumentologDelivery, row.id).mode = "real"
        db.commit()
    result = api.client.post(f"/api/documentolog/webhook/{row.callback_token}", json={"event": "document_completed", "doc_id": "real-doc"})
    assert result.json()["status"] == "completed_reported"
    assert api.post(url, {}, "hr").status_code == 409  # mode switch cannot resend


def test_concurrent_hr_commands_create_one_external_document(api, docs):
    from concurrent.futures import ThreadPoolExecutor
    client, path = docs
    item = approved(api)
    api.headers("hr")
    url = f"/api/requests/{item['id']}/documentolog"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: api.post(url, {}, "hr"), range(2)))
    assert all(result.status_code == 200 for result in results)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    from app.models import DocumentologDelivery
    with api.db.session() as db:
        assert len(db.scalars(select(DocumentologDelivery)).all()) == 1


def test_docx_handles_untrusted_text_as_valid_xml():
    from datetime import date
    from types import SimpleNamespace
    from xml.etree import ElementTree
    from app.leave_document import leave_document
    item = SimpleNamespace(id=1, start_date=date(2027, 1, 11), end_date=date(2027, 1, 12),
        days_count=2, calendar_version="demo", comment="<tag>&\x00\ud800")
    employee = SimpleNamespace(company="Example", full_name="Демо", position="Role")
    with ZipFile(BytesIO(leave_document(item, employee, demo=True))) as document:
        tree = ElementTree.fromstring(document.read("word/document.xml"))
        assert "<tag>&" in "".join(tree.itertext())
