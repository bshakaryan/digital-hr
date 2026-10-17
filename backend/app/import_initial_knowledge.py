"""Repeatable initial import through the same ingest_file service as HR uploads."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import Employee
from app.modules.knowledge_ingestion import UploadDetails, chunk_count, ingest_file

MANIFEST = Path(__file__).with_name("corpus_manifest.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=Path("/corpus"))
    parser.add_argument("--actor-email", default="hr@example.com", help="Existing HR administrator for import audit")
    args = parser.parse_args()
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = {entry["filename"] for entry in entries}
    actual = {path.name for path in args.directory.iterdir() if path.suffix.lower() in {".pdf", ".docx"}}
    if expected != actual:
        raise SystemExit(f"Corpus mismatch: missing={sorted(expected-actual)}, unexpected={sorted(actual-expected)}")
    with Session(get_engine()) as db:
        actor = db.scalar(select(Employee).where(Employee.email == args.actor_email.lower()))
        if actor is None or actor.role != "hr_admin":
            raise SystemExit("Import actor must be an existing HR administrator")
        actor_id = actor.id
    results = []
    for entry in entries:
        name = entry["filename"]
        try:
            with Session(get_engine()) as db:
                item, created = ingest_file(db, data=(args.directory / name).read_bytes(), filename=name,
                    details=UploadDetails(**{key: value for key, value in entry.items() if key != "filename"}),
                    actor_id=actor_id)
                results.append({"filename": name, "status": "imported" if created else "duplicate",
                                "file_id": item.id, "sha256": item.sha256, "chunks": chunk_count(db, item.id)})
        except Exception as exc:
            message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            results.append({"filename": name, "status": "failed", "error": message})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if any(row["status"] == "failed" for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
