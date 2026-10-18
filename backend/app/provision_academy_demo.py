"""Explicit, repeatable Academy demo provisioning from imported synthetic files.

Run after ``app.import_initial_knowledge``. Existing courses and assignments are
never overwritten. The default demo reference date is 2026-10-17.
"""
import json
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.models import Course, CourseAssignment, CourseMaterial, KnowledgeDocument, KnowledgeFile, Employee
from app.modules.academy import attach_material, assign_course, complete, create_course_record, edit_course, progress, publish_course, set_quiz
from app.modules.academy_analytics import reference_date
from app.schemas import AttachMaterial, Completion, CourseAssign, CourseDraft, CourseQuiz, Progress


@dataclass(frozen=True)
class DemoCourse:
    code: str
    category: str
    title: str
    description: str
    objectives: str
    minutes: int
    files: tuple[str, ...]
    section: str
    evidence: str
    question: str
    options: tuple[str, str, str]
    correct: int = 0


COURSES = (
    DemoCourse("DEMO-ONB-01", "onboarding", "Первый день в JanaМен", "Ориентация в демонстрационном цифровом HR-пространстве.", "Находить профиль, заявки, уведомления, обучение и HR-помощь.", 12, ("HR-02",), "01. Единое пространство", "объединяет профиль, заявки, уведомления, обучение и HR-помощь", "Какие разделы объединяет JanaМен в учебном маршруте?", ("Профиль, заявки, уведомления, обучение и HR-помощь", "Только склад и перевозки", "Только личные сообщения")),
    DemoCourse("DEMO-ONB-02", "onboarding", "Заявка на отпуск в прототипе", "Демонстрационный маршрут подачи и согласования заявки; не кадровая политика Jana Post.", "Различать промежуточное решение руководителя и финальное решение HR.", 15, ("HR-01",), "03. Руководитель", "промежуточный этап, а не окончательное разрешение", "Что означает одобрение заявки руководителем?", ("Промежуточный этап перед решением HR", "Окончательное разрешение", "Автоматическое списание без решения HR")),
    DemoCourse("DEMO-ONB-03", "onboarding", "Как учиться в Jana Academy", "Назначения, материалы и проверка знаний в демонстрационной Academy.", "Объяснять, почему чтение материала ещё не завершает курс.", 10, ("LMS-01",), "03. Материалы", "Изучение материала само по себе не означает завершения", "Завершает ли одно лишь изучение материала курс?", ("Нет, требуется предусмотренная проверка знаний", "Да, сразу после открытия документа", "Да, после просмотра описания")),
    DemoCourse("DEMO-LOG-01", "logistics", "Приёмка отправлений: сверка данных", "Общие принципы складской приёмки на синтетических примерах.", "Сверять идентификатор, количество мест и видимое состояние упаковки с записью.", 18, ("LOG-01",), "02. Приёмка", "Сопоставляют идентификатор, количество мест", "Что сопоставляют при учебной приёмке?", ("Идентификатор, количество мест и состояние упаковки", "Только цвет коробки", "Только плановую дату доставки")),
    DemoCourse("DEMO-LOG-02", "logistics", "Жизненный цикл посылки", "Учебные события от создания записи до физического приёма и передачи.", "Отличать электронную запись от подтверждённого физического приёма.", 20, ("LOG-02",), "02. Создание", "Создание записи не означает физического приёма", "Что подтверждает создание электронной записи?", ("Наличие записи, но не физический приём", "Физическое вручение получателю", "Завершение всех этапов")),
    DemoCourse("DEMO-LOG-03", "logistics", "Статусы и подтверждённые события", "Качество данных отслеживания в учебной модели.", "Отличать подтверждённое событие от предположения о статусе.", 16, ("OPS-02", "LOG-02"), "01. Зачем нужны события", "Статус отправления — это краткое отражение подтверждённого события", "На чём должен основываться статус отправления?", ("На подтверждённом событии", "На намерении сотрудника", "На предположении клиента")),
    DemoCourse("DEMO-LOG-04", "logistics", "Передачи в трансграничной цепочке", "Общие принципы прослеживаемости при передаче между операторами.", "Отличать задержку обновления статуса от доказанной физической задержки груза.", 22, ("INT-01",), "03. Передачи между операторами", "Задержка обновления статуса не всегда означает физическую задержку груза", "Всегда ли задержка статуса доказывает задержку груза?", ("Нет, нужно проверить подтверждённые источники", "Да, это всегда одно и то же", "Да, если статус не менялся час")),
    DemoCourse("DEMO-SAFE-01", "warehouse_safety", "Рабочая зона склада: основы безопасности", "Общие образовательные принципы оценки складских рисков.", "Замечать перекрытые проходы и другие видимые риски.", 15, ("OPS-01",), "01. Рабочая среда и риски", "проходы должны оставаться свободными", "Каким должно быть состояние проходов в рабочей зоне?", ("Проходы должны оставаться свободными", "Проходы можно занимать временным грузом", "Состояние проходов не влияет на риск")),
    DemoCourse("DEMO-SAFE-02", "warehouse_safety", "Перемещение грузов без догадок", "Учебный разбор массы, габаритов и устойчивости груза.", "Учитывать массу, габариты и центр тяжести перед ручным перемещением.", 17, ("OPS-01", "LOG-01"), "02. Подъём и перемещение", "массу, габариты, центр тяжести", "Что учитывают перед ручным перемещением груза?", ("Массу, габариты и центр тяжести", "Только внешний размер коробки", "Только цвет маркировки")),
    DemoCourse("DEMO-SAFE-03", "warehouse_safety", "Исключения и проблемные отправления", "Наблюдаемые признаки отклонения и границы полномочий.", "Фиксировать видимые признаки и не выдумывать причину повреждения.", 19, ("OPS-03",), "01. Как распознать исключение", "повреждённая упаковка", "Какой пример требует дополнительной проверки?", ("Повреждённая упаковка", "Обычная читаемая метка", "Подтверждённый плановый приём")),
    DemoCourse("DEMO-CS-01", "customer_service", "Структура клиентского обращения", "Нейтральная фиксация проблемы и ожиданий клиента.", "Разделять наблюдение клиента и обещание решения.", 14, ("CS-01",), "01. Структура обращения", "не обещает решение до проверки фактов", "Когда допустимо обещать конкретное решение обращения?", ("После проверки фактов и оснований", "До проверки, чтобы успокоить клиента", "Сразу после получения трек-номера")),
    DemoCourse("DEMO-CS-02", "customer_service", "Конфиденциальность в ответе клиенту", "Учебный принцип проверки полномочий перед раскрытием данных.", "Не раскрывать адрес или телефон другого получателя по одному трек-номеру.", 16, ("CS-01",), "02. Проверка личности и данных", "Нельзя сообщать адрес, телефон", "Можно ли раскрыть адрес другого получателя только по трек-номеру?", ("Нет, сначала нужна предусмотренная проверка полномочий", "Да, трек-номера достаточно", "Да, если спрашивает третье лицо")),
)

