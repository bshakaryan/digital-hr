"""HR upload and authorized access to original knowledge-base files."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, KnowledgeFile
from app.modules.knowledge_ingestion import MAX_FILE_BYTES, UploadDetails, chunk_count, ingest_file
from app.schemas import KnowledgeFileOut
from app.security import current_user, require_hr

router = APIRouter(prefix="/knowledge-files", tags=["knowledge"])


def _present(db: Session, item: KnowledgeFile, *, duplicate=False) -> KnowledgeFileOut:
    return KnowledgeFileOut(
        id=item.id, filename=item.filename, title=item.title, document_code=item.document_code,
        version=item.version, language=item.language, classification=item.classification,
        source_note=item.source_note, access_scope=item.access_scope, sha256=item.sha256,
        size_bytes=item.size_bytes, chunk_count=chunk_count(db, item.id), duplicate=duplicate,
    )


@router.post("", response_model=KnowledgeFileOut)
async def upload_knowledge_file(
    file: UploadFile = File(...), title: str = Form(...), version: str = Form(...),
    language: str = Form("ru"), classification: str = Form(...),
    access_scope: str = Form("all"), source_note: str = Form(""),
    document_code: str | None = Form(None),
    user: Employee = Depends(require_hr), db: Session = Depends(get_db),
):
    data = await file.read(MAX_FILE_BYTES + 1)
    try:
        item, created = ingest_file(db, data=data, filename=file.filename or "", actor_id=user.id,
            details=UploadDetails(title=title, version=version, language=language,
                                  classification=classification, access_scope=access_scope,
                                  source_note=source_note, document_code=document_code))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _present(db, item, duplicate=not created)


@router.get("", response_model=list[KnowledgeFileOut])
def list_knowledge_files(user: Employee = Depends(require_hr), db: Session = Depends(get_db)):
    return [_present(db, item) for item in db.scalars(select(KnowledgeFile).order_by(KnowledgeFile.id)).all()]


def readable_file(db: Session, file_id: int, user: Employee) -> KnowledgeFile:
    item = db.get(KnowledgeFile, file_id)
    if item is None or item.access_scope not in readable_scopes(user):
        raise HTTPException(404, "Источник не найден")
    return item


def readable_scopes(user: Employee) -> tuple[str, str]:
    return ("all", user.role)


def authorized_file_metadata(db: Session, user: Employee):
    # Select only display metadata; original bytes and filenames stay out of this path.
    return db.execute(select(KnowledgeFile.title, KnowledgeFile.media_type).where(
        KnowledgeFile.access_scope.in_(readable_scopes(user)),
    ).order_by(KnowledgeFile.id)).all()


@router.get("/{file_id}", response_model=KnowledgeFileOut)
def knowledge_file(file_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    return _present(db, readable_file(db, file_id, user))


@router.get("/{file_id}/download")
def download_knowledge_file(file_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    item = readable_file(db, file_id, user)
    encoded = quote(item.filename, safe="")
    return Response(content=item.original_bytes, media_type=item.media_type,
        headers={"Content-Disposition": f"attachment; filename=source; filename*=UTF-8''{encoded}",
                 "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
