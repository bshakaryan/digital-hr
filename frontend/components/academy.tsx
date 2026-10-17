"use client";

import { useRef, useState, type FormEvent } from "react";
import { ApiClient, errorMessage, type Course, type KnowledgeFile } from "@/lib/api";
import { shortDate } from "@/lib/academy-labels";
import { ErrorBox, Icon, Loading, Modal } from "./ui";
import { useResource } from "./use-resource";
import { CourseAssistant } from "./course-assistant";
import styles from "./academy-ux.module.css";

export function CourseReader({ id, api, onClose, onChanged, notify, onRewardsChanged }: { id: number; api: ApiClient; onClose: () => void; onChanged: () => void; notify: (message: string) => void; onRewardsChanged: () => void }) {
  const resource = useResource<Course>(api, `/courses/${id}`);
  const materials = useResource<KnowledgeFile[]>(api, `/courses/${id}/materials`);
  const [section, setSection] = useState<"overview" | "materials" | "assistant" | "quiz" | "result">("overview");
  const [answer, setAnswer] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [materialRead, setMaterialRead] = useState(false);
  const busy = useRef(false);
  const course = resource.data;
  async function saveProgress() {
    if (!course || busy.current) return;
    busy.current = true; setPending(true); setError("");
    try { await api.post<Course>(`/courses/${id}/progress`, { progress: Math.max(course.progress, 70) }); setMaterialRead(true); setSection("quiz"); resource.reload(); onChanged(); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { busy.current = false; setPending(false); }
  }
  async function complete(event: FormEvent) {
    event.preventDefault();
    if (answer === null || busy.current) return;
    busy.current = true; setPending(true); setError("");
    try { await api.post<Course>(`/courses/${id}/complete`, { answer_index: answer }); setSection("result"); resource.reload(); onChanged(); onRewardsChanged(); notify(course?.completed ? "Курс уже завершён." : "Курс завершён: +100 XP!"); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { busy.current = false; setPending(false); }
  }
  const canTakeQuiz = materialRead || (course?.progress ?? 0) >= 70;
  const outline: { id: typeof section; label: string; icon: "book" | "document" | "spark" | "check" | "shield" }[] = [
    { id: "overview", label: "О курсе", icon: "book" }, { id: "materials", label: "Материалы", icon: "document" },
    { id: "assistant", label: "Спросить AI Jana", icon: "spark" }, { id: "quiz", label: "Тест", icon: "check" },
    ...(course?.completed ? [{ id: "result" as const, label: "Результат", icon: "shield" as const }] : []),
  ];
  return <Modal title="Jana Academy · Обучение" wide className={`course-learning-dialog ${styles.reader}`} onClose={() => { if (!pending) onClose(); }}>
    {resource.error ? <ErrorBox message={resource.error} retry={resource.reload} /> : resource.loading && !course ? <Loading /> : course && <>
      <header className="course-reader-heading"><span className="course-meta"><Icon name="clock" size={15} />{course.duration_minutes} мин. · Назначенный курс{course.deadline ? ` · Срок: ${shortDate(course.deadline)}` : ""}</span><h2>{course.title}</h2><p>{course.description}</p><div className={styles.readerSteps} aria-label="Этапы курса"><span>01 Материалы</span><span>02 Проверка знаний</span><span>03 Результат</span></div><div className="progress-label"><span>Ваш прогресс</span><strong>{course.progress}%</strong></div><progress value={course.progress} max={100} aria-label="Прогресс курса" /></header>
      <div className="learning-layout"><nav className="learning-outline" aria-label="Содержание курса"><span className="small-label">СОДЕРЖАНИЕ</span>{outline.map((item, index) => <button key={item.id} type="button" className={section === item.id ? "learning-outline-item is-active" : "learning-outline-item"} aria-current={section === item.id ? "step" : undefined} onClick={() => setSection(item.id)}><span className="learning-outline-icon"><Icon name={item.icon} size={17} /></span><span>{index + 1}. {item.label}</span>{item.id === "quiz" && !canTakeQuiz && !course.completed && <small>После материала</small>}{item.id === "result" && <Icon name="check" size={15} />}</button>)}</nav>
        <div className="learning-panel">
          {section === "overview" && <section className="learning-section"><span className="small-label">О КУРСЕ</span><h3>Чему вы научитесь</h3>{course.objectives ? <div className="course-objectives"><p>{course.objectives}</p></div> : <p className="learning-muted">Изучите материалы курса и пройдите контрольный вопрос.</p>}<div className="learning-next"><span><Icon name="document" size={18} /> Начните с материала курса</span><button className="button button-primary" onClick={() => setSection("materials")}>Открыть материалы <Icon name="arrow" size={17} /></button></div></section>}
          {section === "materials" && <section className="learning-section"><span className="small-label">МАТЕРИАЛЫ</span><h3>Изучите содержание курса</h3><p className="learning-muted">Откройте документ и изучите его в удобном темпе. Отметка ниже сохраняет ваш прогресс.</p>{course.content && <article className="course-content"><div>{course.content}</div></article>}<div className="course-documents"><strong>Прикреплённые документы</strong>{materials.error ? <ErrorBox message={materials.error} retry={materials.reload} /> : materials.loading ? <Loading /> : materials.data?.length ? <ul>{materials.data.map((file) => <li key={file.id}><span className="academy-file-icon"><Icon name="document" size={20} /></span><span className="course-document-description"><strong>{file.title}</strong><small>{file.filename}</small><small>{file.classification === "external_legal_snapshot" ? "Предоставленная копия закона; актуальность не подтверждена" : file.classification === "synthetic_demo" ? "DEMO / SYNTHETIC" : "Внешний справочный материал"}</small></span><button type="button" className="button button-secondary button-small" onClick={() => api.download(`/knowledge-files/${file.id}/download`, file.filename, true).catch((cause) => notify(errorMessage(cause)))}>{file.filename.toLowerCase().endsWith(".pdf") ? "Открыть PDF" : "Скачать DOCX"}</button></li>)}</ul> : <p>Документы к курсу пока не прикреплены. AI Jana ответит только после их добавления HR.</p>}</div>{!course.completed && course.progress < 70 ? <div className="learning-complete-material"><p>Когда закончите, отметьте изучение материала. Затем откроется тест.</p><button className="button button-primary material-read" onClick={saveProgress} disabled={pending || resource.loading}>{pending ? "Сохраняем…" : "Материал изучен — перейти к тесту"}<Icon name="arrow" size={17} /></button></div> : <div className="academy-published"><Icon name="check" size={18} />{course.completed ? "Материал изучен. Курс завершён." : "Материал отмечен как изученный. Можно перейти к тесту."}</div>}</section>}
          <section className="learning-section" hidden={section !== "assistant"}><span className="small-label">ПОМОЩЬ В КУРСЕ</span><h3>Спросите AI Jana</h3><p className="learning-muted">Ответы основаны только на доступных материалах этого курса и содержат ссылки на источники.</p><CourseAssistant api={api} courseId={id} /></section>
          {section === "quiz" && <section className="learning-section"><span className="small-label">ПРОВЕРКА ЗНАНИЙ</span><h3>Контрольный вопрос</h3>{course.completed ? <div className="course-success"><Icon name="check" size={25} /><div><h3>Тест уже пройден</h3><p>Повторное прохождение не начисляет XP.</p></div></div> : !canTakeQuiz ? <div className="learning-locked"><Icon name="info" size={22} /><div><strong>Сначала изучите материал</strong><p>Откройте материалы и отметьте их изучение, чтобы перейти к тесту.</p><button className="button button-secondary" onClick={() => setSection("materials")}>Перейти к материалам</button></div></div> : <form className="course-test" onSubmit={complete}><fieldset disabled={pending || resource.loading}><legend>{course.question}</legend>{course.options.map((option, index) => <label className={`answer-option ${answer === index ? "answer-selected" : ""}`} key={index}><input type="radio" name="course-answer" checked={answer === index} onChange={() => setAnswer(index)} required /><span>{option}</span></label>)}</fieldset>{error && <ErrorBox message={error} />}<button className="button button-primary" disabled={pending || resource.loading || answer === null}>{pending ? "Проверяем…" : "Отправить ответ"}<Icon name="check" size={17} /></button></form>}</section>}
          {section === "result" && course.completed && <section className="learning-section"><span className="small-label">РЕЗУЛЬТАТ</span><div className="course-success learning-result"><Icon name="check" size={30} /><div><h3>Курс завершён</h3><p>Тест пройден, прогресс сохранён. За курс начислено 100 XP.</p></div></div><button className="button button-secondary" onClick={() => setSection("materials")}>Повторить материал</button></section>}
          {error && section !== "quiz" && <ErrorBox message={error} />}
        </div>
      </div>
      <div className="learning-footer"><button className="button button-secondary course-back" onClick={onClose} disabled={pending}>К списку курсов</button><span>Прогресс сохраняется в вашем аккаунте</span></div>
    </>}
  </Modal>;
}
