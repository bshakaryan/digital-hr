"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ApiClient, errorMessage, type CourseCatalogItem, type CourseCategory, type KnowledgeFile, type Profile } from "@/lib/api";
import { categoryLabel } from "@/lib/academy-labels";
import { Empty, ErrorBox, Icon, Loading } from "./ui";
import { useResource } from "./use-resource";
import { KnowledgeAdmin } from "./knowledge-admin";

type CourseDraft = { title: string; description: string; objectives: string; duration_minutes: number; category: CourseCategory };
const scopeLabel: Record<KnowledgeFile["access_scope"], string> = {
  all: "все роли", employee: "сотрудники", manager: "руководители", hr_admin: "только HR",
};
type EditorStep = "details" | "materials" | "quiz" | "preview" | "publish";
const editorSteps: { id: EditorStep; label: string }[] = [
  { id: "details", label: "О курсе" }, { id: "materials", label: "Материалы" },
  { id: "quiz", label: "Тест" }, { id: "preview", label: "Предпросмотр" }, { id: "publish", label: "Публикация" },
];

function DocumentPicker({ files, value, onChange, disabled }: { files: KnowledgeFile[]; value: string; onChange: (value: string) => void; disabled: boolean }) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const selected = files.find((file) => String(file.id) === value);

  useEffect(() => {
    if (!open) return;
    list.current?.focus();
    const closeOutside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [open]);

  function choose(file: KnowledgeFile) {
    onChange(String(file.id));
    setOpen(false);
    trigger.current?.focus();
  }

  return <div ref={root} className="academy-document-picker" onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false); }}>
    <button ref={trigger} type="button" className={`academy-document-trigger ${open ? "is-open" : ""}`} aria-label={selected ? `Документ курса: ${selected.title}` : "Документ курса: не выбран"} aria-haspopup="listbox" aria-expanded={open} aria-controls={listId} disabled={disabled || !files.length} onClick={() => { setActive(Math.max(0, files.findIndex((file) => String(file.id) === value))); setOpen((current) => !current); }} onKeyDown={(event) => { if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setActive(Math.max(0, files.findIndex((file) => String(file.id) === value))); setOpen(true); } }}>
      <span className="academy-document-trigger-icon"><Icon name="document" size={18} /></span>
      <span className="academy-document-trigger-text">{selected ? <><strong>{selected.title}</strong><small>{selected.filename}</small></> : <span>{files.length ? "Выберите документ из базы знаний" : "Нет доступных документов"}</span>}</span>
      <Icon name="chevron" size={17} />
    </button>
    {open && <div ref={list} id={listId} className="academy-document-options" role="listbox" aria-label="Документы базы знаний" aria-activedescendant={files[active] ? `${listId}-option-${files[active].id}` : undefined} tabIndex={-1} onKeyDown={(event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setActive((current) => (current + (event.key === "ArrowDown" ? 1 : -1) + files.length) % files.length); }
      else if (event.key === "Home" || event.key === "End") { event.preventDefault(); setActive(event.key === "Home" ? 0 : files.length - 1); }
      else if ((event.key === "Enter" || event.key === " ") && files[active]) { event.preventDefault(); choose(files[active]); }
      else if (event.key === "Escape") { event.preventDefault(); setOpen(false); trigger.current?.focus(); }
    }}>{files.map((file, index) => <div key={file.id} id={`${listId}-option-${file.id}`} className={`academy-document-option ${active === index ? "is-active" : ""}`} role="option" aria-selected={String(file.id) === value} onMouseEnter={() => setActive(index)} onClick={() => choose(file)}><span className="academy-document-option-icon"><Icon name="document" size={18} /></span><span className="academy-document-option-text"><strong>{file.title}</strong><small>{file.filename} · {scopeLabel[file.access_scope]}</small></span><span className="academy-document-format">{file.filename.toLowerCase().endsWith(".pdf") ? "PDF" : "DOCX"}</span></div>)}</div>}
  </div>;
}

