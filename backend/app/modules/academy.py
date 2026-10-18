import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Course, CourseAssignment, CourseMaterial, Employee, KnowledgeDocument, KnowledgeFile
from app.modules.academy_analytics import assignment_status, employee_profile, overview, reference_date, rows_for
from app.modules.assistant import answer_from_documents, without_frontmatter
from app.modules.assistant_conversations import reply
from app.modules.audit import record
from app.modules.knowledge_files import _present
from app.modules.notifications import notify
from app.schemas import AssistantOut, AttachMaterial, Completion, CourseAssign, CourseCatalogItem, CourseDraft, CourseOut, CourseQuiz, CourseTrackChange, EmployeeLearningOut, KnowledgeFileOut, LearningAnalyticsOut, Progress, PublicCourseItem, Question, RewardsOut
from app.security import current_user, require_hr

router = APIRouter(prefix="/courses", tags=["academy"])


def assigned(db: Session, employee_id: int, course_id: int):
    pair = db.execute(select(Course, CourseAssignment).join(CourseAssignment, CourseAssignment.course_id == Course.id).where(Course.id == course_id, Course.status == "published", CourseAssignment.employee_id == employee_id)).first()
    if pair is None:
        raise HTTPException(404, "Курс не назначен")
    return pair


def present(course: Course, assignment: CourseAssignment):
    learning_status, overdue = assignment_status(assignment, reference_date())
    return CourseOut(id=course.id, title=course.title, description=course.description, content=course.content, duration_minutes=course.duration_minutes, progress=assignment.progress, completed=assignment.completed, question=course.question, options=json.loads(course.options_json), objectives=course.objectives, status=course.status, category=course.category, is_demo=course.demo_code is not None, self_enrollable=course.self_enrollable, learning_track=assignment.learning_track, deadline=assignment.deadline, learning_status=learning_status, overdue=overdue)


def admin_course(course: Course):
    return CourseCatalogItem(id=course.id, title=course.title, description=course.description,
        objectives=course.objectives, duration_minutes=course.duration_minutes, status=course.status,
        question=course.question, options=json.loads(course.options_json), correct_index=course.correct_index,
        category=course.category, is_demo=course.demo_code is not None, self_enrollable=course.self_enrollable)


def editable_course(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "Курс не найден")
    return course


