"""Generic AI Jana questions against actual provisioned demo course materials."""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Course, CourseMaterial, Employee, KnowledgeDocument, KnowledgeFile
from app.modules.knowledge_ingestion import UploadDetails, ingest_file
from app.provision_academy_demo import provision


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "backend" / "app" / "corpus_manifest.json"


def test_generic_course_questions_use_attached_evidence(api, monkeypatch):
    # The production import and demo provisioner use ingest_file and the same
    # manifest. Run them inside the fixture's temporary PostgreSQL schema.
    monkeypatch.setattr("app.modules.assistant.generate_answer",
                        lambda *args: pytest.fail("LLM must not receive a generic course overview"))
    with api.db.session() as db:
        hr_id = db.scalar(select(Employee.id).where(Employee.email == "hr@example.com"))
    files = {}
    for entry in json.loads(MANIFEST.read_text(encoding="utf-8")):
        with api.db.session() as db:
            file, created = ingest_file(
                db, data=(ROOT / "knowledge_base_docs" / entry["filename"]).read_bytes(),
                filename=entry["filename"], actor_id=hr_id,
                details=UploadDetails(**{key: value for key, value in entry.items() if key != "filename"}),
            )
            assert created
            files[entry["document_code"]] = file.id
    provisioned = provision()
    assert provisioned["created_courses"] == 12

    with api.db.session() as db:
        courses = {item.demo_code: item.id for item in db.scalars(select(Course).where(
            Course.demo_code.in_(("DEMO-ONB-01", "DEMO-ONB-02", "DEMO-LOG-02", "DEMO-LOG-03")))).all()}
        attached = {code: set(db.scalars(select(CourseMaterial.file_id).where(
            CourseMaterial.course_id == course_id)).all()) for code, course_id in courses.items()}
        assert attached["DEMO-ONB-01"] == {files["HR-02"]}
        assert attached["DEMO-ONB-02"] == {files["HR-01"]}
        assert attached["DEMO-LOG-02"] == {files["LOG-02"]}
        assert attached["DEMO-LOG-03"] == {files["LOG-02"], files["OPS-02"]}
        assert db.scalar(select(KnowledgeDocument.id).where(
            KnowledgeDocument.file_id == files["HR-02"])) is not None

    cases = (
        ("employee", "DEMO-ONB-01", "О чём этот материал?", "HR-02", "JanaМен объединяет профиль"),
        ("employee", "DEMO-ONB-01", "Что изучается в этом курсе?", "HR-02", "JanaМен объединяет профиль"),
        ("manager", "DEMO-LOG-02", "Расскажи об этом материале.", "LOG-02", "Создание записи не означает физического приёма"),
        ("employee", "DEMO-ONB-02", "Что важно запомнить?", "HR-01", "промежуточный этап, а не окончательное разрешение"),
        ("employee", "DEMO-LOG-03", "О чём этот курс?", "OPS-02", "Если статус не подтверждён"),
    )
    failures = []
    overview_conversation_id = None
    for actor, code, question, document_code, expected_phrase in cases:
        body = {"question": question}
        if overview_conversation_id is None:
            body["client_turn_id"] = "course-overview-1"
        response = api.post(f"/api/courses/{courses[code]}/ask", body, actor)
        assert response.status_code == 200, response.text
        answer = response.json()
        if "client_turn_id" in body:
            overview_conversation_id = answer["conversation_id"]
        if (answer["escalate_to_hr"] or len(answer["sources"]) != 1
                or answer["sources"][0].get("document_code") != document_code
                or answer["sources"][0]["source_type"] != "course"
                or expected_phrase not in answer["answer"]):
            failures.append((code, question, answer["answer"],
                             [item.get("document_code") for item in answer["sources"]]))
        if answer["sources"]:
            cited = answer["sources"][0]
            direct = api.get(f"/api/knowledge/{cited['document_id']}", actor)
            assert direct.status_code == 200
            assert {key: value for key, value in cited.items() if key != "source_type"} == {
                key: value for key, value in direct.json().items() if key != "source_type"}
            normalized_source = " ".join(cited["content"].split())
            excerpt = answer["answer"].split(": ", 1)[1].removesuffix(" [1]")
            assert excerpt in normalized_source
    assert not failures, failures

    unrelated = api.post(f"/api/courses/{courses['DEMO-ONB-01']}/ask",
                         {"question": "Какова орбита Нептуна?"}).json()
    assert unrelated["escalate_to_hr"] and unrelated["sources"] == []
    not_in_material = api.post(f"/api/courses/{courses['DEMO-ONB-01']}/ask",
                               {"question": "Как заказать корпоративное такси?"}).json()
    assert not_in_material["escalate_to_hr"] and not_in_material["sources"] == []
    general = api.post("/api/assistant/query", {"question": "О чём этот материал?"}).json()
    assert general["escalate_to_hr"] and general["sources"] == []
    no_files = api.post("/api/courses/1/ask", {"question": "О чём этот материал?"}).json()
    assert no_files["escalate_to_hr"] and no_files["sources"] == []
    with api.db.session() as db:
        unassigned_id = db.scalar(select(Course.id).where(Course.demo_code == "DEMO-LOG-04"))
    assert api.post(f"/api/courses/{unassigned_id}/ask",
                    {"question": "О чём этот материал?"}, "manager").status_code == 404

    # If the attached file becomes unreadable, deictic questions must refuse.
    with api.db.session() as db:
        db.get(KnowledgeFile, files["HR-02"]).access_scope = "hr_admin"
        db.commit()
    hidden = api.post(f"/api/courses/{courses['DEMO-ONB-01']}/ask",
                      {"question": "О чём этот материал?"}).json()
    assert hidden["escalate_to_hr"] and hidden["sources"] == []
    history = api.get(f"/api/assistant/conversations/{overview_conversation_id}").json()
    assert history["messages"][1]["sources"] == []
    assert "больше недоступны" in history["messages"][1]["text"]
