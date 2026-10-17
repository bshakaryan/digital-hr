"""One real Compose API scenario using an already imported OPS-02 document."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

import httpx

BASE = "http://backend:8000/api"


def main():
    with httpx.Client(timeout=30) as client:
        headers = {}
        for role in ("hr", "employee", "outsider"):
            response = client.post(BASE + "/auth/login", json={"email": f"{role}@example.com", "password": os.environ["DEMO_PASSWORD"]})
            response.raise_for_status()
            headers[role] = {"Authorization": "Bearer " + response.json()["access_token"]}

        def get(path, role="employee"):
            result = client.get(BASE + path, headers=headers[role])
            result.raise_for_status()
            return result.json()

        def post(path, data, role="employee"):
            result = client.post(BASE + path, json=data, headers=headers[role])
            result.raise_for_status()
            return result.json()

        before = get("/courses/rewards")
        files = get("/knowledge-files", "hr")
        material = next(file for file in files if file["filename"] == "OPS-02.docx")
        employee_id = get("/employees")[0]["id"]
        title = "Демо · статусы отправлений · " + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        draft = post("/courses", {"title": title, "description": "Учебный курс по подтверждённым событиям",
            "objectives": "Отличать подтверждённый статус от предположения", "duration_minutes": 8}, "hr")
        assert draft["status"] == "draft"
        course_id = draft["id"]
        assert client.get(BASE + f"/courses/{course_id}", headers=headers["employee"]).status_code == 404
        assert client.post(BASE + "/courses", json={"title": "x"}, headers=headers["employee"]).status_code == 403
        attached = post(f"/courses/{course_id}/materials", {"file_id": material["id"]}, "hr")
        assert attached["id"] == material["id"]
        quiz = client.put(BASE + f"/courses/{course_id}/quiz", headers=headers["hr"], json={
            "question": "Что отражает статус отправления?",
            "options": ["Подтверждённое событие", "Непроверенное предположение"], "correct_index": 0})
        quiz.raise_for_status()
        assert post(f"/courses/{course_id}/publish", {}, "hr")["status"] == "published"
        assert post(f"/courses/{course_id}/assign", {"employee_id": employee_id}, "hr")["assigned"] is True
        assert post(f"/courses/{course_id}/assign", {"employee_id": employee_id}, "hr")["assigned"] is False
        assert client.get(BASE + f"/courses/{course_id}", headers=headers["outsider"]).status_code == 404
        course = get(f"/courses/{course_id}")
        assert course["progress"] == 0 and not course["completed"]
        assert material["id"] in [file["id"] for file in get(f"/courses/{course_id}/materials")]
        download = client.get(BASE + f"/knowledge-files/{material['id']}/download", headers=headers["employee"])
        download.raise_for_status()
        assert hashlib.sha256(download.content).hexdigest() == material["sha256"]
        answer = post(f"/courses/{course_id}/ask", {"question": "Что отражает статус отправления?"})
        assert answer["sources"] and answer["sources"][0]["file_id"] == material["id"]
        assert answer["sources"][0]["source_filename"] == "OPS-02.docx"
        assert answer["sources"][0]["section"] != "Общий текст"
        assert "подтверждённ" in answer["answer"].lower()
        unsupported = post(f"/courses/{course_id}/ask", {"question": "Какова орбита Нептуна?"})
        assert unsupported["sources"] == [] and unsupported["escalate_to_hr"]
        assert client.post(BASE + f"/courses/{course_id}/complete", json={"answer_index": 0}, headers=headers["employee"]).status_code == 409
        assert post(f"/courses/{course_id}/progress", {"progress": 70})["progress"] == 70
        assert get(f"/courses/{course_id}")["progress"] == 70
        assert client.post(BASE + f"/courses/{course_id}/complete", json={"answer_index": 1}, headers=headers["employee"]).status_code == 422
        assert post(f"/courses/{course_id}/complete", {"answer_index": 0})["completed"] is True
        after = get("/courses/rewards")
        assert after["xp"] == before["xp"] + 100
        assert post(f"/courses/{course_id}/complete", {"answer_index": 0})["completed"] is True
        assert get("/courses/rewards")["xp"] == after["xp"]
        assert get(f"/courses/{course_id}")["progress"] == 100
        print(json.dumps({"course_id": course_id, "document": material["filename"],
            "source_section": answer["sources"][0]["section"], "source_id": answer["sources"][0]["document_id"],
            "xp_before": before["xp"], "xp_after": after["xp"], "badges_after": after["badges"],
            "progress_after_refresh": get(f"/courses/{course_id}")["progress"],
            "repeat_assignment_created": False, "unsupported_refused": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
