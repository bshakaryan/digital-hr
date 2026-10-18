"""Persistent assistant history and access checks on isolated PostgreSQL."""
from pathlib import Path

from alembic import command
from sqlalchemy import select, text

from app.models import AssistantConversation, AssistantTurn, CourseAssignment, KnowledgeFile

CORPUS = Path(__file__).resolve().parents[2] / "knowledge_base_docs"


def test_migration_from_populated_0013_keeps_existing_academy_rows(postgres_schema):
    command.upgrade(postgres_schema.config, "0013")
    with postgres_schema.engine.begin() as db:
        db.execute(text("""INSERT INTO employees
            (id,email,password_hash,full_name,role,company,position,department,hire_date,leave_balance)
            VALUES (1,'history@example.com','test','History','employee','Demo','Role','Team','2025-01-01',12)"""))
        db.execute(text("""INSERT INTO courses
            (id,title,description,content,duration_minutes,question,options_json,correct_index)
            VALUES (1,'Existing course','old','old',10,'Question','[\"yes\",\"no\"]',0)"""))
        db.execute(text("""INSERT INTO course_assignments
            (id,employee_id,course_id,progress,completed,learning_track)
            VALUES (1,1,1,100,true,'onboarding')"""))
    command.upgrade(postgres_schema.config, "0014")
    with postgres_schema.engine.connect() as db:
        assert db.execute(text("SELECT progress,completed,learning_track FROM course_assignments WHERE id=1")).one() == (
            100, True, "onboarding")
        assert db.scalar(text("SELECT COUNT(*) FROM assistant_conversations")) == 0
        assert db.scalar(text("SELECT COUNT(*) FROM assistant_turns")) == 0


def upload_leave(api):
    response = api.client.post("/api/knowledge-files", headers=api.headers("hr"),
        data={"title": "Оформление отпуска", "version": "test", "language": "ru",
              "classification": "synthetic_demo", "access_scope": "all"},
        files={"file": ("HR-01.pdf", (CORPUS / "HR-01.pdf").read_bytes())})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def ask(api, question="Как оформить отпуск?", **fields):
    return api.post("/api/assistant/query", {"question": question, **fields})


def test_create_reopen_relogin_and_paginate(api, monkeypatch):
    monkeypatch.setattr("app.modules.assistant.generate_answer", lambda *args: None)
    upload_leave(api)
    first = ask(api, client_turn_id="leave-1")
    assert first.status_code == 200 and first.json()["sources"]
    conversation_id = first.json()["conversation_id"]
    assert first.json()["turn_id"] and first.json()["client_turn_id"] == "leave-1"
    second = ask(api, "Какие документы есть в базе знаний?", conversation_id=conversation_id,
        client_turn_id="inventory-2")
    assert second.status_code == 200 and second.json()["conversation_id"] == conversation_id
    listing = api.get("/api/assistant/conversations?page=1&page_size=1").json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == conversation_id
    new = ask(api, "Неизвестный вопрос про полёт на Марс", client_turn_id="other-1")
    assert new.status_code == 200 and new.json()["conversation_id"] != conversation_id
    listing = api.get("/api/assistant/conversations?page=1&page_size=1").json()
    assert listing["total"] == 2 and len(listing["items"]) == 1
    assert len(api.get("/api/assistant/conversations?page=2&page_size=1").json()["items"]) == 1
    token = api.client.post("/api/auth/login", json={"email": "employee@example.com",
        "password": api.db.password}).json()["access_token"]
    reopened = api.client.get(f"/api/assistant/conversations/{conversation_id}?page=1&page_size=1",
        headers={"Authorization": f"Bearer {token}"}).json()
    assert reopened["total_turns"] == 2 and len(reopened["messages"]) == 2
    assert reopened["messages"][0]["role"] == "user"
    assert reopened["messages"][1]["sources"][0]["section"] == first.json()["sources"][0]["section"]
    page_two = api.get(f"/api/assistant/conversations/{conversation_id}?page=2&page_size=1").json()
    assert len(page_two["messages"]) == 2 and page_two["messages"][1]["sources"] == []
    assert "Оформление отпуска" in page_two["messages"][1]["text"]


