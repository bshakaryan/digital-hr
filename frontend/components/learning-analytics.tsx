"use client";

import { useMemo, useState } from "react";
import { ApiClient, type EmployeeLearning, type LearningAnalytics, type LearningAssignment, type LearningStatus, type Profile } from "@/lib/api";
import { categoryLabel, shortDate, statusLabel } from "@/lib/academy-labels";
import { Empty, ErrorBox, Loading } from "./ui";
import { useResource } from "./use-resource";
import styles from "./learning-analytics-ux.module.css";

type FilterStatus = "all" | LearningStatus | "overdue";
const statusOptions: { value: FilterStatus; label: string }[] = [
  { value: "all", label: "Все статусы" }, { value: "completed", label: "Завершены" },
  { value: "in_progress", label: "В процессе" }, { value: "not_started", label: "Не начаты" },
  { value: "overdue", label: "Просрочены" },
];

function matchesStatus(row: LearningAssignment, status: FilterStatus) {
  return status === "all" || (status === "overdue" ? row.overdue : row.status === status);
}

function normalizedName(value: string) {
  return value.normalize("NFKC").toLocaleLowerCase("ru").replace(/ё/g, "е").replace(/\s+/g, " ").trim();
}

function PercentBar({ value, label }: { value: number; label: string }) {
  return <div className={styles.track} role="img" aria-label={`${label}: ${Math.round(value * 10) / 10}%`}><span style={{ width: `${Math.min(100, Math.max(0, value))}%` }} /></div>;
}

function StatusBadge({ row }: { row: LearningAssignment }) {
  return <span className={styles.statuses}><span className={`learning-status is-${row.status}`}>{statusLabel[row.status]}</span>{row.overdue && <span className="learning-status is-overdue">Просрочен</span>}</span>;
}

function AssignmentProgress({ row }: { row: LearningAssignment }) {
  return <div className={styles.progress}><div><span>Прогресс</span><strong>{row.progress}%</strong></div><PercentBar value={row.progress} label={`Прогресс курса «${row.course_title}»`} /></div>;
}

