import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import get_settings
from app.models import Employee, KnowledgeDocument, KnowledgeFile
from app.modules.assistant_llm import generate_answer
from app.modules.assistant_conversations import conversation_detail, list_conversations, reply
from app.modules.knowledge_files import authorized_file_metadata
from app.modules.retrieval import ACTION_EQUIVALENTS, concepts, evidence, ranked, supports, terms
from app.schemas import AssistantOut, ConversationDetail, ConversationPage, Question, Source
from app.security import current_user

router = APIRouter(tags=["assistant"])

UNSUPPORTED = re.compile(r"игнориру|забудь|инструкци[ию].*систем|system prompt|ignore|зарплат|иин|паспорт|увол|закон|коллег|чуж|персональн.*данн|сколько|\bположен(?:о|а|ы)?\b|начисл|остат|рассчит|пересчит|компенсац|больнич|аванс|срок|длит|стоим|цен[аыу]|жалақ|жеке дерек|әріптес|заң|жсн|қанша")
INVENTORY_CONTEXT = re.compile(r"баз\w*\s+знан\w*|каталог\w*|корпус\w*|knowledge\s*base")
INVENTORY_ITEM = re.compile(r"документ\w*|файл\w*|материал\w*|источник\w*|\bpdf\b|\bdocx\b")
INVENTORY_REQUEST = re.compile(r"\b(?:какие|какой|список|перечень|перечисл\w*|покаж\w*|назов\w*|доступн\w*|загружен\w*|есть)\b")
CONTENT_REQUEST = re.compile(r"\b(?:написан\w*|сказан\w*|говорит\w*|объясн\w*|нужн\w*|треб\w*|оформ\w*|содерж\w*|курс\w*|как|почему)\b")


def inventory_intent(question: str) -> bool:
    normalized = question.casefold().replace("ё", "е")
    if not INVENTORY_REQUEST.search(normalized) or CONTENT_REQUEST.search(normalized):
        return False
    if INVENTORY_CONTEXT.search(normalized):
        return bool(INVENTORY_ITEM.search(normalized) or re.search(
            r"\bчто\b.*\b(?:есть|загружен\w*|доступн\w*)\b", normalized))
    return bool(INVENTORY_ITEM.search(normalized) and re.search(
        r"\b(?:список|перечень|перечисл\w*|покаж\w*|какие)\b", normalized))


def inventory_answer(db: Session, user: Employee) -> AssistantOut:
    files = authorized_file_metadata(db, user)
    if not files:
        answer = "В базе знаний нет доступных вам документов."
    else:
        formats = {"application/pdf": "PDF",
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX"}
        answer = "Доступные документы в базе знаний:\n" + "\n".join(
            f"• {title} ({formats[media_type]})" for title, media_type in files)
    return AssistantOut(answer=answer, sources=[], escalate_to_hr=False)


def refusal_answer() -> AssistantOut:
    return AssistantOut(answer="В демонстрационной базе нет надёжного ответа на этот вопрос. Обратитесь в HR. Я не получаю персональные данные сотрудников и не принимаю кадровые решения.", sources=[], escalate_to_hr=True)


def allowed_documents(db: Session, user: Employee):
    # Filter BEFORE retrieval. Restricted text never enters the answer context.
    scopes = ["all", user.role]
    documents = db.scalars(select(KnowledgeDocument).outerjoin(KnowledgeFile,
        KnowledgeFile.id == KnowledgeDocument.file_id).where(KnowledgeDocument.access_scope.in_(scopes),
        or_(KnowledgeDocument.file_id.is_(None), KnowledgeFile.access_scope.in_(scopes)))).all()
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
    def answer():
        if inventory_intent(data.question):
            if UNSUPPORTED.search(data.question.lower().replace("ё", "е")):
                return refusal_answer(), "rag"
            return inventory_answer(db, user), "inventory"
        return answer_from_documents(data.question, allowed_documents(db, user)), "rag"
    return reply(db, user, data.question, data.conversation_id, data.client_turn_id, None, answer)


@router.get("/assistant/conversations", response_model=ConversationPage)
def conversations(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                  user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    return list_conversations(db, user, page, page_size)


@router.get("/assistant/conversations/{conversation_id}", response_model=ConversationDetail)
def conversation(conversation_id: int, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
                 user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    return conversation_detail(db, user, conversation_id, page, page_size)


def answer_from_documents(question: str, documents, *, source_type="knowledge", min_score=0.8) -> AssistantOut:
    normalized = question.lower().replace("ё", "е")
    refusal = refusal_answer()
    if UNSUPPORTED.search(normalized):
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