# State and deadline offsets are relative to ACADEMY_DEMO_AS_OF, not wall time.
# Existing assignments are never advanced or given a new deadline on rerun.
LEARNING = {
    "employee@example.com": (("DEMO-ONB-01", "completed", -3), ("DEMO-ONB-02", "in_progress", 5), ("DEMO-LOG-01", "not_started", -2), ("DEMO-LOG-03", "completed", 7), ("DEMO-SAFE-01", "in_progress", -1), ("DEMO-CS-01", "not_started", 9)),
    "manager@example.com": (("DEMO-ONB-03", "completed", 3), ("DEMO-LOG-02", "in_progress", -4), ("DEMO-SAFE-02", "not_started", 8), ("DEMO-CS-02", "not_started", -2)),
    "outsider@example.com": (("DEMO-ONB-01", "not_started", -5), ("DEMO-LOG-04", "in_progress", 6), ("DEMO-SAFE-03", "not_started", 10), ("DEMO-CS-01", "not_started", -1)),
    "hr@example.com": (("DEMO-ONB-03", "completed", 4), ("DEMO-CS-02", "not_started", 10)),
}

# New assignments only. The employee's existing demo courses are legacy and
# cannot be reclassified or assigned a second time under another track.
ONBOARDING = {
    "employee@example.com": (("DEMO-ONB-03", "completed", 7), ("DEMO-LOG-02", "in_progress", 14),
                             ("DEMO-SAFE-02", "not_started", 21), ("DEMO-CS-02", "not_started", 28)),
}
SELF_ENROLLABLE = frozenset({"DEMO-LOG-04", "DEMO-SAFE-03", "DEMO-CS-01"})
DEMO_EMPLOYEES = {"employee@example.com": "demo-1", "manager@example.com": "demo-2",
                  "outsider@example.com": "demo-4", "hr@example.com": "demo-3"}