function Kpi({ label, value, detail, attention = false }: { label: string; value: number | string; detail: string; attention?: boolean }) {
  return <div className={`${styles.kpi} ${attention ? styles.attention : ""}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}

function ProfileView({ api, employeeId, onBack }: { api: ApiClient; employeeId: number; onBack: () => void }) {
  const profile = useResource<EmployeeLearning>(api, `/courses/analytics/employees/${employeeId}`);
  const employee = profile.data;
  return <section className={`panel ${styles.profile}`} aria-label="Учебный профиль сотрудника">
    <button type="button" className="button button-secondary button-small" onClick={onBack}>← К списку сотрудников</button>
    {profile.error ? <ErrorBox message={profile.error} retry={profile.reload} /> : profile.loading && !employee ? <Loading /> : employee && <>
      <header className={styles.profileHeader}><div><span className="small-label">УЧЕБНЫЙ ПРОФИЛЬ</span><h2>{employee.employee_name}</h2><p>{employee.position} · {employee.department}{employee.manager_name ? ` · Руководитель: ${employee.manager_name}` : ""}</p></div><div className={styles.level}><strong>{employee.level} уровень</strong><span>{employee.xp} XP</span></div></header>
      <div className={styles.kpis} aria-label="Показатели сотрудника">
        <Kpi label="Назначено" value={employee.total_assigned} detail="курсов" />
        <Kpi label="Завершено" value={employee.completed} detail={`${employee.completion_rate}% назначений`} />
        <Kpi label="В процессе" value={employee.in_progress} detail="начатых курсов" />
        <Kpi label="Не начато" value={employee.not_started} detail="назначений" />
        <Kpi label="Просрочено" value={employee.overdue} detail="незавершённых" attention />
      </div>
      <div className={styles.profileSummary}><div><strong>Выполнение назначений</strong><span>{employee.completed} из {employee.total_assigned} · {employee.completion_rate}%</span></div><PercentBar value={employee.completion_rate} label="Выполнение назначений" /><p>{employee.badges.length ? `Достижения: ${employee.badges.join(" · ")}` : "Достижений пока нет"}</p></div>
      <div className={styles.sectionTitle}><div><span className="small-label">ПО КУРСАМ</span><h3>Прогресс обучения</h3></div><span>{employee.assignments.length} назначений</span></div>
      {employee.assignments.length ? <div className={styles.assignmentGrid}>{employee.assignments.map((row) => <article className={styles.assignmentCard} key={row.course_id}>
        <div className={styles.assignmentHeading}><div><span className="small-label">{categoryLabel[row.category]}</span><h4>{row.course_title}</h4></div><StatusBadge row={row} /></div>
        <AssignmentProgress row={row} />
        <dl className={styles.assignmentMeta}><div><dt>Срок</dt><dd>{shortDate(row.deadline)}</dd></div><div><dt>Последняя активность</dt><dd>{row.last_activity_at ? shortDate(row.last_activity_at.slice(0, 10)) : "Нет событий"}</dd></div><div><dt>Завершение</dt><dd>{row.status === "completed" ? row.completed_at ? shortDate(row.completed_at.slice(0, 10)) : "Дата не зафиксирована" : "Не завершён"}</dd></div></dl>
      </article>)}</div> : <Empty icon="book" title="Назначений пока нет" text="Курсы появятся после назначения HR." />}
    </>}
  </section>;
}

export function LearningAnalyticsPanel({ api, role }: { api: ApiClient; role: Profile["role"] }) {
  const isHr = role === "hr_admin";
  const dashboard = useResource<LearningAnalytics>(api, isHr ? "/courses/analytics" : "/courses/analytics/employees");
  const directory = useResource<EmployeeLearning[]>(api, "/courses/analytics/employees");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("all");
  const [courseId, setCourseId] = useState("all");
  const [status, setStatus] = useState<FilterStatus>("all");
  const employees = directory.data ?? [];
  const data = isHr ? dashboard.data : null;
  const departments = useMemo(() => [...new Set(employees.map((person) => person.department))].sort(), [employees]);
  const courses = useMemo(() => [...new Map(employees.flatMap((person) => person.assignments).map((row) => [row.course_id, { course_id: row.course_id, course_title: row.course_title }])).values()].sort((a, b) => a.course_title.localeCompare(b.course_title, "ru")), [employees]);
  const nameParts = normalizedName(search).split(" ").filter(Boolean);
  const visibleEmployees = employees.filter((person) => (department === "all" || person.department === department)
    && nameParts.every((part) => normalizedName(person.employee_name).includes(part))
    && ((courseId === "all" && status === "all") || person.assignments.some((row) => (courseId === "all" || String(row.course_id) === courseId) && matchesStatus(row, status))));
  const visibleRows = data?.assignments.filter((row) => (department === "all" || row.department === department)
    && nameParts.every((part) => normalizedName(row.employee_name).includes(part))
    && (courseId === "all" || String(row.course_id) === courseId) && matchesStatus(row, status)) ?? [];
  const hasFilters = search.trim() !== "" || department !== "all" || courseId !== "all" || status !== "all";
  function clearFilters() { setSearch(""); setDepartment("all"); setCourseId("all"); setStatus("all"); }

  return <section className={styles.root} aria-label="Аналитика обучения">
    <div className={`academy-section-heading ${styles.pageHeading}`}><div><span className="small-label">JANA ACADEMY · {isHr ? "HR" : "РУКОВОДИТЕЛЬ"}</span><h2>{isHr ? "Аналитика обучения" : "Обучение команды"}</h2><p>{isHr ? "Сводка по опубликованным назначениям демо сотрудников" : "Профили прямых подчинённых"}</p></div>{data && <span className={styles.asOf}>Данные на {shortDate(data.as_of)}</span>}</div>
    {selectedId !== null ? <ProfileView api={api} employeeId={selectedId} onBack={() => setSelectedId(null)} /> : <>
      {isHr && (dashboard.error ? <ErrorBox message={dashboard.error} retry={dashboard.reload} /> : dashboard.loading && !data ? <Loading /> : data && <>
        <div className={styles.kpis} aria-label="Ключевые показатели обучения">
          <Kpi label="Сотрудники" value={data.total_demo_employees} detail="демо профилей" />
          <Kpi label="Выполнение курсов" value={`${data.completion_rate}%`} detail={`${data.status_counts.completed} из ${data.total_assignments} назначений`} />
          <Kpi label="Просрочено" value={data.overdue_assignments} detail="незавершённых назначений" attention />
          <Kpi label="Активное обучение" value={data.status_counts.in_progress} detail="назначений в процессе" />
        </div>
        <p className={styles.scopeNote}>Опубликовано курсов: {data.published_courses}. Просрочка учитывается отдельно от статуса. Показатели и диаграммы охватывают все назначения демо сотрудников; фильтры применяются к списку профилей и мониторингу.</p>
        <div className={styles.chartGrid}>
          <section className={`panel ${styles.chartCard}`} aria-label="Назначения по статусу"><div className={styles.chartHeading}><h3>Назначения по статусу</h3><span>{data.total_assignments} всего</span></div>{data.total_assignments ? (["completed", "in_progress", "not_started"] as LearningStatus[]).map((key) => <div className={styles.chartRow} key={key}><span>{statusLabel[key]}</span><PercentBar value={data.status_counts[key] / data.total_assignments * 100} label={`Доля статуса «${statusLabel[key]}»`} /><strong>{data.status_counts[key]}</strong></div>) : <Empty icon="book" title="Назначений пока нет" text="Распределение появится после назначения курсов." />}</section>
          <section className={`panel ${styles.chartCard}`} aria-label="Выполнение по курсам"><div className={styles.chartHeading}><h3>Выполнение по курсам</h3><span>завершено / назначено</span></div>{data.course_completion.length ? data.course_completion.map((row) => <div className={styles.courseRow} key={row.course_id}><div><strong title={row.course_title}>{row.course_title}</strong><span>{row.completed} / {row.total} · {row.rate}%</span></div><PercentBar value={row.rate} label={`Выполнение курса «${row.course_title}»`} /></div>) : <Empty icon="book" title="По курсам пока нет данных" text="После назначения курсов здесь появится доля завершений." />}</section>
          <section className={`panel ${styles.chartCard}`} aria-label="Активность за 14 дней"><div className={styles.chartHeading}><h3>Активность за 14 дней</h3><span>события</span></div>{data.daily_activity.some((day) => day.count > 0) ? <div className={styles.activityChart}>{data.daily_activity.map((day) => <div key={day.date} className={styles.activityDay} title={`${shortDate(day.date)}: ${day.count} событий`}><span>{day.count || ""}</span><div className={styles.activityColumn}><i style={{ height: `${day.count / Math.max(1, ...data.daily_activity.map((entry) => entry.count)) * 100}%` }} /></div><small>{day.date.slice(8)}</small></div>)}</div> : <Empty icon="book" title="За 14 дней нет событий" text="Здесь появятся события сохранения прогресса и завершения курсов." />}<p className={styles.chartNote}>{data.activity_includes_demo ? "Демо: включает синтетическую историю учебных событий." : "Сохранение прогресса и завершение по журналу аудита."}</p></section>
          <section className={`panel ${styles.chartCard}`} aria-label="Просрочка по отделам"><div className={styles.chartHeading}><h3>Просрочка по отделам</h3><span>{data.overdue_assignments} всего</span></div>{data.overdue_by_department.length ? data.overdue_by_department.map((row) => <div className={styles.chartRow} key={row.department}><span title={row.department}>{row.department}</span><PercentBar value={row.count / Math.max(1, data.overdue_assignments) * 100} label={`Доля просрочек отдела «${row.department}»`} /><strong>{row.count}</strong></div>) : <Empty icon="book" title="Просрочек нет" text="Назначений с истёкшим сроком и незавершённым курсом нет." />}</section>
        </div>
      </>)}
      <div className={`panel ${styles.directory}`}><div className={styles.directoryHeading}><div><span className="small-label">СОТРУДНИКИ</span><h3>Учебные профили</h3><p>{isHr ? "Демо сотрудники" : "Прямые подчинённые"}</p></div><div className={styles.directoryTools}><span>{visibleEmployees.length} из {employees.length}</span>{hasFilters && <button type="button" onClick={clearFilters}>Сбросить фильтры</button>}</div></div>
        <div className={styles.filters}><label>Поиск по имени<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Имя сотрудника" /></label><label>Отдел<select value={department} onChange={(event) => setDepartment(event.target.value)}><option value="all">Все отделы</option>{departments.map((name) => <option key={name} value={name}>{name}</option>)}</select></label><label>Курс<select value={courseId} onChange={(event) => setCourseId(event.target.value)}><option value="all">Все курсы</option>{courses.map((course) => <option key={course.course_id} value={course.course_id}>{course.course_title}</option>)}</select></label><label>Статус<select value={status} onChange={(event) => setStatus(event.target.value as FilterStatus)}>{statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label></div>
        {directory.error ? <ErrorBox message={directory.error} retry={directory.reload} /> : directory.loading && !directory.data ? <Loading /> : visibleEmployees.length ? <div className={styles.peopleGrid}>{visibleEmployees.map((person) => <button type="button" className={styles.personCard} key={person.employee_id} onClick={() => setSelectedId(person.employee_id)}><div><strong>{person.employee_name}</strong><span>{person.position} · {person.department}</span></div><div className={styles.personMetrics}><span>{person.completed} / {person.total_assigned} завершено</span><span>{person.overdue ? `${person.overdue} просрочено` : `${person.xp} XP`}</span></div><PercentBar value={person.completion_rate} label={`Выполнение назначений: ${person.employee_name}`} /><small>Открыть профиль →</small></button>)}</div> : <Empty icon="book" title={hasFilters ? "По фильтрам сотрудников нет" : "Профилей пока нет"} text={hasFilters ? "Измените фильтры или сбросьте их." : "Учебные профили появятся после добавления доступных сотрудников."} />}</div>
      {data && <div className={`panel ${styles.monitoring}`}><div className={styles.sectionTitle}><div><span className="small-label">НАЗНАЧЕНИЯ</span><h3>Мониторинг курсов</h3></div><span>{visibleRows.length} из {data.assignments.length}</span></div>{visibleRows.length ? <div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Сотрудник</th><th>Отдел</th><th>Курс</th><th>Прогресс</th><th>Срок</th><th>Статус</th><th>Активность</th></tr></thead><tbody>{visibleRows.map((row) => <tr key={`${row.employee_id}-${row.course_id}`}><td><button type="button" className={styles.tableLink} onClick={() => setSelectedId(row.employee_id)}>{row.employee_name}</button></td><td>{row.department}</td><td>{row.course_title}</td><td><AssignmentProgress row={row} /></td><td>{shortDate(row.deadline)}</td><td><StatusBadge row={row} /></td><td>{row.last_activity_at ? shortDate(row.last_activity_at.slice(0, 10)) : "Нет событий"}</td></tr>)}</tbody></table></div> : <Empty icon="book" title={hasFilters ? "Назначения не найдены" : "Назначений пока нет"} text={hasFilters ? "Измените фильтры мониторинга." : "Назначения появятся после добавления курсов сотрудникам."} />}</div>}
    </>}
  </section>;
}
