"""Small labeled, seeded-corpus HTTP evaluation; run from backend/."""
import json
import os
import sys
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
cases = json.loads((Path(__file__).parent / "assistant_questions.json").read_text(encoding="utf-8"))
with tempfile.TemporaryDirectory() as directory:
    os.environ.update(DATABASE_URL=f"sqlite:///{Path(directory) / 'eval.db'}",
                      JWT_SECRET="evaluation-only-secret-long-enough-2026",
                      DEMO_PASSWORD="evaluation-only-password-2026")
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    from app.seed import seed
    from app.main import app
    seed()
    with TestClient(app) as client:
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
    from app.database import get_engine
    get_engine().dispose()
