# AI Jana P0: citation authorization and grounded wording

**Status, 18 October 2026:** Agent A's two targeted tests reproduced the findings in [the 20-question evaluation](AI_JANA_EVALUATION.md). They were **red before the Integration Lead fix and green afterward** on isolated PostgreSQL. This document retains the original failure evidence; the current verification result is in [verification.md](verification.md).

## Reproduce without shared services

From the repository root in PowerShell, use a local backend image with the dependencies in `backend/requirements.lock`. If necessary, build it separately with `docker build -t digital-hr-backend:latest -f backend/Dockerfile backend`. Then:

```powershell
$auditRoot = (Get-Location).Path
docker run -d --rm --name jana-ai-p0-pg --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=512m -e POSTGRES_USER=jana_p0 -e POSTGRES_PASSWORD=jana_p0_only -e POSTGRES_DB=jana_p0 postgres:17-alpine
docker run --rm --network container:jana-ai-p0-pg --entrypoint python -e TEST_DATABASE_URL=postgresql+psycopg://jana_p0:jana_p0_only@127.0.0.1:5432/jana_p0 -e PYTHONDONTWRITEBYTECODE=1 -v "${auditRoot}\backend:/workspace/backend:ro" -v "${auditRoot}\knowledge_base_docs:/workspace/knowledge_base_docs:ro" -w /workspace/backend digital-hr-backend:latest -m pytest -q -p no:cacheprovider tests/test_assistant_p0_regressions.py
docker stop jana-ai-p0-pg
```

The [`api` fixture](../backend/tests/conftest.py) creates a random schema, migrates it to Alembic `0014`, seeds synthetic users, and drops the schema at teardown. It sets `LLM_PROVIDER=disabled` for ordinary requests; the second test calls the real wording guard through `httpx.MockTransport`. The corpus file is `knowledge_base_docs/HR-01.pdf`. No production data, shared Compose container, persistent volume or external LLM is involved. The disposable container used for this run was stopped and removed afterward.

**Baseline result on Agent A's checkout:** `2 failed, 1 warning in 6.93s`; both failures were final safety assertions, not setup failures. The Integration Lead reproduced `2 failed, 1 warning in 6.16s` on integrated `main`, then obtained `40 passed, 1 warning` across the focused assistant/security modules after the fix. The warning is the existing Starlette/httpx deprecation. No broad regression suite was run.

## Regression 1 — known citation after file restriction

[`test_known_citation_is_denied_after_parent_file_becomes_hr_only`](../backend/tests/test_assistant_p0_regressions.py) uses two independently authenticated roles, `employee` and `hr_admin` (`api.headers("hr")`). HR uploads the real synthetic `HR-01.pdf` as `all`. Both roles can initially retrieve the same known chunk ID from `GET /api/knowledge/{document_id}`. The test changes **only** the parent `KnowledgeFile.access_scope` to `hr_admin` in its private schema, leaving the previously indexed `KnowledgeDocument.access_scope=all`.

After the change, the employee correctly receives **404** from `/api/knowledge-files/{file_id}` and its download; HR still receives **200** from the citation endpoint. The expected employee citation result is **404**, but the current endpoint returns **200**, including the restricted title and passage.

**Root cause:** [`knowledge()` in `backend/app/modules/assistant.py`](../backend/app/modules/assistant.py) filters `KnowledgeDocument.access_scope` only. It does not join and check its parent `KnowledgeFile.access_scope`. General retrieval and historical citation reauthorization already check both scopes. A known document ID bypasses those safer paths.

**Implemented change:** In `backend/app/modules/assistant.py`, the direct source lookup uses the same outer join and predicate as `allowed_documents`: the chunk must be readable **and**, when `file_id` is present, its parent file must be readable. Unauthorized and missing chunks return 404. Legacy chunks with no parent file continue to follow their own scope. No API shape or migration changed.

## Regression 2 — unsupported claim receives `[1]`

[`test_mocked_unsupported_approval_claim_cannot_receive_citation`](../backend/tests/test_assistant_p0_regressions.py) uploads `HR-01.pdf`, asks «Как оформить отпуск?», and supplies this deterministic mock provider output:

> Отпуск автоматически одобряется после подачи заявки.

The selected `HR-01` §02 passage describes **submitting** a request. It does not say approval is automatic. The current server returns the mock sentence under a demo prefix with `[1]` and the `HR-01` source. The test expects a cited, supported extractive answer **without** the mock sentence; its final assertion currently fails.

**Root cause:** [`safe_answer()` in `backend/app/modules/assistant_llm.py`](../backend/app/modules/assistant_llm.py) allows a generated sentence when any terms overlap the passage and its numbers fit. The approval form «одобряется» is outside its narrow forbidden-output regex. [`answer_from_documents()` in `backend/app/modules/assistant.py`](../backend/app/modules/assistant.py) then adds a server citation to accepted wording without checking that the new claim is entailed by the passage. Prompt instructions alone do not enforce grounding.

**Conservative fallback now in place:** Generated wording is accepted only when it repeats one or more contiguous, complete sentences of the selected authorized passage, with only whitespace/case differences. Extra conclusions, paraphrases, dropped negations and reordered sentences return `None` from `generate_answer`, so the existing server path uses extracted evidence with the same authorized source and `[1]`. `NO_EVIDENCE` remains a refusal with `sources=[]`. This limits freeform wording; it does not prove that the selected evidence answers every question.

**Implemented change:** `backend/app/modules/assistant_llm.py` now applies that fail-closed check. Existing `None` → extractive fallback and `NO_EVIDENCE` → refusal behavior remain; mocked-provider tests and contract documentation were updated. No frontend, migration, retrieval rebuild or new dependency was required.

## Acceptance after the Integration Lead fix

1. Both tests in `backend/tests/test_assistant_p0_regressions.py` pass on isolated PostgreSQL.
2. `employee` gets 404 for a known chunk after its parent file becomes HR-only; `hr_admin` still gets 200. Ordinary retrieval, history replay, file metadata and download remain consistent with this rule.
3. The mock automatic-approval sentence never reaches `answer`, even with overlapping words. A supported extractive answer retains its server source and `[1]`; lack of adequate evidence produces the existing refusal without a citation.
4. The focused assistant authorization and mocked-provider tests pass after updating expectations for the stricter generated-wording policy. Real-provider semantic accuracy remains unverified by these mocks.

All four checks passed in the focused PostgreSQL run reported in [verification.md](verification.md). The historical 20-question retrieval matrix was not rerun; its six answer-quality failures remain separate work.
