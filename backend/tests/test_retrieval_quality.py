"""Actual-corpus retrieval checks on the temporary migrated database fixture."""

import json
import os
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.config import Settings
from app.models import Employee, KnowledgeDocument
from app.modules import assistant, assistant_llm
from app.modules.knowledge_ingestion import UploadDetails, ingest_file


@pytest.fixture
def corpus(api):
    directory = Path(os.environ.get("TEST_CORPUS_DIR", Path(__file__).resolve().parents[2] / "knowledge_base_docs"))
    manifest = json.loads((Path(__file__).resolve().parents[1] / "app" / "corpus_manifest.json").read_text(encoding="utf-8"))
    assert all((directory / entry["filename"]).is_file() for entry in manifest)
    with api.db.session() as db:
        actor_id = db.scalar(select(Employee.id).where(Employee.email == "hr@example.com"))
    imported = {}
    for entry in manifest:
        with api.db.session() as db:
            file, created = ingest_file(db, data=(directory / entry["filename"]).read_bytes(),
                filename=entry["filename"], details=UploadDetails(**{key: value for key, value in entry.items() if key != "filename"}),
                actor_id=actor_id)
            assert created
            imported[entry["document_code"]] = file.id
    return imported


def test_actual_corpus_selects_supported_sections_and_refuses_unknown(api, corpus):
    for question in ("Как оформить отпуск?", "Как подать заявку на отпуск?"):
        response = api.post("/api/assistant/query", {"question": question})
        assert response.status_code == 200
        answer = response.json()
        assert not answer["escalate_to_hr"]
        assert len(answer["sources"]) == 1
        source = answer["sources"][0]
        assert (source["file_id"], source["source_filename"], source["section"], source["page_number"]) == (
            corpus["HR-01"], "HR-01.pdf", "02. Подача заявки", 1)
        assert api.get(f"/api/knowledge/{source['document_id']}").json() == source
        assert "отпуск" in answer["answer"].lower()
        assert "Практический контекст" not in answer["answer"]

    hiring = api.post("/api/assistant/query", {"question": "Как оформить приём на работу?"}).json()
    assert hiring["sources"] and hiring["sources"][0]["document_code"] == "KZ-LC-414-V"
    assert hiring["sources"][0]["section"].startswith("Статья 34.")
    assert corpus["HR-01"] not in {source.get("file_id") for source in hiring["sources"]}

    damaged = api.post("/api/assistant/query", {"question": "Что делать с повреждённой посылкой?"}).json()
    assert damaged["sources"] and damaged["sources"][0]["document_code"] in {"LOG-02", "OPS-03"}
    assert "повреж" in damaged["sources"][0]["content"].lower()

    unknown = api.post("/api/assistant/query", {"question": "Какова орбита Нептуна?"}).json()
    assert unknown["escalate_to_hr"] and unknown["sources"] == []


def test_permissions_and_course_scope_still_precede_retrieval(api, corpus, monkeypatch):
    with api.db.session() as db:
        private = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.access_scope == "hr_admin"))
        private_id = private.id
    assert api.get(f"/api/knowledge/{private_id}").status_code == 404
    seen = []
    monkeypatch.setattr(assistant, "generate_answer", lambda *args: seen.append(args) or None)
    restricted = api.post("/api/assistant/query", {"question": "аудит журнал"}).json()
    assert restricted["sources"] == [] and restricted["escalate_to_hr"]
    assert not seen

    assert api.post("/api/courses/1/materials", {"file_id": corpus["HR-01"]}, "hr").status_code == 200
    course = api.post("/api/courses/1/ask", {"question": "Как оформить отпуск?"}).json()
    assert course["sources"] and course["sources"][0]["file_id"] == corpus["HR-01"]
    assert course["sources"][0]["source_type"] == "course"
    before = len(seen)
    unrelated = api.post("/api/courses/1/ask", {"question": "Что делать с повреждённой посылкой?"}).json()
    assert unrelated["sources"] == [] and unrelated["escalate_to_hr"]
    assert len(seen) == before


def test_mocked_provider_and_extract_fallback_keep_same_citation(api, corpus, monkeypatch):
    settings = Settings(_env_file=None, database_url="sqlite:///unused.sqlite3",
        jwt_secret="test-only-jwt-secret-never-use-outside-pytest-2026",
        llm_provider="openai_compatible", llm_api_key="test-provider-key", openai_api_key=None)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": "Сотрудник открывает «Заявки», выбирает отпуск, указывает даты и отправляет запрос."}}]})

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(assistant, "generate_answer", lambda question, passage, _: assistant_llm.generate_answer(
        question, passage, settings, transport=transport))
    generated = api.post("/api/assistant/query", {"question": "Как оформить отпуск?"}).json()
    assert generated["sources"][0]["file_id"] == corpus["HR-01"]
    assert generated["sources"][0]["section"] == "02. Подача заявки"
    assert generated["answer"].endswith(" [1]") and len(requests) == 1
    sent = json.loads(requests[0].content)["messages"][1]["content"]
    assert "Сотрудник открывает" in sent and "Оформление приема на работу" not in sent

    monkeypatch.setattr(assistant, "generate_answer", lambda question, passage, _: assistant_llm.generate_answer(
        question, passage, settings, transport=httpx.MockTransport(lambda _: httpx.Response(503))))
    fallback = api.post("/api/assistant/query", {"question": "Как оформить отпуск?"}).json()
    assert fallback["sources"] == generated["sources"]
    assert fallback["answer"].endswith(" [1]") and not fallback["escalate_to_hr"]