def test_idempotence_scope_and_user_isolation(api, monkeypatch):
    monkeypatch.setattr("app.modules.assistant.generate_answer", lambda *args: None)
    upload_leave(api)
    first = ask(api, client_turn_id="same-turn").json()
    with api.db.session() as db:
        before = (db.query(AssistantConversation).count(), db.query(AssistantTurn).count())
    duplicate = ask(api, client_turn_id="same-turn")
    assert duplicate.status_code == 200 and duplicate.json()["turn_id"] == first["turn_id"]
    assert ask(api, "Другой вопрос", client_turn_id="same-turn").status_code == 409
    assert ask(api, client_turn_id="same-turn", conversation_id=999999).status_code == 409
    with api.db.session() as db:
        assert (db.query(AssistantConversation).count(), db.query(AssistantTurn).count()) == before
    assert api.get(f"/api/assistant/conversations/{first['conversation_id']}", "manager").status_code == 404
    assert api.get("/api/assistant/conversations", "manager").json()["total"] == 0
    assert api.post("/api/assistant/query", {"question": "Как оформить отпуск?",
        "conversation_id": first["conversation_id"]}, "manager").status_code == 404
    assert api.get("/api/assistant/conversations?page_size=101").status_code == 422


def test_course_scope_and_revalidated_historical_citation(api, monkeypatch):
    from test_academy_tracks import published_course

    monkeypatch.setattr("app.modules.assistant.generate_answer", lambda *args: None)
    course_id = published_course(api)
    employee_id = api.get("/api/me").json()["id"]
    assert api.post(f"/api/courses/{course_id}/assign", {"employee_id": employee_id}, "hr").status_code == 200
    question = "Что отражает статус отправления?"
    response = api.post(f"/api/courses/{course_id}/ask", {"question": question,
        "client_turn_id": "course-1"})
    assert response.status_code == 200 and response.json()["sources"]
    payload = response.json()
    assert payload["sources"][0]["source_type"] == "course"
    assert api.post("/api/assistant/query", {"question": question,
        "conversation_id": payload["conversation_id"]}).status_code == 404
    assert api.post(f"/api/courses/1/ask", {"question": question,
        "conversation_id": payload["conversation_id"]}).status_code == 404
    assert api.get(f"/api/assistant/conversations/{payload['conversation_id']}", "manager").status_code == 404
    with api.db.session() as db:
        turn = db.get(AssistantTurn, payload["turn_id"])
        assert "content" not in turn.source_refs_json and "Статус" not in turn.source_refs_json
        file = db.get(KnowledgeFile, payload["sources"][0]["file_id"])
        file.access_scope = "hr_admin"
        db.commit()
    history = api.get(f"/api/assistant/conversations/{payload['conversation_id']}").json()
    answer = history["messages"][1]
    assert answer["sources"] == [] and "больше недоступны" in answer["text"]
    assert payload["answer"] not in answer["text"]
    retry = api.post(f"/api/courses/{course_id}/ask", {"question": question,
        "client_turn_id": "course-1"}).json()
    assert retry["sources"] == [] and "больше недоступны" in retry["answer"]
    fresh = api.post(f"/api/courses/{course_id}/ask", {"question": question,
        "client_turn_id": "course-2"}).json()
    assert fresh["sources"] == [] and fresh["escalate_to_hr"] is True
    with api.db.session() as db:
        assignment = db.scalar(select(CourseAssignment).where(CourseAssignment.course_id == course_id,
            CourseAssignment.employee_id == employee_id))
        db.delete(assignment)
        db.commit()
    assert api.get(f"/api/assistant/conversations/{payload['conversation_id']}").status_code == 404
    assert api.post(f"/api/courses/{course_id}/ask", {"question": question,
        "client_turn_id": "course-1"}).status_code == 404


def test_inventory_history_rechecks_current_visibility(api, monkeypatch):
    monkeypatch.setattr("app.modules.assistant.generate_answer", lambda *args: None)
    file_id = upload_leave(api)
    cited = ask(api, client_turn_id="cited-1").json()
    assert cited["sources"]
    answer = ask(api, "Какие документы есть в базе знаний?", client_turn_id="inventory-1").json()
    assert "Оформление отпуска" in answer["answer"]
    with api.db.session() as db:
        db.get(KnowledgeFile, file_id).access_scope = "hr_admin"
        db.commit()
    history = api.get(f"/api/assistant/conversations/{answer['conversation_id']}").json()
    assert "Оформление отпуска" not in history["messages"][1]["text"]
    assert history["messages"][1]["sources"] == []
    cited_history = api.get(f"/api/assistant/conversations/{cited['conversation_id']}").json()
    assert cited_history["messages"][1]["sources"] == []
    assert "больше недоступны" in cited_history["messages"][1]["text"]
