"use client";

import { useEffect, useState } from "react";
import { ApiClient, errorMessage, type AcademyRewards, type Course, type Profile, type PublicCourse } from "@/lib/api";
import { categoryLabel, shortDate, statusLabel } from "@/lib/academy-labels";
import { Empty, ErrorBox, Icon, Loading } from "./ui";
import { useResource, type Resource } from "./use-resource";
import { PageHeading } from "./workspace";
import { CourseReader } from "./academy";
import { CourseAdmin } from "./course-admin";
import { LearningAnalyticsPanel } from "./learning-analytics";
import { JanaJourney } from "./jana-journey";
import styles from "./academy-ux.module.css";

type LearningFilter = "all" | "completed" | "in_progress" | "not_started" | "overdue";
type AcademyView = "onboarding" | "development" | "team" | "manage" | "analytics";
const filters: { key: LearningFilter; label: string }[] = [
  { key: "all", label: "Все" }, { key: "in_progress", label: "В процессе" },
  { key: "not_started", label: "Не начаты" }, { key: "completed", label: "Завершены" },
  { key: "overdue", label: "Просрочены" },
];

function CourseCard({ course, index, onOpen }: { course: Course; index: number; onOpen: (id: number) => void }) {
  return <article className="panel course-card">
    <div className={"course-card-cover cover-" + index % 3}><span className="small-label">{categoryLabel[course.category]}</span><Icon name={course.category === "warehouse_safety" ? "shield" : "book"} size={48} /><span className={styles.routeLine} aria-hidden="true"><i /><i /><i /></span></div>
    <div className="course-card-body"><div className="academy-course-status"><span className={"learning-status " + (course.overdue ? "is-overdue" : "is-" + course.learning_status)}>{course.overdue ? "Просрочен" : statusLabel[course.learning_status]}</span>{course.is_demo && <small>DEMO / SYNTHETIC</small>}</div>
      <h3>{course.title}</h3><p>{course.description}</p>
      <div className={styles.courseFacts}><span><Icon name="clock" size={14} />{course.duration_minutes} мин.</span><span className={course.overdue ? styles.deadlineLate : ""}>{course.deadline ? "Срок: " + shortDate(course.deadline) : "Без срока"}</span></div>
      <div className="progress-label"><span>Прогресс</span><strong>{course.progress}%</strong></div><progress value={course.progress} max={100} aria-label={"Прогресс: " + course.title} />
      <button type="button" className="button button-secondary" onClick={() => onOpen(course.id)}>{course.completed ? "Повторить материал" : course.progress ? "Продолжить курс" : "Открыть курс"}<Icon name="arrow" size={17} /></button>
    </div>
  </article>;
}

function CourseList({ title, description, eyebrow, items, emptyTitle, emptyText, onOpen, filterable = true }: { title: string; description: string; eyebrow: string; items: Course[]; emptyTitle: string; emptyText: string; onOpen: (id: number) => void; filterable?: boolean }) {
  const [filter, setFilter] = useState<LearningFilter>("all");
  const visible = items.filter((course) => filter === "all" || (filter === "overdue" ? course.overdue : course.learning_status === filter));
  return <section className={"academy-my-courses " + styles.assigned} aria-label={title}>
    <div className="academy-section-heading"><div><span className={styles.eyebrow}>{eyebrow}</span><h2>{title}</h2><p>{description}</p></div><span className={styles.count}>{items.length}</span></div>
    {filterable && items.length > 0 && <div className="academy-filter-tabs" role="group" aria-label={"Фильтр: " + title}>{filters.map((item) => <button key={item.key} type="button" className={filter === item.key ? "is-active" : ""} aria-pressed={filter === item.key} onClick={() => setFilter(item.key)}>{item.label}<span>{item.key === "all" ? items.length : items.filter((course) => item.key === "overdue" ? course.overdue : course.learning_status === item.key).length}</span></button>)}</div>}
    {!visible.length ? <div className="panel"><Empty icon="book" title={items.length ? "По этому фильтру курсов нет" : emptyTitle} text={items.length ? "Выберите другой статус, чтобы увидеть курсы." : emptyText} /></div> : <div className="courses-grid">{visible.map((course, index) => <CourseCard key={course.id} course={course} index={index} onOpen={onOpen} />)}</div>}
  </section>;
}

function RewardsPanel({ rewards, error, retry }: { rewards: AcademyRewards | null; error: string | null; retry: () => void }) {
  return <>{rewards && <section className={styles.rewards} aria-label="Ваши награды"><div className={styles.levelMark}><Icon name="shield" size={24} /><span>УР. {rewards.level}</span></div><div className={styles.rewardBody}><div className={styles.rewardHeading}><div><span className={styles.eyebrow}>ВАШИ ДОСТИЖЕНИЯ</span><h2>Уровень {rewards.level} <span>· {rewards.xp} XP</span></h2></div><strong>{Math.max(0, rewards.next_level_xp - rewards.xp)} XP до следующего уровня</strong></div><progress value={rewards.xp} max={rewards.next_level_xp} aria-label="Прогресс уровня" /><div className={styles.badges}>{rewards.badges.length ? rewards.badges.map((badge) => <span className={styles.badge} key={badge}><Icon name="check" size={14} />{badge}</span>) : <span className={styles.badgeHint}>Первый значок появится после завершения курса.</span>}</div></div></section>}{error && <ErrorBox message={error} retry={retry} />}</>;
}

