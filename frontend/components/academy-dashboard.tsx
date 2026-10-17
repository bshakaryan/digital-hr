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
import styles from "./academy-ux.module.css";

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
  const completed = assigned.filter((course) => course.completed).length;
  const inProgress = assigned.filter((course) => course.learning_status === "in_progress").length;
  const overdue = assigned.filter((course) => course.overdue).length;

  return <div className={styles.dashboard}>
    <PageHeading eyebrow="JANA ACADEMY" title={role === "hr_admin" ? "Курсы и обучение" : "Моё обучение"} />
    <header className={styles.hero}><div><span className={styles.eyebrow}>ВАШ УЧЕБНЫЙ МАРШРУТ</span><h2>Учитесь в своём темпе</h2><p>Назначенные курсы, материалы и проверка знаний — в одном месте.</p></div><div className={styles.heroStats} aria-label="Сводка обучения"><div><strong>{courses.data ? completed : "—"}</strong><span>завершено</span></div><div><strong>{courses.data ? inProgress : "—"}</strong><span>в процессе</span></div><div><strong>{courses.data ? overdue : "—"}</strong><span>просрочено</span></div></div></header>
    {rewards.data && <section className={styles.rewards} aria-label="Ваши награды"><div className={styles.levelMark}><Icon name="shield" size={24} /><span>УР. {rewards.data.level}</span></div><div className={styles.rewardBody}><div className={styles.rewardHeading}><div><span className={styles.eyebrow}>ВАШИ ДОСТИЖЕНИЯ</span><h2>Уровень {rewards.data.level} <span>· {rewards.data.xp} XP</span></h2></div><strong>{Math.max(0, rewards.data.next_level_xp - rewards.data.xp)} XP до следующего уровня</strong></div><progress value={rewards.data.xp} max={rewards.data.next_level_xp} aria-label="Прогресс уровня" /><div className={styles.badges}>{rewards.data.badges.length ? rewards.data.badges.map((badge) => <span className={styles.badge} key={badge}><Icon name="check" size={14} />{badge}</span>) : <span className={styles.badgeHint}>Первый значок появится после завершения курса.</span>}</div></div></section>}
    {rewards.error && <ErrorBox message={rewards.error} retry={rewards.reload} />}
    {(role === "hr_admin" || role === "manager") && <LearningAnalyticsPanel api={api} role={role} />}
    {role === "hr_admin" && <CourseAdmin api={api} notify={notify} />}
    <section className={`academy-my-courses ${styles.assigned}`} aria-label="Назначенные курсы"><div className="academy-section-heading"><div><span className={styles.eyebrow}>01 / МОЁ ОБУЧЕНИЕ</span><h2>Назначенные курсы</h2><p>Материалы и тест доступны здесь. Прогресс сохраняется в вашем аккаунте.</p></div><span className={styles.count}>{assigned.length}</span></div>
      <div className="academy-filter-tabs" role="group" aria-label="Фильтр назначенных курсов">{filters.map((item) => <button key={item.key} type="button" className={filter === item.key ? "is-active" : ""} aria-pressed={filter === item.key} onClick={() => setFilter(item.key)}>{item.label}<span>{item.key === "all" ? assigned.length : assigned.filter((course) => item.key === "overdue" ? course.overdue : course.learning_status === item.key).length}</span></button>)}</div>
      {courses.error ? <ErrorBox message={courses.error} retry={courses.reload} /> : courses.loading && !courses.data ? <Loading /> : !filtered.length ? <div className="panel"><Empty icon="book" title={assigned.length ? "По этому фильтру курсов нет" : "Пока нет назначенных курсов"} text={assigned.length ? "Выберите другой статус, чтобы увидеть курсы." : "Когда HR назначит курс, материалы и тест появятся здесь. Пока можно посмотреть общий каталог ниже."} /></div> : <div className="courses-grid">{filtered.map((course, index) => <article className="panel course-card" key={course.id}><div className={`course-card-cover cover-${index % 3}`}><span className="small-label">{categoryLabel[course.category]}</span><Icon name={course.category === "warehouse_safety" ? "shield" : "book"} size={48} /><span className={styles.routeLine} aria-hidden="true"><i /><i /><i /></span></div><div className="course-card-body"><div className="academy-course-status"><span className={`learning-status ${course.overdue ? "is-overdue" : `is-${course.learning_status}`}`}>{course.overdue ? "Просрочен" : statusLabel[course.learning_status]}</span>{course.is_demo && <small>DEMO / SYNTHETIC</small>}</div><h2>{course.title}</h2><p>{course.description}</p><div className={styles.courseFacts}><span><Icon name="clock" size={14} />{course.duration_minutes} мин.</span><span className={course.overdue ? styles.deadlineLate : ""}>{course.deadline ? `Срок: ${shortDate(course.deadline)}` : "Без срока"}</span></div><div className="progress-label"><span>Прогресс</span><strong>{course.progress}%</strong></div><progress value={course.progress} max={100} aria-label={`Прогресс: ${course.title}`} /><button type="button" className="button button-secondary" onClick={() => setSelected(course.id)}>{course.completed ? "Повторить материал" : course.progress ? "Продолжить курс" : "Открыть курс"}<Icon name="arrow" size={17} /></button></div></article>)}</div>}
    </section>
    <section className={`academy-public-catalog ${styles.catalog}`} aria-label="Общий каталог курсов"><div className="academy-section-heading"><div><span className={styles.eyebrow}>02 / ОБЗОР</span><h2>Общий каталог</h2><p>Опубликованные курсы, доступные вашей роли. Для обучения нужно назначение HR.</p></div><span className={styles.count}>{catalog.data?.length ?? "—"}</span></div>
      {catalog.error ? <ErrorBox message={catalog.error} retry={catalog.reload} /> : catalog.loading && !catalog.data ? <Loading /> : !catalog.data?.length ? <div className="panel"><Empty icon="book" title="Каталог пока пуст" text="Курсы появятся после публикации и добавления материалов." /></div> : <div className="academy-catalog-grid">{catalog.data.map((course) => <article className="panel academy-catalog-card" key={course.id}><span className="small-label">{categoryLabel[course.category]} {course.is_demo && "· DEMO"}</span><h3>{course.title}</h3><p>{course.description}</p><footer><span><Icon name="clock" size={14} /> {course.duration_minutes} мин.</span>{assignedIds.has(course.id) ? <button type="button" className={styles.catalogOpen} onClick={() => setSelected(course.id)}>Назначен · открыть <Icon name="arrow" size={14} /></button> : <span>По назначению HR</span>}</footer></article>)}</div>}
    </section>
    {selected !== null && <CourseReader key={selected} id={selected} api={api} onClose={() => setSelected(null)} onChanged={onChanged} notify={notify} onRewardsChanged={rewards.reload} />}
  </div>;
}
