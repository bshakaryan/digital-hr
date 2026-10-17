"""Small labeled, seeded-corpus HTTP evaluation; run from backend/."""
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import get_settings, postgres_database_url
from app.database import get_engine


ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
cases = json.loads((Path(__file__).parent / "assistant_questions.json").read_text(encoding="utf-8"))


@contextmanager
def evaluation_client():
    configured = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not configured:
        raise SystemExit("Set TEST_DATABASE_URL (or DATABASE_URL) to PostgreSQL, or run inside Docker Compose")
    url = make_url(postgres_database_url(configured))
    schema = "jana_eval_" + uuid4().hex
    admin = create_engine(url)
    created = False
    secret = "evaluation-only-secret-long-enough-2026"
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        scenario_url = url.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "DATABASE_URL": scenario_url, "JWT_SECRET": secret, "ZUP_API_TOKEN": secret,
            "DEMO_PASSWORD": "evaluation-only-password-2026", "ZUP_MODE": "mock", "DOCUMENTOLOG_MODE": "disabled",
            "LLM_PROVIDER": "disabled", "LLM_API_KEY": "", "OPENAI_API_KEY": "",
        }):
            get_settings.cache_clear()
            from app.mock_zup import create_mock_app
            from app.modules.integrations import HttpZupAdapter
            with TestClient(create_mock_app(str(Path(directory) / "zup.sqlite3"), secret)) as mock:
                def transport(request):
                    return mock.request(request.method, request.url.path, headers=dict(request.headers), content=request.content)

                adapter = HttpZupAdapter("http://zup.test/hs/jana/v1", secret, httpx.MockTransport(transport))
                with patch("app.seed.zup_adapter", return_value=adapter), patch("app.modules.integrations.zup_adapter", return_value=adapter):
                    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
                    from app.seed import seed
                    from app.main import app
                    seed()
                    with TestClient(app) as client:
                        yield client
    finally:
        if get_engine.cache_info().currsize:
            get_engine().dispose()
        get_engine.cache_clear()
        get_settings.cache_clear()
        try:
            if created:
                with admin.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            admin.dispose()


with evaluation_client() as client:
    tokens = {}
    for role in {case["role"] for case in cases}:
        login = client.post("/api/auth/login", json={"email": f"{role}@example.com", "password": os.environ["DEMO_PASSWORD"]})
        login.raise_for_status()
        tokens[role] = {"Authorization": f"Bearer {login.json()['access_token']}"}
    good = supported = factual = refused = 0
    answerable = sum(case["document_id"] is not None for case in cases)
    unanswerable = len(cases) - answerable
    for case in cases:
        response = client.post("/api/assistant/query", json={"question": case["question"]}, headers=tokens[case["role"]])
        response.raise_for_status()
        result = response.json()
        ids = [item["document_id"] for item in result["sources"]]
        correct = case["document_id"] == (ids[0] if ids else None)
        good += correct and case["document_id"] is not None
        refused += correct and case["document_id"] is None and result["escalate_to_hr"]
        factual += bool(correct and case.get("fact") and case["fact"] in result["answer"])
        if ids:
            cited = result["sources"][0]
            quoted = result["answer"].removeprefix("По демонстрационной базе: ").removesuffix(" [1]")
            supported += bool(client.get(f"/api/knowledge/{cited['document_id']}", headers=tokens[case["role"]]).json() == cited
                              and all(part.strip() in cited["content"] for part in quoted.split(". ") if part.strip()))
        print(f"{'PASS' if correct else 'MISS'} {case['role']:8} expected={case['document_id']} got={ids[:1]} fact={case.get('fact', '') in result['answer'] if case.get('fact') else '-'} {case['question']}")
    print(f"retrieval_top1={good}/{answerable}; labeled_fact={factual}/{answerable}; citation_supported={supported}/{answerable}; refusals={refused}/{unanswerable}")