function DevelopmentCatalog({ api, catalog, assignments, onChanged, onOpen, notify }: { api: ApiClient; catalog: Resource<PublicCourse[]>; assignments: Course[]; onChanged: () => void; onOpen: (id: number) => void; notify: (message: string) => void }) {
  const [enrollingId, setEnrollingId] = useState<number | null>(null);
  const [enrollError, setEnrollError] = useState("");
  const assignedById = new Map(assignments.map((course) => [course.id, course]));
  const available = catalog.data?.filter((course) => course.self_enrollable) ?? [];
  async function enroll(course: PublicCourse) {
    if (enrollingId !== null) return;
    setEnrollingId(course.id); setEnrollError("");
    try {
      const result = await api.post<{ assigned: boolean; learning_track: Course["learning_track"] }>("/courses/" + course.id + "/enroll", {});
      onChanged();
      if (result.learning_track === "development") {
        notify(result.assigned ? "Вы записались на курс. Прогресс появится в «Моих курсах»." : "Курс уже есть в вашем обучении.");
        onOpen(course.id);
      } else {
        notify("Курс уже назначен вам в другом разделе Academy.");
      }
    } catch (cause) { setEnrollError(errorMessage(cause)); }
    finally { setEnrollingId(null); }
  }
  return <section className={"academy-public-catalog " + styles.catalog} aria-label="Каталог курсов для самостоятельной записи">
    <div className="academy-section-heading"><div><span className={styles.eyebrow}>РАЗВИТИЕ / КАТАЛОГ</span><h2>Каталог курсов</h2><p>Выберите курс и запишитесь самостоятельно. Завершение курса добавит XP по общим правилам Academy.</p></div><span className={styles.count}>{catalog.data ? available.length : "—"}</span></div>
    {enrollError && <ErrorBox message={enrollError} />}
    {catalog.error ? <ErrorBox message={catalog.error} retry={catalog.reload} /> : catalog.loading && !catalog.data ? <Loading /> : !available.length ? <div className="panel"><Empty icon="book" title="Открытых курсов пока нет" text="Когда HR откроет самостоятельную запись, курсы появятся здесь." /></div> : <div className="academy-catalog-grid">{available.map((course) => {
      const assigned = assignedById.get(course.id);
      return <article className="panel academy-catalog-card" key={course.id}><span className="small-label">{categoryLabel[course.category]} {course.is_demo && "· DEMO"}</span><h3>{course.title}</h3><p>{course.description}</p><footer><span><Icon name="clock" size={14} /> {course.duration_minutes} мин.</span>{assigned ? <button type="button" className={styles.catalogOpen} onClick={() => onOpen(course.id)}>{assigned.learning_track === "onboarding" ? "В адаптации · открыть" : "Открыть курс"}<Icon name="arrow" size={14} /></button> : <button type="button" className={styles.catalogOpen} disabled={enrollingId !== null} onClick={() => void enroll(course)}>{enrollingId === course.id ? "Записываем…" : "Записаться"}<Icon name="arrow" size={14} /></button>}</footer></article>;
    })}</div>}
  </section>;
}

