"""Run inside backend against the Compose stack; creates synthetic demo records.

docker compose exec -T backend python - < scripts/compose_smoke.py
The default URL exercises the frontend's /api proxy as well as FastAPI/PostgreSQL.
"""
import json
import os
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from sqlalchemy import select

from app.database import Base, get_engine
from app import models  # noqa: F401 — register all tables for the persistence snapshot


base = os.environ.get("API_BASE_URL", "http://frontend:3000/api").rstrip("/")


def call(method, path, body=None, token=None, expected=200, key=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if key:
        headers["Idempotency-Key"] = key
    request = Request(
        f"{base}{path}", method=method, headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        response = urlopen(request, timeout=20)
    except HTTPError as error:
        response = error
    with response:
        result = json.load(response)
        assert response.status == expected, (method, path, response.status, result)
        return result


assert call("GET", "/health") == {"status": "ok"}
tokens = {
    actor: call("POST", "/auth/login", {
        "email": f"{actor}@example.com", "password": os.environ["DEMO_PASSWORD"],
    })["access_token"]
    for actor in ("employee", "manager", "hr", "outsider")
}
assert call("GET", "/me", token=tokens["employee"])["role"] == "employee"
assert len(call("GET", "/employees", token=tokens["employee"])) == 1
assert len(call("GET", "/employees", token=tokens["manager"])) == 2
call("GET", "/audit", token=tokens["employee"], expected=403)

body = {"start_date": "2027-03-01", "end_date": "2027-03-05", "comment": "Docker smoke: synthetic demo"}
key = f"docker-smoke-{uuid4()}"
item = call("POST", "/requests", body, tokens["employee"], 201, key)
assert call("POST", "/requests", body, tokens["employee"], 201, key)["id"] == item["id"]
call("POST", "/requests", {**body, "comment": "conflicting command"}, tokens["employee"], 409, key)
path = f"/requests/{item['id']}"
decision = {"status": "approved", "version": item["version"], "comment": "Demo manager decision"}
call("PATCH", f"{path}/status", decision, tokens["employee"], 403)
call("GET", path, token=tokens["outsider"], expected=404)
approved = call("PATCH", f"{path}/status", decision, tokens["manager"])
assert approved["status"] == "approved" and len(approved["history"]) == 2
call("PATCH", f"{path}/status", decision, tokens["manager"], 409)
notifications = call("GET", "/notifications", token=tokens["employee"])
notification = next(n for n in notifications if f"№{item['id']}:" in n["body"])
for _ in range(2):
    assert call("PATCH", f"/notifications/{notification['id']}/read", token=tokens["employee"])["read"]

assert call("POST", "/courses/1/complete", {"answer_index": 0}, tokens["employee"])["completed"]
assert call("POST", "/courses/1/complete", {"answer_index": 0}, tokens["employee"])["completed"]
answer = call("POST", "/assistant/query", {"question": "Как подать заявку на отпуск?"}, tokens["employee"])
assert answer["mode"] == "extractive_demo" and answer["sources"]
assert call("GET", "/audit", token=tokens["hr"])


def snapshot():
    with get_engine().connect() as connection:
        return {
            table.name: connection.execute(select(table).order_by(*table.primary_key.columns)).all()
            for table in Base.metadata.sorted_tables
        }


before = snapshot()
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
subprocess.run([sys.executable, "-m", "alembic", "check"], check=True)
subprocess.run([sys.executable, "-m", "app.seed"], check=True)
subprocess.run([sys.executable, "-m", "app.seed"], check=True)
assert snapshot() == before, "Migration/seed changed populated database"
assert call("GET", path, token=tokens["employee"])["status"] == "approved"
print(f"Compose smoke passed: request {item['id']}, frontend proxy, four roles, idempotency, decision, notifications, course, sources; migration/seed preserve PostgreSQL data.")
