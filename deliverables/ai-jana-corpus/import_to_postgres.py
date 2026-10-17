"""One-off, additive import of this five-DOCX demo corpus into existing KB rows.

Run inside the existing backend image with this directory mounted at /corpus:
  docker compose run --rm --no-deps -v PATH_TO_DIR:/corpus:ro backend python /corpus/import_to_postgres.py
Add --apply only after reviewing the dry-run. Existing rows are never updated.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0, "/app")
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from app.database import get_engine  # noqa: E402
from app.models import KnowledgeDocument  # noqa: E402

ROOT = Path(__file__).resolve().parent
IDS = ("HR-01", "HR-02", "LMS-01", "LOG-01", "LOG-02")
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
HEADING = re.compile(r"^(HR-01|HR-02|LMS-01|LOG-01|LOG-02) (?:§)(\d+\.\d+)\s+(.+)$")


def paragraphs(path):
    with ZipFile(path) as package:
        root = ET.fromstring(package.read("word/document.xml"))
    for paragraph in root.findall("./w:body/w:p", NS):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", NS)).strip()
        style = paragraph.find("./w:pPr/w:pStyle", NS)
        style_id = style.get("{%s}val" % NS["w"]) if style is not None else ""
        if text:
            yield style_id, text


def extract(path, index):
    rows = list(paragraphs(path))
    doc_id = IDS[index]
    assert rows[0][1] == doc_id, path
    assert any("DEMO / SYNTHETIC" in text for _, text in rows), path
    metadata = {text.split(": ", 1)[0]: text.split(": ", 1)[1]
                for _, text in rows if ": " in text and text.split(": ", 1)[0] in
                {"Document ID", "Version / created", "Category", "Source classification", "Intended audience", "Access scope"}}
    assert metadata["Document ID"] == doc_id
    assert metadata["Access scope"] in {"all", "hr_admin", "manager", "employee"}
    title = rows[1][1]
    output = []
    current = None
    for style, text in rows:
        match = HEADING.match(text)
        if match and style.startswith("Heading"):
            if current:
                output.append(current)
            assert match.group(1) == doc_id
            current = {"section": text, "content": []}
        elif style.startswith("Heading") and "Источники и примечания" in text:
            if current:
                output.append(current)
            current = None
        elif current:
            current["content"].append(text)
    if current:
        output.append(current)
    assert output, path
    result = []
    for number, section in enumerate(output, 1):
        assert section["content"]
        row_id = 1000 + (index + 1) * 100 + number
        content = "DEMO / SYNTHETIC. " + "\n\n".join(section["content"])
        result.append(SimpleNamespace(id=row_id, title=f"{doc_id} — {title}",
                                      section=section["section"], content=content,
                                      keywords=f"{doc_id} {section['section']}", access_scope=metadata["Access scope"]))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Insert missing rows; never update existing rows")
    args = parser.parse_args()
    rows = [row for index, doc_id in enumerate(IDS) for row in extract(ROOT / f"{doc_id}.docx", index)]
    added = skipped = 0
    with Session(get_engine()) as db:
        for row in rows:
            existing = db.get(KnowledgeDocument, row.id)
            if existing is not None:
                if any(getattr(existing, field) != getattr(row, field) for field in
                       ("title", "section", "content", "keywords", "access_scope")):
                    raise SystemExit(f"Conflict at KB id {row.id}; existing row preserved")
                skipped += 1
                continue
            duplicate = db.scalar(select(KnowledgeDocument.id).where(
                KnowledgeDocument.title == row.title, KnowledgeDocument.section == row.section))
            if duplicate is not None:
                raise SystemExit(f"Duplicate section {row.section} at KB id {duplicate}; existing row preserved")
            if args.apply:
                db.add(KnowledgeDocument(**vars(row)))
            added += 1
        if args.apply:
            db.commit()
    print(f"{'Applied' if args.apply else 'Dry run'}: {added} new sections, {skipped} identical existing sections; original rows retained")


if __name__ == "__main__":
    main()
