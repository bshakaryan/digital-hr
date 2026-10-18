"""Expected-safe AI Jana behavior for two confirmed P0 regressions.

Run only with TEST_DATABASE_URL pointing to an isolated PostgreSQL instance.
The shared api fixture migrates and drops a private schema; the LLM uses MockTransport.
These tests intentionally fail until the Integration Lead fixes the backend paths.
"""

from pathlib import Path

import httpx
from sqlalchemy import select

from app.config import Settings
from app.models import KnowledgeDocument, KnowledgeFile
from app.modules import assistant, assistant_llm


CORPUS = Path(__file__).resolve().parents[2] / "knowledge_base_docs"


def upload_leave_document(api):
    response = api.client.post(
        "/api/knowledge-files",
        headers=api.headers("hr"),
        data={"title": "Подача и согласование отпуска", "version": "test", "language": "ru",
              "classification": "synthetic_demo", "access_scope": "all"},
        files={"file": ("HR-01.pdf", (CORPUS / "HR-01.pdf").read_bytes())},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_known_citation_is_denied_after_parent_file_becomes_hr_only(api):
    file_id = upload_leave_document(api)
    with api.db.session() as db:
        document = db.scalar(select(KnowledgeDocument).where(
            KnowledgeDocument.file_id == file_id,
            KnowledgeDocument.section == "02. Подача заявки",
        ).order_by(KnowledgeDocument.id))
        assert document is not None and document.access_scope == "all"
        document_id = document.id

    citation = f"/api/knowledge/{document_id}"
    assert api.get(citation, "employee").status_code == 200
    assert api.get(citation, "hr").status_code == 200

    # Model an access-policy change without rewriting previously indexed chunks.
    with api.db.session() as db:
        file = db.get(KnowledgeFile, file_id)
        file.access_scope = "hr_admin"
        db.commit()

    # The file and its download are already denied to the employee. The chunk
    # citation must obey the same parent-file rule, even with a known ID.
    assert api.get(f"/api/knowledge-files/{file_id}", "employee").status_code == 404
    assert api.get(f"/api/knowledge-files/{file_id}/download", "employee").status_code == 404
    assert api.get(citation, "hr").status_code == 200
    denied = api.get(citation, "employee")
    assert denied.status_code == 404, "employee could read a chunk after its parent file was restricted"


def test_mocked_unsupported_approval_claim_cannot_receive_citation(api, monkeypatch):
    upload_leave_document(api)
    fabricated = "Отпуск автоматически одобряется после подачи заявки."
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
            "message": {"content": fabricated}}]})

    settings = Settings(
        _env_file=None,
        database_url=api.db.engine.url.render_as_string(hide_password=False),
        jwt_secret=api.db.secret,
        llm_provider="openai_compatible",
        llm_api_key="test-provider-key",
        openai_api_key=None,
    )
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(assistant, "generate_answer", lambda question, passage, _:
        assistant_llm.generate_answer(question, passage, settings, transport=transport))

    response = api.post("/api/assistant/query", {"question": "Как оформить отпуск?"})
    assert response.status_code == 200, response.text
    answer = response.json()
    assert len(requests) == 1  # The injected wording came from a mocked provider.
    # The retrieved passage supports a cited extractive fallback, but it does
    # not support automatic approval. Preserve that valid server citation.
    assert answer["sources"] and answer["sources"][0]["section"] == "02. Подача заявки"
    assert answer["answer"].endswith(" [1]")
    assert fabricated not in answer["answer"], "unsupported automatic-approval claim was cited"