export function CourseAdmin({ api, notify }: { api: ApiClient; notify: (message: string) => void }) {
  const catalog = useResource<CourseCatalogItem[]>(api, "/courses/catalog");
  const [selected, setSelected] = useState<CourseCatalogItem | null>(null);
  const [creating, setCreating] = useState(false);
  const [newCourse, setNewCourse] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [objectives, setObjectives] = useState("");
  const [duration, setDuration] = useState("10");
  const [category, setCategory] = useState<CourseCategory>("general");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function create(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    const body: CourseDraft = { title: title.trim(), description: description.trim(), objectives: objectives.trim(), duration_minutes: Number(duration), category };
    try {
      const item = await api.post<CourseCatalogItem>("/courses", body);
      setSelected(item); setCreating(false); setNewCourse(true); catalog.reload(); setTitle(""); setDescription(""); setObjectives(""); setDuration("10"); setCategory("general");
      notify("Черновик курса создан. Прикрепите материал и подготовьте тест.");
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  }

  return <section className="academy-admin" aria-label="Управление курсами">
    <div className="academy-admin-heading"><div><span className="small-label">JANA ACADEMY · HR</span><h2>Управление курсами</h2><p>Подготовьте курс, проверьте материал и тест, затем назначьте его сотрудникам.</p></div><button className="button button-primary" type="button" onClick={() => { setSelected(null); setCreating(true); setNewCourse(false); setError(""); }}><Icon name="plus" size={18} /> Новый курс</button></div>
    {error && <ErrorBox message={error} />}
    <div className="academy-admin-layout"><aside className="academy-course-library" aria-label="Каталог курсов"><div className="academy-library-heading"><h3>Курсы</h3><span>{catalog.data?.length ?? "—"}</span></div>
      {catalog.error && <ErrorBox message={catalog.error} retry={catalog.reload} />}
      {catalog.loading && !catalog.data ? <Loading /> : !catalog.data?.length ? <p className="academy-library-empty">Пока нет курсов. Начните с нового черновика.</p> : <div className="academy-admin-list">{catalog.data.map((item) => <button key={item.id} type="button" className={selected?.id === item.id && !creating ? "academy-admin-item is-active" : "academy-admin-item"} onClick={() => { setSelected(item); setCreating(false); setNewCourse(false); setError(""); }}><strong>{item.title}</strong><span>{item.status === "draft" ? "Черновик" : "Опубликован"}</span></button>)}</div>}
    </aside><div className="academy-admin-content">
      {creating ? <section className="academy-editor" aria-label="Новый курс"><div className="academy-editor-title"><div><span className="small-label">ШАГ 1 ИЗ 5</span><h3>О курсе</h3><p>Название и цели помогут сотруднику понять, чему он научится.</p></div><span className="tag">Черновик</span></div><div className="academy-step-content"><form className="academy-admin-grid" onSubmit={create}>
        <label>Название курса<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} required /></label>
        <label>Длительность, мин.<input type="number" min={1} max={480} value={duration} onChange={(event) => setDuration(event.target.value)} required /></label>
        <label className="academy-admin-wide">Категория<select value={category} onChange={(event) => setCategory(event.target.value as CourseCategory)}>{Object.entries(categoryLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="academy-admin-wide">Краткое описание<input value={description} onChange={(event) => setDescription(event.target.value)} maxLength={2000} required /></label>
        <label className="academy-admin-wide">Цели обучения<textarea value={objectives} onChange={(event) => setObjectives(event.target.value)} maxLength={2000} required /></label>
        <button className="button button-primary" disabled={busy}>{busy ? "Создаём…" : "Создать черновик"}</button>
      </form></div></section> : selected ? <CourseEditor key={selected.id} api={api} initial={selected} initialStep={newCourse ? "materials" : "details"} notify={notify} onCatalogChanged={catalog.reload} /> : <div className="academy-admin-welcome"><Empty icon="book" title="Выберите курс или создайте новый" text="Черновик можно сохранить, дополнить материалами и тестом, а затем опубликовать." action={<button className="button button-primary" type="button" onClick={() => setCreating(true)}>Создать курс</button>} /></div>}
    </div></div>
  </section>;
}

function CourseEditor({ api, initial, initialStep, notify, onCatalogChanged }: { api: ApiClient; initial: CourseCatalogItem; initialStep: EditorStep; notify: (message: string) => void; onCatalogChanged: () => void }) {
  const [course, setCourse] = useState(initial);
  const [step, setStep] = useState<EditorStep>(initialStep);
  const editorTop = useRef<HTMLDivElement>(null);
  const [title, setTitle] = useState(initial.title);
  const [description, setDescription] = useState(initial.description);
  const [objectives, setObjectives] = useState(initial.objectives);
  const [duration, setDuration] = useState(String(initial.duration_minutes));
  const [category, setCategory] = useState<CourseCategory>(initial.category);
  const [question, setQuestion] = useState(initial.question);
  const [options, setOptions] = useState(initial.options.length >= 2 ? initial.options : ["", ""]);
  const [correct, setCorrect] = useState(initial.correct_index);
  const [fileId, setFileId] = useState("");
  const [employeeIds, setEmployeeIds] = useState<number[]>([]);
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [deadline, setDeadline] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const files = useResource<KnowledgeFile[]>(api, "/knowledge-files");
  const materials = useResource<KnowledgeFile[]>(api, `/courses/${course.id}/materials`);
  const employees = useResource<Profile[]>(api, "/employees");

  async function run(action: () => Promise<CourseCatalogItem | void>, success: string) {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const updated = await action();
      if (updated) { setCourse(updated); onCatalogChanged(); }
      if (success) notify(success);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  }

  function saveDetails(event: FormEvent) {
    event.preventDefault();
    void run(() => api.patch<CourseCatalogItem>(`/courses/${course.id}`, { title: title.trim(), description: description.trim(), objectives: objectives.trim(), duration_minutes: Number(duration), category }), "Данные курса сохранены.");
  }
  function saveQuiz(event: FormEvent) {
    event.preventDefault();
    void run(() => api.put<CourseCatalogItem>(`/courses/${course.id}/quiz`, { question: question.trim(), options: options.map((value) => value.trim()), correct_index: correct }), "Тест сохранён.");
  }
  function attach(event: FormEvent) {
    event.preventDefault();
    void run(async () => { await api.post(`/courses/${course.id}/materials`, { file_id: Number(fileId) }); setFileId(""); materials.reload(); }, "Документ прикреплён к курсу.");
  }
  function publish() {
    void run(() => api.post<CourseCatalogItem>(`/courses/${course.id}/publish`, {}), "Курс опубликован. Теперь его можно назначить сотруднику.");
  }
  async function assign(event: FormEvent) {
    event.preventDefault();
    if (busy || employeeIds.length === 0) return;
    setBusy(true); setError("");
    let assigned = 0;
    let existing = 0;
    const failed: number[] = [];
    const failureMessages: string[] = [];
    for (const id of employeeIds) {
      try {
        const result = await api.post<{ assigned: boolean }>(`/courses/${course.id}/assign`, { employee_id: id, deadline: deadline || null });
        if (result.assigned) assigned += 1;
        else existing += 1;
      } catch (cause) {
        failed.push(id);
        const name = employees.data?.find((person) => person.id === id)?.full_name || `ID ${id}`;
        failureMessages.push(`${name}: ${errorMessage(cause)}`);
      }
    }
    setEmployeeIds(failed);
    setBusy(false);
    if (assigned || existing) notify(`Назначено: ${assigned}. Уже было назначено: ${existing}.`);
    if (failed.length) setError(`Не удалось назначить курс (${failed.length}): ${failureMessages.join("; ")}`);
  }

  const learnerList = employees.data?.filter((person) => person.role !== "hr_admin") || [];
  const visibleLearners = learnerList.filter((person) => `${person.full_name} ${person.department}`.toLocaleLowerCase().includes(employeeSearch.trim().toLocaleLowerCase()));
  const allVisibleSelected = visibleLearners.length > 0 && visibleLearners.every((person) => employeeIds.includes(person.id));

  function toggleVisible() {
    const visibleIds = visibleLearners.map((person) => person.id);
    setEmployeeIds((current) => allVisibleSelected ? current.filter((id) => !visibleIds.includes(id)) : [...new Set([...current, ...visibleIds])]);
  }

  const hasLearnerMaterial = !!materials.data?.some((file) => file.access_scope !== "hr_admin");
  const hasQuiz = !!course.question && course.options.length >= 2;
  const availableFiles = files.data?.filter((file) => !materials.data?.some((attached) => attached.id === file.id)) || [];

  function goToStep(next: EditorStep) {
    setStep(next);
    setError("");
    window.requestAnimationFrame(() => editorTop.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }));
  }

  return <div className="academy-editor">
    <div ref={editorTop} className="academy-editor-title"><div><span className="small-label">КУРС · #{course.id}</span><h3>{course.title}</h3><p>{course.status === "draft" ? "Подготовка курса" : "Курс доступен назначенным сотрудникам"}</p></div><span className="tag">{course.status === "draft" ? "Черновик" : "Опубликован"}</span></div>
    <nav className="academy-stepper" aria-label="Шаги подготовки курса">{editorSteps.map((item, index) => <button key={item.id} type="button" className={step === item.id ? "academy-step is-active" : "academy-step"} aria-current={step === item.id ? "step" : undefined} disabled={busy} onClick={() => goToStep(item.id)}><span className="academy-step-number">{index + 1}</span><span>{item.label}</span></button>)}</nav>
    {error && <ErrorBox message={error} />}
    {step === "details" && <section className="academy-step-content"><div className="academy-step-heading"><h4>О курсе</h4><p>Коротко опишите тему, результат обучения и примерное время изучения.</p></div><form className="academy-admin-grid" onSubmit={saveDetails}>
      <label>Название<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} required /></label>
      <label>Длительность, мин.<input type="number" min={1} max={480} value={duration} onChange={(event) => setDuration(event.target.value)} required /></label>
      <label className="academy-admin-wide">Категория<select value={category} onChange={(event) => setCategory(event.target.value as CourseCategory)}>{Object.entries(categoryLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label className="academy-admin-wide">Описание<input value={description} onChange={(event) => setDescription(event.target.value)} maxLength={2000} required /></label>
      <label className="academy-admin-wide">Цели обучения<textarea value={objectives} onChange={(event) => setObjectives(event.target.value)} maxLength={2000} required /></label>
      <button className="button button-secondary" disabled={busy}>Сохранить изменения</button>
    </form></section>}
    {step === "materials" && <section className="academy-step-content"><div className="academy-step-heading"><h4>Материалы курса</h4><p>AI Jana использует только прикреплённые документы, доступные ученику.</p></div>
      {files.error && <ErrorBox message={files.error} retry={files.reload} />}{materials.error && <ErrorBox message={materials.error} retry={materials.reload} />}
      {materials.loading && !materials.data ? <Loading /> : materials.data?.length ? <ul className="academy-material-list">{materials.data.map((file) => <li key={file.id}><span className="academy-file-icon"><Icon name="document" size={19} /></span><span><strong>{file.title}</strong><small>{file.filename} · {scopeLabel[file.access_scope]}</small></span><span className="tag">{file.filename.toLowerCase().endsWith(".pdf") ? "PDF" : "DOCX"}</span></li>)}</ul> : <div className="academy-step-empty"><Icon name="document" size={21} /><span>Пока нет материалов. Прикрепите документ из базы знаний.</span></div>}
      <form className="academy-inline" onSubmit={attach}><DocumentPicker files={availableFiles} value={fileId} onChange={setFileId} disabled={files.loading || busy} /><button className="button button-secondary" disabled={busy || !fileId}>Прикрепить</button><button className="text-button" type="button" onClick={files.reload}>Обновить список</button></form>
      <details className="academy-upload-disclosure"><summary>Загрузить новый PDF или DOCX</summary><KnowledgeAdmin api={api} notify={notify} compact onUploaded={files.reload} /></details>
      <div className="academy-step-actions"><span className="academy-field-note">{hasLearnerMaterial ? "Материал прикреплён. Можно подготовить тест." : "Чтобы перейти к тесту, прикрепите документ, доступный ученику."}</span><button type="button" className="button button-primary" disabled={busy || materials.loading || !hasLearnerMaterial} onClick={() => goToStep("quiz")}>Далее: тест <Icon name="arrow" size={16} /></button></div>
    </section>}
    {step === "quiz" && <section className="academy-step-content"><div className="academy-step-heading"><h4>Контрольный вопрос</h4><p>Один вопрос с 2–4 вариантами. После публикации ответы не меняются.</p></div>
      <form className="academy-quiz-editor" onSubmit={saveQuiz}><label>Вопрос<input value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={500} required disabled={course.status === "published"} /></label>
        {options.map((option, index) => <div className="academy-option-editor" key={index}><input type="radio" name={`right-${course.id}`} checked={correct === index} onChange={() => setCorrect(index)} disabled={course.status === "published"} aria-label={`Правильный ответ ${index + 1}`} /><input value={option} onChange={(event) => setOptions((old) => old.map((value, position) => position === index ? event.target.value : value))} maxLength={300} required disabled={course.status === "published"} aria-label={`Вариант ${index + 1}`} /></div>)}
        {course.status === "draft" ? <div className="academy-inline"><button type="button" className="text-button" onClick={() => setOptions((old) => [...old, ""])} disabled={options.length >= 4}>Добавить вариант</button><button type="button" className="text-button" onClick={() => { setOptions((old) => old.slice(0, -1)); setCorrect(0); }} disabled={options.length <= 2}>Убрать последний</button><button className="button button-secondary" disabled={busy}>Сохранить тест</button></div> : <p className="academy-field-note">Тест опубликован и защищён от изменений, чтобы условия обучения оставались прежними.</p>}</form>
    </section>}
    {step === "preview" && <section className="academy-step-content"><div className="academy-step-heading"><h4>Предпросмотр курса</h4><p>Так сотрудник увидит основные сведения до начала обучения. Ответ на тест здесь не раскрывается.</p></div><div className="academy-preview-card"><span className="small-label">JANA ACADEMY · {course.duration_minutes} МИН.</span><h3>{course.title}</h3><p>{course.description}</p>{course.objectives && <div className="course-objectives"><strong>После курса вы сможете</strong><p>{course.objectives}</p></div>}<h4>Материалы</h4>{materials.loading && !materials.data ? <Loading /> : materials.data?.length ? <ul className="academy-preview-list">{materials.data.map((file) => <li key={file.id}><Icon name="document" size={17} />{file.title} · {file.filename}</li>)}</ul> : <p className="academy-field-note">Материалы ещё не прикреплены.</p>}<h4>Проверка знаний</h4>{hasQuiz ? <div className="academy-preview-question"><strong>{course.question}</strong>{course.options.map((option, index) => <span key={index}>{option}</span>)}</div> : <p className="academy-field-note">Тест ещё не сохранён.</p>}</div></section>}
    {step === "publish" && <section className="academy-step-content"><div className="academy-step-heading"><h4>Публикация и назначение</h4><p>Проверьте готовность курса. Ученики увидят его только после назначения.</p></div><div className="academy-readiness" aria-label="Готовность курса"><div><Icon name="check" size={17} /><span>Описание и цели сохранены</span></div><div className={hasLearnerMaterial ? "is-ready" : "is-missing"}><Icon name={hasLearnerMaterial ? "check" : "info"} size={17} /><span>{hasLearnerMaterial ? "Материал доступен ученику" : "Нужен материал, доступный сотруднику"}</span></div><div className={hasQuiz ? "is-ready" : "is-missing"}><Icon name={hasQuiz ? "check" : "info"} size={17} /><span>{hasQuiz ? "Контрольный вопрос сохранён" : "Сохраните контрольный вопрос"}</span></div></div>
      {course.status === "draft" ? <button type="button" className="button button-primary" disabled={busy || !hasLearnerMaterial || !hasQuiz || materials.loading} onClick={publish}>{busy ? "Публикуем…" : "Опубликовать курс"}</button> : <><div className="academy-published" role="status"><Icon name="check" size={20} /><span>Курс опубликован. Выберите сотрудников для назначения.</span></div><form className="academy-assignment" onSubmit={assign}>
        <label className="academy-assignment-search">Сотрудники<input type="search" value={employeeSearch} onChange={(event) => setEmployeeSearch(event.target.value)} placeholder="Поиск по имени или отделу" /></label>
        <label className="academy-assignment-search">Срок прохождения <span className="optional">· необязательно</span><input type="date" value={deadline} onChange={(event) => setDeadline(event.target.value)} /></label>
        <div className="academy-assignment-toolbar"><button className="text-button" type="button" onClick={toggleVisible} disabled={busy || !visibleLearners.length}>{allVisibleSelected ? "Снять выбор с найденных" : "Выбрать всех найденных"}</button><span>Выбрано: {employeeIds.length}</span></div>
        <fieldset className="academy-assignment-list" disabled={busy}><legend className="sr-only">Кому назначить курс</legend>{visibleLearners.map((person) => <label className="academy-assignment-person" key={person.id}><input type="checkbox" checked={employeeIds.includes(person.id)} onChange={() => setEmployeeIds((current) => current.includes(person.id) ? current.filter((id) => id !== person.id) : [...current, person.id])} /><span><strong>{person.full_name}</strong><small>{person.department} · {person.role === "manager" ? "Руководитель" : "Сотрудник"}</small></span></label>)}{!visibleLearners.length && <p>{employees.loading ? "Загружаем сотрудников…" : "Сотрудники не найдены"}</p>}</fieldset>
        <button className="button button-primary" disabled={busy || !employeeIds.length}>{busy ? "Назначаем…" : `Назначить курс (${employeeIds.length})`}</button>
      </form></>}
      {employees.error && <ErrorBox message={employees.error} retry={employees.reload} />}
    </section>}
  </div>;
}