@router.get("", response_model=list[CourseOut])
def courses(user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    pairs = db.execute(select(Course, CourseAssignment).join(CourseAssignment, CourseAssignment.course_id == Course.id).where(CourseAssignment.employee_id == user.id, Course.status == "published").order_by(Course.id)).all()
    return [present(c, a) for c, a in pairs]


@router.get("/rewards", response_model=RewardsOut)
def rewards(user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    # Completed assignments are the single source of truth: one unique assignment
    # per employee/course means retries cannot award XP again.
    completed = db.scalar(select(func.count()).select_from(CourseAssignment).where(
        CourseAssignment.employee_id == user.id, CourseAssignment.completed.is_(True))) or 0
    xp = completed * 100
    return RewardsOut(xp=xp, level=1 + xp // 100, next_level_xp=(1 + xp // 100) * 100,
                      badges=(["Первый курс"] if completed >= 1 else []) + (["Три курса"] if completed >= 3 else []))


@router.get("/catalog", response_model=list[CourseCatalogItem])
def course_catalog(user: Employee = Depends(require_hr), db: Session = Depends(get_db)):
    return [admin_course(item) for item in db.scalars(select(Course).order_by(Course.id)).all()]


@router.get("/discover", response_model=list[PublicCourseItem])
def discover_courses(user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    courses = db.scalars(select(Course).join(CourseMaterial, CourseMaterial.course_id == Course.id)
        .join(KnowledgeFile, KnowledgeFile.id == CourseMaterial.file_id)
        .where(Course.status == "published", KnowledgeFile.access_scope.in_(("all", user.role)))
        .distinct().order_by(Course.id)).all()
    return [PublicCourseItem(id=item.id, title=item.title, description=item.description,
        objectives=item.objectives, duration_minutes=item.duration_minutes,
        category=item.category, is_demo=item.demo_code is not None,
        self_enrollable=item.self_enrollable) for item in courses]


@router.get("/analytics", response_model=LearningAnalyticsOut)
def learning_analytics(user: Employee = Depends(require_hr), db: Session = Depends(get_db)):
    return overview(db, reference_date())


@router.get("/analytics/employees", response_model=list[EmployeeLearningOut])
def learning_directory(user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    if user.role == "hr_admin":
        employees = db.scalars(select(Employee).order_by(Employee.full_name)).all()
    elif user.role == "manager":
        employees = db.scalars(select(Employee).where(Employee.manager_id == user.id).order_by(Employee.full_name)).all()
    else:
        raise HTTPException(403, "Доступ только для HR и руководителя")
    rows = rows_for(db, employees, reference_date())
    return [employee_profile(employee, rows) for employee in employees]


@router.get("/analytics/employees/{employee_id}", response_model=EmployeeLearningOut)
def learning_employee(employee_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in ("hr_admin", "manager"):
        raise HTTPException(403, "Доступ только для HR и руководителя")
    employee = db.get(Employee, employee_id)
    if employee is None or (user.role == "manager" and employee.manager_id != user.id):
        raise HTTPException(404, "Сотрудник не найден")
    return employee_profile(employee, rows_for(db, [employee], reference_date()))


def create_course_record(data: CourseDraft, user: Employee, db: Session, demo_code: str | None = None) -> Course:
    item = Course(title=data.title.strip(), description=data.description.strip(), objectives=data.objectives.strip(),
        content="", duration_minutes=data.duration_minutes, question="", options_json="[]", correct_index=0,
        status="draft", category=data.category or "general", demo_code=demo_code,
        self_enrollable=data.self_enrollable if data.self_enrollable is not None else False)
    db.add(item)
    db.flush()
    record(db, user.id, "course.created", "course", item.id)
    db.commit()
    return item


@router.post("", response_model=CourseCatalogItem, status_code=201)
def create_course(data: CourseDraft, user: Employee = Depends(require_hr), db: Session = Depends(get_db)):
    item = create_course_record(data, user, db)
    return admin_course(item)


@router.patch("/{course_id}", response_model=CourseCatalogItem)
def edit_course(course_id: int, data: CourseDraft, user: Employee = Depends(require_hr), db: Session = Depends(get_db)):
    item = editable_course(db, course_id)
    values = (data.title.strip(), data.description.strip(), data.objectives.strip(), data.duration_minutes,
        data.category or item.category, item.self_enrollable if data.self_enrollable is None else data.self_enrollable)
    old = (item.title, item.description, item.objectives, item.duration_minutes, item.category, item.self_enrollable)
    if values != old:
        item.title, item.description, item.objectives, item.duration_minutes, item.category, item.self_enrollable = values
        record(db, user.id, "course.updated", "course", item.id)
        db.commit()
    return admin_course(item)


@router.put("/{course_id}/quiz", response_model=CourseCatalogItem)
def set_quiz(course_id: int, data: CourseQuiz, user: Employee = Depends(require_hr), db: Session = Depends(get_db)):
    item = editable_course(db, course_id)
    if item.status != "draft":
        raise HTTPException(409, "Тест опубликованного курса нельзя менять")
    values = (data.question.strip(), json.dumps([option.strip() for option in data.options], ensure_ascii=False), data.correct_index)
    if values != (item.question, item.options_json, item.correct_index):
        item.question, item.options_json, item.correct_index = values
        record(db, user.id, "course.quiz_updated", "course", item.id)
        db.commit()
    return admin_course(item)


@router.post("/{course_id}/publish", response_model=CourseCatalogItem)
def publish_course(course_id: int, user: Employee = Depends(require_hr), db: Session = Depends(get_db)):
    item = db.scalar(select(Course).where(Course.id == course_id).with_for_update())
    if item is None:
        raise HTTPException(404, "Курс не найден")
    if item.status == "draft":
        if not item.question.strip() or len(json.loads(item.options_json)) < 2:
            raise HTTPException(409, "Сначала создайте тест")
        readable = db.scalar(select(CourseMaterial.id).join(KnowledgeFile, CourseMaterial.file_id == KnowledgeFile.id)
            .where(CourseMaterial.course_id == course_id, KnowledgeFile.access_scope.in_(("all", "employee", "manager"))).limit(1))
        if readable is None:
            raise HTTPException(409, "Прикрепите документ, доступный ученику")
        item.status = "published"
        record(db, user.id, "course.published", "course", item.id)
        db.commit()
    return admin_course(item)


@router.post("/{course_id}/assign")
def assign_course(course_id: int, data: CourseAssign, user: Employee = Depends(require_hr), db: Session = Depends(get_db)):
    item = db.scalar(select(Course).where(Course.id == course_id).with_for_update())
    if item is None:
        raise HTTPException(404, "Курс не найден")
    if item.status != "published":
        raise HTTPException(409, "Сначала опубликуйте курс")
    employee = db.get(Employee, data.employee_id)
    if employee is None:
        raise HTTPException(404, "Сотрудник не найден")
    existing = db.scalar(select(CourseAssignment).where(CourseAssignment.course_id == course_id,
        CourseAssignment.employee_id == employee.id))
    if existing is not None:
        return {"course_id": course_id, "employee_id": employee.id, "assigned": False}
    readable = db.scalar(select(CourseMaterial.id).join(KnowledgeFile, CourseMaterial.file_id == KnowledgeFile.id)
        .where(CourseMaterial.course_id == course_id, KnowledgeFile.access_scope.in_(("all", employee.role))).limit(1))
    if readable is None:
        raise HTTPException(409, "У сотрудника нет доступа к материалам курса")
    db.add(CourseAssignment(employee_id=employee.id, course_id=course_id, progress=0, completed=False,
        deadline=data.deadline, learning_track=data.learning_track))
    notify(db, employee.id, "course_assigned", "Вам назначен курс", f"Начните с курса «{item.title}».",
        entity_type="course", entity_id=course_id, actor_id=user.id)
    record(db, user.id, "course.assigned", "employee", employee.id)
    db.commit()
    return {"course_id": course_id, "employee_id": employee.id, "assigned": True}


@router.patch("/{course_id}/assignments/{employee_id}/track")
def reclassify_assignment(course_id: int, employee_id: int, data: CourseTrackChange,
                          user: Employee = Depends(require_hr), db: Session = Depends(get_db)):
    assignment = db.scalar(select(CourseAssignment).where(CourseAssignment.course_id == course_id,
        CourseAssignment.employee_id == employee_id).with_for_update())
    if assignment is None:
        raise HTTPException(404, "Назначение не найдено")
    if assignment.learning_track == data.learning_track:
        return {"course_id": course_id, "employee_id": employee_id, "learning_track": assignment.learning_track, "changed": False}
    if assignment.learning_track != "legacy":
        raise HTTPException(409, "Трек уже установлен; изменение требует отдельного решения HR")
    assignment.learning_track = data.learning_track
    record(db, user.id, "course.assignment_reclassified", "course_assignment", assignment.id)
    db.commit()
    return {"course_id": course_id, "employee_id": employee_id, "learning_track": assignment.learning_track, "changed": True}


@router.post("/{course_id}/enroll")
def self_enroll(course_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(Course).where(Course.id == course_id).with_for_update())
    if item is None or item.status != "published":
        raise HTTPException(404, "Курс не найден")
    existing = db.scalar(select(CourseAssignment).where(CourseAssignment.course_id == course_id,
        CourseAssignment.employee_id == user.id))
    if existing is not None:
        return {"course_id": course_id, "employee_id": user.id, "assigned": False,
            "learning_track": existing.learning_track}
    if not item.self_enrollable:
        raise HTTPException(409, "Самостоятельная запись на курс закрыта")
    readable = db.scalar(select(CourseMaterial.id).join(KnowledgeFile, CourseMaterial.file_id == KnowledgeFile.id)
        .where(CourseMaterial.course_id == course_id, KnowledgeFile.access_scope.in_(("all", user.role))).limit(1))
    if readable is None:
        raise HTTPException(404, "Курс не найден")
    db.add(CourseAssignment(employee_id=user.id, course_id=course_id, progress=0, completed=False,
        learning_track="development"))
    record(db, user.id, "course.self_enrolled", "course", course_id)
    db.commit()
    return {"course_id": course_id, "employee_id": user.id, "assigned": True,
        "learning_track": "development"}


@router.get("/{course_id}", response_model=CourseOut)
def course(course_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    return present(*assigned(db, user.id, course_id))


@router.post("/{course_id}/progress", response_model=CourseOut)
def progress(course_id: int, data: Progress, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    c, a = assigned(db, user.id, course_id)
    saved_progress = min(data.progress, 99)  # 100 is reserved for verified quiz completion.
    changed = db.execute(update(CourseAssignment).where(CourseAssignment.id == a.id, CourseAssignment.progress < saved_progress).values(progress=saved_progress).execution_options(synchronize_session=False))
    if changed.rowcount:
        record(db, user.id, "course.progressed", "course", course_id)
    db.commit()
    db.refresh(a)
    return present(c, a)


@router.post("/{course_id}/complete", response_model=CourseOut)
def complete(course_id: int, data: Completion, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    c, a = assigned(db, user.id, course_id)
    if not a.completed and a.progress < 70:
        raise HTTPException(409, "Сначала отметьте изучение материала")
    if data.answer_index != c.correct_index:
        raise HTTPException(422, "Ответ неверный. Прочитайте материал и попробуйте ещё раз")
    changed = db.execute(update(CourseAssignment).where(CourseAssignment.id == a.id, CourseAssignment.completed.is_(False)).values(progress=100, completed=True).execution_options(synchronize_session=False))
    if changed.rowcount:
        notify(db, user.id, "course_completed", "Курс завершён", f"Вы прошли «{c.title}».", entity_type="course", entity_id=c.id, actor_id=user.id)
        record(db, user.id, "course.completed", "course", course_id)
    db.commit()
    db.refresh(a)
    return present(c, a)


@router.post("/{course_id}/ask", response_model=AssistantOut, response_model_exclude_none=True)
def ask_course(course_id: int, data: Question, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    assigned(db, user.id, course_id)
    def answer():
        documents = db.scalars(select(KnowledgeDocument).join(CourseMaterial, CourseMaterial.file_id == KnowledgeDocument.file_id)
            .join(KnowledgeFile, KnowledgeFile.id == KnowledgeDocument.file_id)
            .where(CourseMaterial.course_id == course_id, KnowledgeDocument.access_scope.in_(("all", user.role)),
                   KnowledgeFile.access_scope.in_(("all", user.role)))).all()
        return answer_from_documents(data.question, without_frontmatter(documents), source_type="course", min_score=0.25), "rag"
    return reply(db, user, data.question, data.conversation_id, data.client_turn_id, course_id, answer)


@router.get("/{course_id}/materials", response_model=list[KnowledgeFileOut])
def course_materials(course_id: int, user: Employee = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "hr_admin":
        assigned(db, user.id, course_id)
    elif db.get(Course, course_id) is None:
        raise HTTPException(404, "Курс не найден")
    files = db.scalars(select(KnowledgeFile).join(CourseMaterial, CourseMaterial.file_id == KnowledgeFile.id)
        .where(CourseMaterial.course_id == course_id, KnowledgeFile.access_scope.in_(("all", user.role)))
        .order_by(KnowledgeFile.id)).all()
    return [_present(db, item) for item in files]


@router.post("/{course_id}/materials", response_model=KnowledgeFileOut)
def attach_material(course_id: int, data: AttachMaterial, user: Employee = Depends(require_hr), db: Session = Depends(get_db)):
    if db.get(Course, course_id) is None:
        raise HTTPException(404, "Курс не найден")
    file = db.get(KnowledgeFile, data.file_id)
    if file is None:
        raise HTTPException(404, "Документ не найден")
    existing = db.scalar(select(CourseMaterial).where(CourseMaterial.course_id == course_id, CourseMaterial.file_id == file.id))
    if existing is None:
        db.add(CourseMaterial(course_id=course_id, file_id=file.id, attached_by=user.id))
        record(db, user.id, "course.material_attached", "course", course_id)
        db.commit()
    return _present(db, file)
