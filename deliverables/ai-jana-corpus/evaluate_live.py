"""Evaluate the running AI Jana API against the independent CSV; no state changes beyond login audit."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
BASE = "http://backend:8000/api"
EMAIL = {"employee": "employee@example.com", "manager": "manager@example.com", "hr_admin": "hr@example.com"}


def main():
    password = os.environ["DEMO_PASSWORD"]
    with httpx.Client(timeout=20) as client:
        headers = {}
        for role, email in EMAIL.items():
            response = client.post(BASE + "/auth/login", json={"email": email, "password": password})
            response.raise_for_status()
            headers[role] = {"Authorization": "Bearer " + response.json()["access_token"]}
        # Source endpoint checks also establish that old seed records remain present.
        access_checks = {
            "employee_old_public": client.get(BASE + "/knowledge/1", headers=headers["employee"]).status_code,
            "employee_old_restricted": client.get(BASE + "/knowledge/5", headers=headers["employee"]).status_code,
            "hr_old_restricted": client.get(BASE + "/knowledge/5", headers=headers["hr_admin"]).status_code,
            "employee_new_restricted": client.get(BASE + "/knowledge/1501", headers=headers["employee"]).status_code,
            "manager_new_restricted": client.get(BASE + "/knowledge/1501", headers=headers["manager"]).status_code,
            "hr_new_restricted": client.get(BASE + "/knowledge/1501", headers=headers["hr_admin"]).status_code,
        }
        with (ROOT / "rag_evaluation.csv").open(encoding="utf-8", newline="") as handle:
            cases = list(csv.DictReader(handle))
        results = []
        for case in cases:
            response = client.post(BASE + "/assistant/query", headers=headers[case["role"]],
                                   json={"question": case["question"]})
            response.raise_for_status()
            payload = response.json()
            sources = payload["sources"]
            cited = [f"{s['section'].split(' §')[0]} §{s['section'].split(' §')[1].split(' ')[0]}"
                     for s in sources if " §" in s["section"]]
            expected = case["expected_support"].split("|") if case["expected_support"] else []
            resolved = True
            for source in sources:
                check = client.get(BASE + f"/knowledge/{source['document_id']}", headers=headers[case["role"]])
                resolved &= check.status_code == 200 and check.json().get("section") == source["section"]
            results.append({
                "id": case["id"], "type": case["type"], "role": case["role"],
                "expected_outcome": case["expected_outcome"], "expected_support": expected,
                "status": response.status_code, "answer": payload["answer"],
                "cited_sections": cited, "source_ids": [s["document_id"] for s in sources],
                "refused": not sources and payload["escalate_to_hr"],
                "citation_resolves": resolved if sources else None,
                "hit_any": bool(set(cited) & set(expected)) if expected else None,
                "hit_all": set(expected) <= set(cited) if expected else None,
            })
    supported = [r for r in results if r["expected_outcome"] == "supported"]
    no_answer = [r for r in results if r["expected_outcome"] == "no_supported_answer"]
    restricted = [r for r in results if r["expected_outcome"] == "no_authorized_answer"]
    answered = [r for r in results if r["source_ids"]]
    summary = {
        "cases": len(results), "supported": len(supported), "unanswerable": len(no_answer),
        "unauthorized": len(restricted), "hit_any": sum(r["hit_any"] for r in supported),
        "hit_all": sum(r["hit_all"] for r in supported),
        "unanswerable_refused": sum(r["refused"] for r in no_answer),
        "unauthorized_refused": sum(r["refused"] for r in restricted),
        "answered": len(answered), "citation_resolves": sum(r["citation_resolves"] for r in answered),
        "access_checks": access_checks,
    }
    (ROOT / "rag_live_results.json").write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for r in results:
        print(f"{r['id']}: {r['cited_sections'] or 'REFUSED'}; expected {r['expected_support'] or r['expected_outcome']}")


if __name__ == "__main__":
    main()