export function Academy({ api, courses, role, onChanged, notify, initialCourseId = null }: { api: ApiClient; courses: Resource<Course[]>; role: Profile["role"]; onChanged: () => void; notify: (message: string) => void; initialCourseId?: number | null }) {
  const [selected, setSelected] = useState<number | null>(initialCourseId);
  const [view, setView] = useState<AcademyView>(role === "hr_admin" ? "manage" : "onboarding");
  const [developmentView, setDevelopmentView] = useState<"courses" | "catalog">("courses");
  const rewards = useResource<AcademyRewards>(api, "/courses/rewards");
  const catalog = useResource<PublicCourse[]>(api, "/courses/discover");
  const assigned = courses.data ?? [];
  const onboarding = assigned.filter((course) => course.learning_track === "onboarding");
  const development = assigned.filter((course) => course.learning_track === "development");
  const legacy = assigned.filter((course) => course.learning_track === "legacy");
  useEffect(() => { setSelected(initialCourseId); }, [initialCourseId]);
  useEffect(() => {
    if (initialCourseId === null || role === "hr_admin") return;
    const linkedCourse = courses.data?.find((course) => course.id === initialCourseId);
    if (linkedCourse) { setView(linkedCourse.learning_track === "onboarding" ? "onboarding" : "development"); setDevelopmentView("courses"); }
  }, [initialCourseId, courses.data, role]);
  const tabs: { id: AcademyView; label: string; count?: number }[] = role === "hr_admin"
    ? [{ id: "manage", label: "Управление курсами" }, { id: "analytics", label: "Аналитика" }]
    : [{ id: "onboarding", label: "Адаптация", count: onboarding.length }, { id: "development", label: "Моё развитие", count: development.length + legacy.length }, ...(role === "manager" ? [{ id: "team" as const, label: "Обучение команды" }] : [])];
  const visibleView = tabs.some((tab) => tab.id === view) ? view : tabs[0].id;
  return <div className={styles.dashboard}>
    <PageHeading eyebrow="JANA ACADEMY" title={role === "hr_admin" ? "Управление обучением" : "Jana Academy"} />
    <nav className={styles.destinationNav} aria-label="Разделы Jana Academy">{tabs.map((tab) => <button key={tab.id} type="button" className={styles.destinationTab + (visibleView === tab.id ? " " + styles.destinationActive : "")} aria-current={visibleView === tab.id ? "page" : undefined} onClick={() => setView(tab.id)}><span>{tab.label}</span>{tab.count !== undefined && <span className={styles.destinationCount}>{tab.count}</span>}</button>)}</nav>
    {visibleView === "onboarding" && <div className={styles.destinationPanel} aria-label="Адаптация"><header className={styles.viewIntro}><div><span className={styles.eyebrow}>ОБЯЗАТЕЛЬНЫЙ МАРШРУТ</span><h2>Адаптация</h2><p>Обязательные курсы и сроки в одном месте. Завершённые курсы адаптации продвигают посылку по маршруту Jana Journey.</p></div>{courses.data && <strong>{onboarding.filter((course) => course.completed).length} / {onboarding.length}<span> курсов завершено</span></strong>}</header>
      {courses.error ? <ErrorBox message={courses.error} retry={courses.reload} /> : courses.loading && !courses.data ? <Loading /> : <><JanaJourney courses={onboarding} rewards={null} /><CourseList title="Обязательные курсы" eyebrow="АДАПТАЦИЯ / КУРСЫ" description="Здесь учитываются только назначения HR для адаптации. Срок и прогресс указаны в каждой карточке." items={onboarding} emptyTitle="Курсов адаптации пока нет" emptyText="HR ещё не назначил вам обязательные курсы. Ваш маршрут начнётся после первого назначения." onOpen={setSelected} /></>}
    </div>}
    {visibleView === "development" && <div className={styles.destinationPanel} aria-label="Моё развитие"><header className={styles.viewIntro}><div><span className={styles.eyebrow}>ПРОФЕССИОНАЛЬНОЕ ОБУЧЕНИЕ</span><h2>Моё развитие</h2><p>Выбирайте доступные курсы, продолжайте обучение и следите за достижениями.</p></div></header>
      <RewardsPanel rewards={rewards.data} error={rewards.error} retry={rewards.reload} />
      <div className={styles.subNav} role="group" aria-label="Разделы развития"><button type="button" className={developmentView === "courses" ? styles.subActive : ""} aria-pressed={developmentView === "courses"} onClick={() => setDevelopmentView("courses")}>Мои курсы <span>{development.length + legacy.length}</span></button><button type="button" className={developmentView === "catalog" ? styles.subActive : ""} aria-pressed={developmentView === "catalog"} onClick={() => setDevelopmentView("catalog")}>Каталог</button></div>
      {developmentView === "courses" ? courses.error ? <ErrorBox message={courses.error} retry={courses.reload} /> : courses.loading && !courses.data ? <Loading /> : <><CourseList title="Курсы развития" eyebrow="РАЗВИТИЕ / МОИ КУРСЫ" description="Назначенные курсы развития и курсы, на которые вы записались самостоятельно." items={development} emptyTitle="Курсов развития пока нет" emptyText="Откройте каталог и выберите курс для самостоятельной записи." onOpen={setSelected} />{legacy.length > 0 && <CourseList title="Ранее назначенные курсы" eyebrow="СУЩЕСТВУЮЩИЕ НАЗНАЧЕНИЯ" description="Для этих назначений трек ещё не указан. Прогресс и завершение сохранены; HR может уточнить их назначение." items={legacy} emptyTitle="Ранее назначенных курсов нет" emptyText="" onOpen={setSelected} filterable={false} />}</> : <DevelopmentCatalog api={api} catalog={catalog} assignments={assigned} onChanged={onChanged} onOpen={setSelected} notify={notify} />}
    </div>}
    {visibleView === "team" && <div className={styles.destinationPanel}><LearningAnalyticsPanel api={api} role={role} /></div>}
    {visibleView === "manage" && <div className={styles.destinationPanel}><CourseAdmin api={api} notify={notify} /></div>}
    {visibleView === "analytics" && <div className={styles.destinationPanel}><LearningAnalyticsPanel api={api} role={role} /></div>}
    {selected !== null && <CourseReader key={selected} id={selected} api={api} onClose={() => setSelected(null)} onChanged={onChanged} notify={notify} onRewardsChanged={rewards.reload} />}
  </div>;
}
