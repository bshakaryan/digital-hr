import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import get_settings
from app.models import Employee, KnowledgeDocument
from app.modules.assistant_llm import generate_answer
from app.modules.retrieval import ACTION_EQUIVALENTS, concepts, evidence, ranked, supports, terms
from app.schemas import AssistantOut, Question, Source
from app.security import current_user

router = APIRouter(tags=["assistant"])


def allowed_documents(db: Session, user: Employee):
    # Filter BEFORE retrieval. Restricted text never enters the answer context.
    scopes = ["all", user.role]
    documents = db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.access_scope.in_(scopes))).all()
    return without_frontmatter(documents)


def without_frontmatter(documents):
    structured = {item.file_id for item in documents if item.file_id is not None and item.section != "Общий текст"}
    return [item for item in documents if not (item.file_id in structured and item.section == "Общий текст")]


def source(document, source_type="knowledge"):
    file = getattr(document, "file", None)
    return Source(document_id=document.id, title=document.title, section=document.section,
                  content=document.content, source_type=source_type,
                  file_id=file.id if file else None,
                  source_filename=file.filename if file else None,
                  page_number=getattr(document, "page_number", None),
                  document_code=file.document_code if file else None,
                  version=file.version if file else None,
                  language=file.language if file else None,
                  classification=file.classification if file else None,
                  source_note=file.source_note if file else None)


@router.get("/knowledge/{document_id}", response_model=Source, response_model_exclude_none=True)
def knowledge(document_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(KnowledgeDocument).where(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.access_scope.in_(["all", user.role]),
    ))
    if item is None:
        raise HTTPException(404, "Источник не найден")
    return source(item)


@router.post("/assistant/query", response_model=AssistantOut, response_model_exclude_none=True)
def query(data: Question, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    return answer_from_documents(data.question, allowed_documents(db, user))


def answer_from_documents(question: str, documents, *, source_type="knowledge", min_score=0.8) -> AssistantOut:
    normalized = question.lower().replace("ё", "е")
    refusal = AssistantOut(answer="В демонстрационной базе нет надёжного ответа на этот вопрос. Обратитесь в HR. Я не получаю персональные данные сотрудников и не принимаю кадровые решения.", sources=[], escalate_to_hr=True)
    if re.search(r"игнориру|забудь|инструкци[ию].*систем|system prompt|ignore|зарплат|иин|паспорт|увол|закон|коллег|чуж|персональн.*данн|сколько|\bположен(?:о|а|ы)?\b|начисл|остат|рассчит|пересчит|компенсац|больнич|аванс|срок|длит|стоим|цен[аыу]|жалақ|жеке дерек|әріптес|заң|жсн|қанша", normalized):
        return refusal
    matches = ranked(question, documents, min_score=min_score)
    if not matches:
        return refusal
    action_question = ACTION_EQUIVALENTS in concepts(question)
    for _, document in matches[:16]:
        if not supports(question, " ".join((document.title, document.section,
                                            document.keywords or "", document.content))):
            continue
        passage = evidence(question, document.content)
        passage_terms = terms(passage)
        if not passage_terms or not (terms(question) & passage_terms):
            continue
        if action_question and (not supports(question, document.title + " " + passage)
                                or not (ACTION_EQUIVALENTS & passage_terms)):
            continue
        file = getattr(document, "file", None)
        if file and file.classification == "external_legal_snapshot":
            prefix = f"В предоставленной копии Трудового кодекса ({file.version}; актуальность не подтверждена): "
        elif file and file.classification == "synthetic_demo":
            prefix = "По демонстрационному материалу: "
        else:
            prefix = "По демонстрационной базе: "
        wording = generate_answer(question, passage, get_settings())
        if wording == "NO_EVIDENCE":
            return refusal
        return AssistantOut(answer=prefix + (wording or passage) + " [1]",
                            sources=[source(document, source_type)], escalate_to_hr=False)
    return refusal