def provision() -> dict:
    if get_settings().zup_mode != "mock":
        raise RuntimeError("Academy demo provisioning is allowed only with ZUP_MODE=mock")
    as_of = reference_date()
    result = {"as_of": as_of.isoformat(), "created_courses": 0, "new_assignments": 0,
              "new_onboarding_assignments": 0, "self_enrollable_enabled": 0,
              "completed": 0, "in_progress": 0, "existing_assignments": 0}
    with Session(get_engine()) as db:
        hr = db.scalar(select(Employee).where(Employee.email == "hr@example.com", Employee.zup_id == "demo-3"))
        if hr is None or hr.role != "hr_admin":
            raise RuntimeError("Synthetic demo HR account is unavailable")
        files = {item.document_code: item for item in db.scalars(select(KnowledgeFile).where(KnowledgeFile.classification == "synthetic_demo")).all()}
        for spec in COURSES:
            for code in spec.files:
                if code not in files or files[code].access_scope not in ("all", "employee", "manager"):
                    raise RuntimeError(f"Missing authorized synthetic source: {code}")
            source = files[spec.files[0]]
            chunks = db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.file_id == source.id,
                KnowledgeDocument.section == spec.section)).all()
            evidence = " ".join(spec.evidence.split()).casefold()
            if not any(evidence in " ".join(chunk.content.split()).casefold() for chunk in chunks):
                raise RuntimeError(f"Quiz evidence missing: {spec.code} / {spec.section}")
        by_code = {}
        for spec in COURSES:
            item = db.scalar(select(Course).where(Course.demo_code == spec.code))
            if item is None:
                item = create_course_record(CourseDraft(title=f"Демо · {spec.title}",
                    description=f"DEMO / SYNTHETIC. {spec.description} Не является официальной инструкцией Jana Post.",
                    objectives=spec.objectives, duration_minutes=spec.minutes, category=spec.category), hr, db, spec.code)
                result["created_courses"] += 1
            by_code[spec.code] = item
            if item.status == "draft":
                for code in spec.files:
                    attach_material(item.id, AttachMaterial(file_id=files[code].id), hr, db)
                if not item.question:
                    set_quiz(item.id, CourseQuiz(question=spec.question, options=list(spec.options), correct_index=spec.correct), hr, db)
                publish_course(item.id, hr, db)
        for code in sorted(by_code):
            course = by_code[code]
            classifications = db.scalars(select(KnowledgeFile.classification).join(CourseMaterial,
                CourseMaterial.file_id == KnowledgeFile.id).where(CourseMaterial.course_id == course.id)).all()
            if (course.status != "published" or not course.description.startswith("DEMO / SYNTHETIC.")
                    or not classifications or any(value != "synthetic_demo" for value in classifications)):
                raise RuntimeError(f"Course is no longer a published synthetic demo: {code}")
        for code in sorted(SELF_ENROLLABLE):
            course = by_code[code]
            if not course.self_enrollable:
                edit_course(course.id, CourseDraft(title=course.title, description=course.description,
                    objectives=course.objectives, duration_minutes=course.duration_minutes,
                    category=course.category, self_enrollable=True), hr, db)
                result["self_enrollable_enabled"] += 1
        for plans, track in ((LEARNING, "legacy"), (ONBOARDING, "onboarding")):
            for email, plan in plans.items():
                employee = db.scalar(select(Employee).where(Employee.email == email,
                    Employee.zup_id == DEMO_EMPLOYEES[email]))
                if employee is None:
                    raise RuntimeError(f"Synthetic demo employee unavailable: {email}")
                for code, state, offset in plan:
                    course = by_code[code]
                    existing = db.scalar(select(CourseAssignment).where(CourseAssignment.employee_id == employee.id,
                        CourseAssignment.course_id == course.id))
                    if existing is not None:
                        result["existing_assignments"] += 1
                        continue
                    assigned = assign_course(course.id, CourseAssign(employee_id=employee.id,
                        deadline=as_of + timedelta(days=offset), learning_track=track), hr, db)
                    if not assigned["assigned"]:
                        raise RuntimeError(f"Unexpected duplicate assignment: {email} / {code}")
                    result["new_assignments"] += 1
                    if track == "onboarding":
                        result["new_onboarding_assignments"] += 1
                    if state in ("in_progress", "completed"):
                        progress(course.id, Progress(progress=70), employee, db)
                        result["in_progress"] += 1
                    if state == "completed":
                        complete(course.id, Completion(answer_index=course.correct_index), employee, db)
                        result["completed"] += 1
    return result


if __name__ == "__main__":
    print(json.dumps(provision(), ensure_ascii=False))
