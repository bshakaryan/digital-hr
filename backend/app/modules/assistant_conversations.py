"""User-owned AI Jana history; citations are resolved afresh on every read."""
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import AssistantConversation, AssistantTurn, Course, CourseAssignment, CourseMaterial, Employee, KnowledgeDocument, KnowledgeFile
from app.modules.audit import record
from app.schemas import AssistantOut


def course_access(db: Session, user: Employee, course_id: int) -> None:
    # Reuse the Academy assignment gate, including published status.
    from app.modules.academy import assigned
    assigned(db, user.id, course_id)


def owned_conversation(db: Session, user: Employee, conversation_id: int, course_id: int | None):
    conversation = db.scalar(select(AssistantConversation).where(
        AssistantConversation.id == conversation_id, AssistantConversation.user_id == user.id))
    if conversation is None or conversation.course_id != course_id:
        raise HTTPException(404, "Диалог не найден")
    if conversation.course_id is not None:
        course_access(db, user, conversation.course_id)
    return conversation


def authorized_sources(db: Session, user: Employee, turn: AssistantTurn, course_id: int | None):
    from app.modules.assistant import source
    refs = json.loads(turn.source_refs_json)
    if not refs:
        return []
    scopes = ("all", user.role)
    sources = []
    for ref in refs:
        document = db.scalar(select(KnowledgeDocument).outerjoin(KnowledgeFile, KnowledgeFile.id == KnowledgeDocument.file_id)
            .where(KnowledgeDocument.id == ref["document_id"], KnowledgeDocument.access_scope.in_(scopes),
                or_(KnowledgeDocument.file_id.is_(None), KnowledgeFile.access_scope.in_(scopes))))
        if document is None:
            return None
        if course_id is not None:
            attached = db.scalar(select(CourseMaterial.id).where(CourseMaterial.course_id == course_id,
                CourseMaterial.file_id == document.file_id))
            if attached is None or ref["source_type"] != "course":
                return None
        elif ref["source_type"] != "knowledge":
            return None
        sources.append(source(document, ref["source_type"]))
    return sources


def safe_answer(db: Session, user: Employee, turn: AssistantTurn, course_id: int | None) -> AssistantOut:
    from app.modules.assistant import inventory_answer
    if turn.answer_kind == "inventory":
        answer = inventory_answer(db, user)
        return answer.model_copy(update={"conversation_id": turn.conversation_id,
            "turn_id": turn.id, "client_turn_id": turn.client_turn_id})
    sources = authorized_sources(db, user, turn, course_id)
    if sources is None:
        return AssistantOut(answer="Источники этого ответа больше недоступны. Задайте вопрос заново.",
            sources=[], escalate_to_hr=True, conversation_id=turn.conversation_id,
            turn_id=turn.id, client_turn_id=turn.client_turn_id)
    return AssistantOut(answer=turn.answer, sources=sources, escalate_to_hr=turn.escalate_to_hr,
        mode=turn.mode, conversation_id=turn.conversation_id, turn_id=turn.id,
        client_turn_id=turn.client_turn_id)


def reply(db: Session, user: Employee, question: str, conversation_id: int | None,
          client_turn_id: str | None, course_id: int | None, answer_factory):
    if course_id is not None:
        course_access(db, user, course_id)
    # Serializes first-message retries as well as replies in the same conversation.
    db.scalar(select(Employee).where(Employee.id == user.id).with_for_update())
    prior = db.scalar(select(AssistantTurn).where(AssistantTurn.user_id == user.id,
        AssistantTurn.client_turn_id == client_turn_id)) if client_turn_id else None
    if prior is not None:
        conversation = owned_conversation(db, user, prior.conversation_id, course_id)
        if (conversation_id is not None and conversation_id != conversation.id) or prior.question != question:
            raise HTTPException(409, "Идентификатор хода уже использован")
        return safe_answer(db, user, prior, course_id)
    conversation = owned_conversation(db, user, conversation_id, course_id) if conversation_id else None
    if conversation is None:
        conversation = AssistantConversation(user_id=user.id, course_id=course_id)
        db.add(conversation)
        db.flush()
        record(db, user.id, "assistant.conversation_created", "assistant_conversation", conversation.id)
    answer, kind = answer_factory()
    refs = [{"document_id": item.document_id, "source_type": item.source_type} for item in answer.sources]
    turn = AssistantTurn(conversation_id=conversation.id, user_id=user.id, client_turn_id=client_turn_id,
        question=question, answer=answer.answer, source_refs_json=json.dumps(refs),
        answer_kind=kind, escalate_to_hr=answer.escalate_to_hr, mode=answer.mode)
    db.add(turn)
    db.flush()
    conversation.updated_at = datetime.now(timezone.utc)
    record(db, user.id, "assistant.turn_created", "assistant_conversation", conversation.id)
    db.commit()
    # Legacy clients receive the unchanged response shape; new clients send a turn ID.
    if client_turn_id is None and conversation_id is None:
        return answer
    return answer.model_copy(update={"conversation_id": conversation.id, "turn_id": turn.id,
        "client_turn_id": client_turn_id})


def visible_conversations(db: Session, user: Employee):
    accessible_course = exists(select(CourseAssignment.id).join(Course, Course.id == CourseAssignment.course_id)
        .where(CourseAssignment.course_id == AssistantConversation.course_id,
            CourseAssignment.employee_id == user.id, Course.status == "published"))
    return select(AssistantConversation).where(AssistantConversation.user_id == user.id,
        or_(AssistantConversation.course_id.is_(None), accessible_course))


def list_conversations(db: Session, user: Employee, page: int, page_size: int):
    query = visible_conversations(db, user)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    conversations = db.scalars(query.order_by(AssistantConversation.updated_at.desc(),
        AssistantConversation.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for conversation in conversations:
        first = db.scalar(select(AssistantTurn.question).where(AssistantTurn.conversation_id == conversation.id)
            .order_by(AssistantTurn.id).limit(1))
        items.append({"id": conversation.id, "course_id": conversation.course_id,
            "title": (first or "Новый диалог")[:100], "created_at": conversation.created_at,
            "updated_at": conversation.updated_at})
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def conversation_detail(db: Session, user: Employee, conversation_id: int, page: int, page_size: int):
    conversation = db.scalar(select(AssistantConversation).where(
        AssistantConversation.id == conversation_id, AssistantConversation.user_id == user.id))
    if conversation is None:
        raise HTTPException(404, "Диалог не найден")
    if conversation.course_id is not None:
        course_access(db, user, conversation.course_id)
    query = select(AssistantTurn).where(AssistantTurn.conversation_id == conversation.id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    turns = db.scalars(query.order_by(AssistantTurn.id).offset((page - 1) * page_size).limit(page_size)).all()
    messages = []
    for turn in turns:
        answer = safe_answer(db, user, turn, conversation.course_id)
        messages.append({"id": turn.id, "role": "user", "text": turn.question,
            "client_turn_id": turn.client_turn_id, "created_at": turn.created_at})
        messages.append({"id": turn.id, "role": "assistant", "text": answer.answer,
            "sources": answer.sources, "escalate_to_hr": answer.escalate_to_hr,
            "mode": answer.mode, "client_turn_id": turn.client_turn_id, "created_at": turn.created_at})
    return {"id": conversation.id, "course_id": conversation.course_id,
        "created_at": conversation.created_at, "updated_at": conversation.updated_at,
        "messages": messages, "total_turns": total, "page": page, "page_size": page_size}
