"use client";

import { useEffect, useState } from "react";
import { ApiClient, type AcademyRewards, type Course, type Profile, type PublicCourse } from "@/lib/api";
import { categoryLabel, shortDate, statusLabel } from "@/lib/academy-labels";
import { Empty, ErrorBox, Icon, Loading } from "./ui";
import { useResource, type Resource } from "./use-resource";
import { PageHeading } from "./workspace";
import { CourseReader } from "./academy";
import { CourseAdmin } from "./course-admin";
import { LearningAnalyticsPanel } from "./learning-analytics";

type LearningFilter = "all" | "completed" | "in_progress" | "not_started" | "overdue";
const filters: { key: LearningFilter; label: string }[] = [
  { key: "all", label: "Все" }, { key: "in_progress", label: "В процессе" },
  { key: "not_started", label: "Не начаты" }, { key: "completed", label: "Завершены" },
  { key: "overdue", label: "Просрочены" },
];

export function Academy({ api, courses, role, onChanged, notify, initialCourseId = null }: { api: ApiClient; courses: Resource<Course[]>; role: Profile["role"]; onChanged: () => void; notify: (message: string) => void; initialCourseId?: number | null }) {
  const [selected, setSelected] = useState<number | null>(initialCourseId);
  const [filter, setFilter] = useState<LearningFilter>("all");
  const rewards = useResource<AcademyRewards>(api, "/courses/rewards");
  const catalog = useResource<PublicCourse[]>(api, "/courses/discover");
  useEffect(() => { setSelected(initialCourseId); }, [initialCourseId]);
  const assigned = courses.data ?? [];
  const filtered = assigned.filter((course) => filter === "all" || (filter === "overdue" ? course.overdue : course.learning_status === filter));
  const assignedIds = new Set(assigned.map((course) => course.id));

  return <>
    <PageHeading eyebrow="JANA ACADEMY" title={role === "hr_admin" ? "Курсы и обучение" : "Моё обучение"} />
    <div className="academy-banner"><span className="metric-icon mint"><Icon name="book" size={27} /></span><div><h2>Растём вместе</h2><p>Изучайте назначенные материалы и проходите тесты. Прогресс сохраняется автоматически.</p></div><span className="academy-total">{courses.data ? `${assigned.filter((course) => course.completed).length} / ${assigned.length}` : "—"}<small>курсов завершено</small></span></div>
    {rewards.data && <section className="academy-rewards"><strong>Уровень {rewards.data.level} · {rewards.data.xp} XP</strong><progress value={rewards.data.xp} max={rewards.data.next_level_xp} aria-label="Прогресс уровня" /><span>До следующего уровня: {Math.max(0, rewards.data.next_level_xp - rewards.data.xp)} XP</span>{rewards.data.badges.map((badge) => <span className="tag" key={badge}>★ {badge}</span>)}</section>}
    {rewards.error && <ErrorBox message={rewards.error} retry={rewards.reload} />}
    {(role === "hr_admin" || role === "manager") && <LearningAnalyticsPanel api={api} role={role} />}
    {role === "hr_admin" && <CourseAdmin api={api} notify={notify} />}
    <section className="academy-my-courses" aria-label="Назначенные курсы"><div className="academy-section-heading"><div><span className="small-label">МОЁ ОБУЧЕНИЕ</span><h2>Назначенные курсы</h2></div><span>{assigned.length}</span></div>
      <div className="academy-filter-tabs" role="group" aria-label="Фильтр назначенных курсов">{filters.map((item) => <button key={item.key} type="button" className={filter === item.key ? "is-active" : ""} aria-pressed={filter === item.key} onClick={() => setFilter(item.key)}>{item.label}<span>{item.key === "all" ? assigned.length : assigned.filter((course) => item.key === "overdue" ? course.overdue : course.learning_status === item.key).length}</span></button>)}</div>
      {courses.error ? <ErrorBox message={courses.error} retry={courses.reload} /> : courses.loading && !courses.data ? <Loading /> : !filtered.length ? <div className="panel"><Empty icon="book" title={assigned.length ? "По этому фильтру курсов нет" : "Ваше обучение ещё впереди"} text={assigned.length ? "Выберите другой статус, чтобы увидеть курсы." : "Когда HR назначит курс, он появится здесь."} /></div> : <div className="courses-grid">{filtered.map((course, index) => <article className="panel course-card" key={course.id}><div className={`course-card-cover cover-${index % 3}`}><span className="small-label">{categoryLabel[course.category]}</span><Icon name={index % 2 ? "shield" : "leaf"} size={64} /><span className="course-cover-arrow">↗</span></div><div className="course-card-body"><span className="course-meta"><Icon name="clock" size={14} />{course.duration_minutes} мин. · {course.deadline ? `до ${shortDate(course.deadline)}` : "без срока"}</span><h2>{course.title}</h2><p>{course.description}</p><div className="academy-course-status"><span className={`learning-status ${course.overdue ? "is-overdue" : `is-${course.learning_status}`}`}>{course.overdue ? "Просрочен" : statusLabel[course.learning_status]}</span>{course.is_demo && <small>DEMO / SYNTHETIC</small>}</div><div className="progress-label"><span>Прогресс</span><strong>{course.progress}%</strong></div><progress value={course.progress} max={100} aria-label={`Прогресс: ${course.title}`} /><button className="button button-secondary" onClick={() => setSelected(course.id)}>{course.completed ? "Повторить материал" : course.progress ? "Продолжить" : "Начать обучение"}<Icon name="arrow" size={17} /></button></div></article>)}</div>}
    </section>
    <section className="academy-public-catalog" aria-label="Общий каталог курсов"><div className="academy-section-heading"><div><span className="small-label">КАТАЛОГ</span><h2>Общий каталог курсов</h2></div><span>{catalog.data?.length ?? "—"}</span></div><p className="learning-analytics-note">Здесь показаны опубликованные курсы с доступными вам материалами. Записать на курс может HR.</p>
      {catalog.error ? <ErrorBox message={catalog.error} retry={catalog.reload} /> : catalog.loading && !catalog.data ? <Loading /> : !catalog.data?.length ? <div className="panel"><Empty icon="book" title="Каталог пока пуст" text="Курсы появятся после публикации и добавления материалов." /></div> : <div className="academy-catalog-grid">{catalog.data.map((course) => <article className="panel academy-catalog-card" key={course.id}><span className="small-label">{categoryLabel[course.category]}</span><h3>{course.title}</h3><p>{course.description}</p><footer><span><Icon name="clock" size={14} /> {course.duration_minutes} мин.</span>{assignedIds.has(course.id) ? <span className="learning-status is-completed">Назначен</span> : <span>Доступен по назначению HR</span>}</footer></article>)}</div>}
    </section>
    {selected !== null && <CourseReader key={selected} id={selected} api={api} onClose={() => setSelected(null)} onChanged={onChanged} notify={notify} onRewardsChanged={rewards.reload} />}
  </>;
}
