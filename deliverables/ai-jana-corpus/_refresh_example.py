"""One-time correction of our freshly imported LOG-01 synthetic example ID."""
from import_to_postgres import extract, ROOT
from sqlalchemy.orm import Session
from app.database import get_engine
from app.models import KnowledgeDocument

new_row = extract(ROOT / "LOG-01.docx", 3)[5]
assert new_row.id == 1406
old_content = new_row.content.replace("WH-DEMO-001", "JP-DEMO-001")
assert old_content != new_row.content
with Session(get_engine()) as db:
    row = db.get(KnowledgeDocument, 1406)
    assert row is not None
    assert row.title == new_row.title and row.section == new_row.section
    assert row.access_scope == new_row.access_scope and row.keywords == new_row.keywords
    assert row.content == old_content, "Unexpected user edit: preserve row"
    row.content = new_row.content
    db.commit()
print("Corrected LOG-01 §4.1 only; original and other imported rows preserved")
