import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, KnowledgeDocument
from app.modules.retrieval import evidence, ranked
from app.schemas import AssistantOut, Question, Source
from app.security import current_user

router = APIRouter(tags=["assistant"])


def allowed_documents(db: Session, user: Employee):
    # Filter BEFORE retrieval. Restricted text never enters the answer context.
    scopes = ["all", user.role]
    return db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.access_scope.in_(scopes))).all()


def source(document, source_type="knowledge"):
    return Source(document_id=document.id, title=document.title, section=document.section, content=document.content, source_type=source_type)


@router.get("/knowledge/{document_id}", response_model=Source)
def knowledge(document_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    item = next((d for d in allowed_documents(db, user) if d.id == document_id), None)
    if item is None:
        raise HTTPException(404, "Источник не найден")
    return source(item)


@router.post("/assistant/query", response_model=AssistantOut)
def query(data: Question, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    return answer_from_documents(data.question, allowed_documents(db, user))


def answer_from_documents(question: str, documents, *, source_type="knowledge", min_score=0.8) -> AssistantOut:
    normalized = question.lower().replace("ё", "е")
    refusal = AssistantOut(answer="В демонстрационной базе нет надёжного ответа на этот вопрос. Обратитесь в HR. Я не получаю персональные данные сотрудников и не принимаю кадровые решения.", sources=[], escalate_to_hr=True)
    if re.search(r"игнориру|забудь|инструкци[ию].*систем|system prompt|ignore|зарплат|иин|паспорт|увол|закон|коллег|чуж|персональн.*данн|сколько|положен|начисл|остат|рассчит|пересчит|компенсац|больнич|аванс|срок|длит|стоим|цен[аыу]|жалақ|жеке дерек|әріптес|заң|жсн|қанша", normalized):
        return refusal
    matches = ranked(question, documents, min_score=min_score)
    if not matches:
        return refusal
    document = matches[0][1]
    return AssistantOut(answer="По демонстрационной базе: " + evidence(question, document.content) + " [1]", sources=[source(document, source_type)], escalate_to_hr=False)
