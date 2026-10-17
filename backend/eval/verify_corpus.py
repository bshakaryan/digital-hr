"""Live read-only retrieval checks plus idempotent course attachments for the supplied corpus."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import httpx

BASE = "http://backend:8000/api"
CORPUS = Path("/corpus")
EMAIL = {"employee": "employee@example.com", "hr": "hr@example.com"}


def main():
    with httpx.Client(timeout=30) as client:
        auth = {}
        for role, email in EMAIL.items():
            response = client.post(BASE + "/auth/login", json={"email": email, "password": os.environ["DEMO_PASSWORD"]})
            response.raise_for_status()
            auth[role] = {"Authorization": "Bearer " + response.json()["access_token"]}
        files_response = client.get(BASE + "/knowledge-files", headers=auth["hr"])
        files_response.raise_for_status()
        files = files_response.json()
        by_name = {item["filename"]: item for item in files}
        expected = {path.name for path in CORPUS.iterdir() if path.suffix.lower() in {".pdf", ".docx"}}
        assert expected == set(by_name), (expected - set(by_name), set(by_name) - expected)
        for name, item in by_name.items():
            assert item["sha256"] == hashlib.sha256((CORPUS / name).read_bytes()).hexdigest()
            assert item["chunk_count"] > 0
            original = client.get(BASE + f"/knowledge-files/{item['id']}/download", headers=auth["employee"])
            original.raise_for_status()
            assert hashlib.sha256(original.content).hexdigest() == item["sha256"]
        assert client.get(BASE + "/knowledge-files", headers=auth["employee"]).status_code == 403
        attached = []
        for name in ("HR-01.pdf", "HR-02.pdf", "LMS-01.pdf"):
            result = client.post(BASE + "/courses/1/materials", headers=auth["hr"], json={"file_id": by_name[name]["id"]})
            result.raise_for_status()
            attached.append(result.json()["id"])
        sources = client.get(BASE + "/courses/1/materials", headers=auth["employee"])
        sources.raise_for_status()
        assert {row["id"] for row in sources.json()} == set(attached)
        questions = {
            "pdf_leave": "Как в HR-01 описана подача заявки на отпуск?",
            "docx_service": "Как в CS-01 отделять подтверждённый факт от предположения в клиентском обращении?",
            "docx_ops": "Что в OPS-02 сказано о качестве данных статуса отправления?",
            "legal_snapshot": "Какие основные понятия перечислены в статье 1 Трудового кодекса?",
            "unanswerable": "Какова орбита Нептуна?",
        }
        outcomes = {}
        for label, question in questions.items():
            response = client.post(BASE + "/assistant/query", headers=auth["employee"], json={"question": question})
            response.raise_for_status()
            answer = response.json()
            for source in answer["sources"]:
                check = client.get(BASE + f"/knowledge/{source['document_id']}", headers=auth["employee"])
                assert check.status_code == 200 and check.json() == source
            outcomes[label] = {"answer": answer["answer"], "sources": [
                {"filename": row.get("source_filename"), "section": row["section"], "page": row.get("page_number"),
                 "classification": row.get("classification")} for row in answer["sources"]]}
        for label, question in {
            "course_intro": "Как в материалах курса описано обучение в Jana Academy?",
            "course_logistics": "Что в OPS-02 сказано о качестве данных статуса отправления?",
        }.items():
            response = client.post(BASE + "/courses/1/ask", headers=auth["employee"], json={"question": question})
            response.raise_for_status()
            answer = response.json()
            assert all(row.get("file_id") in attached for row in answer["sources"])
            outcomes[label] = {"answer": answer["answer"], "sources": [
                {"filename": row.get("source_filename"), "section": row["section"]} for row in answer["sources"]]}
        print(json.dumps({"files": len(files), "chunks": sum(item["chunk_count"] for item in files),
                          "attached_to_course_1": attached, "outcomes": outcomes}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
