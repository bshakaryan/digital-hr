"use client";

import { useMemo, useState } from "react";
import { ApiClient, type EmployeeLearning, type LearningAnalytics, type LearningAssignment, type LearningStatus, type Profile } from "@/lib/api";
import { categoryLabel, shortDate, statusLabel } from "@/lib/academy-labels";
import { Empty, ErrorBox, Loading } from "./ui";
import { useResource } from "./use-resource";

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
  return <div className="learning-analytics-bar" aria-label={`${label}: ${value}%`}><span style={{ width: `${Math.min(100, Math.max(0, value))}%` }} /></div>;
}

function ProfileView({ api, employeeId, onBack }: { api: ApiClient; employeeId: number; onBack: () => void }) {
  const profile = useResource<EmployeeLearning>(api, `/courses/analytics/employees/${employeeId}`);
  const employee = profile.data;
  return <section className="learning-analytics-profile panel" aria-label="Учебный профиль сотрудника">
    <button type="button" className="button button-secondary button-small" onClick={onBack}>← К аналитике и сотрудникам</button>
    {profile.error ? <ErrorBox message={profile.error} retry={profile.reload} /> : profile.loading && !employee ? <Loading /> : employee && <>
      <div className="learning-profile-heading"><div><span className="small-label">УЧЕБНЫЙ ПРОФИЛЬ</span><h2>{employee.employee_name}</h2><p>{employee.position} · {employee.department}{employee.manager_name ? ` · Руководитель: ${employee.manager_name}` : ""}</p></div><strong>{employee.level} уровень · {employee.xp} XP</strong></div>
      <div className="learning-kpis compact"><div><span>Назначено</span><strong>{employee.total_assigned}</strong></div><div><span>Завершено</span><strong>{employee.completed}</strong></div><div><span>В процессе</span><strong>{employee.in_progress}</strong></div><div><span>Не начато</span><strong>{employee.not_started}</strong></div><div><span>Просрочено</span><strong>{employee.overdue}</strong></div></div>
      <div className="learning-profile-summary"><strong>Выполнено {employee.completion_rate}%</strong><PercentBar value={employee.completion_rate} label="Выполнение назначений" /><span>{employee.badges.length ? employee.badges.map((badge) => `★ ${badge}`).join(" · ") : "Достижений пока нет"}</span></div>
      <h3>Курсы сотрудника</h3>
      {employee.assignments.length ? <div className="learning-table-wrap"><table className="learning-table"><thead><tr><th>Курс</th><th>Прогресс</th><th>Срок</th><th>Статус</th><th>Тест / завершение</th><th>Активность</th></tr></thead><tbody>{employee.assignments.map((row) => <tr key={row.course_id}><td><strong>{row.course_title}</strong><small>{categoryLabel[row.category]}</small></td><td>{row.progress}%</td><td>{shortDate(row.deadline)}</td><td><StatusBadge row={row} /></td><td>{row.status === "completed" ? `Пройден${row.completed_at ? ` · ${shortDate(row.completed_at.slice(0, 10))}` : ""}` : "—"}</td><td>{row.last_activity_at ? shortDate(row.last_activity_at.slice(0, 10)) : "—"}</td></tr>)}</tbody></table></div> : <Empty icon="book" title="Назначений пока нет" text="Курсы появятся после назначения HR." />}
    </>}
  </section>;
}

function StatusBadge({ row }: { row: LearningAssignment }) {
  return <span className={`learning-status ${row.overdue ? "is-overdue" : `is-${row.status}`}`}>{row.overdue ? "Просрочен" : statusLabel[row.status]}</span>;
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
  const departments = useMemo(() => [...new Set(employees.map((person) => person.department))].sort(), [employees]);
  const nameParts = normalizedName(search).split(" ").filter(Boolean);
  const matchingNames = employees.filter((person) => nameParts.every((part) => normalizedName(person.employee_name).includes(part)));
  const filteredNames = matchingNames.filter((person) => {
    const rows = person.assignments;
    return (department === "all" || person.department === department)
      && (courseId === "all" || rows.some((row) => String(row.course_id) === courseId))
      && (status === "all" || rows.some((row) => matchesStatus(row, status)));
  });
  const filtersHideName = nameParts.length > 0 && matchingNames.length > 0 && filteredNames.length === 0;
  const visibleEmployees = filtersHideName ? matchingNames : filteredNames;
  const hasFilters = search.trim() !== "" || department !== "all" || courseId !== "all" || status !== "all";
  function clearFilters() { setSearch(""); setDepartment("all"); setCourseId("all"); setStatus("all"); }
  const data = isHr ? dashboard.data as LearningAnalytics | null : null;
  const visibleRows = data?.assignments.filter((row) => (department === "all" || row.department === department)
    && (courseId === "all" || String(row.course_id) === courseId) && matchesStatus(row, status)) ?? [];
  const courses = data?.course_completion ?? [...new Map(employees.flatMap((person) => person.assignments).map((row) => [row.course_id, { course_id: row.course_id, course_title: row.course_title }])).values()];

  return <section className="learning-analytics" aria-label="Аналитика обучения">
    <div className="academy-section-heading"><div><span className="small-label">JANA ACADEMY · {isHr ? "HR" : "РУКОВОДИТЕЛЬ"}</span><h2>{isHr ? "Аналитика обучения" : "Обучение команды"}</h2></div>{data && <span>Демо дата: {shortDate(data.as_of)}</span>}</div>
    {selectedId !== null ? <ProfileView api={api} employeeId={selectedId} onBack={() => setSelectedId(null)} /> : <>
      {isHr && (dashboard.error ? <ErrorBox message={dashboard.error} retry={dashboard.reload} /> : dashboard.loading && !data ? <Loading /> : data && <>
        <div className="learning-kpis"><div><span>Демо сотрудники</span><strong>{data.total_demo_employees}</strong></div><div><span>Опубликованные курсы</span><strong>{data.published_courses}</strong></div><div><span>Назначения</span><strong>{data.total_assignments}</strong></div><div><span>Выполнено</span><strong>{data.completion_rate}%</strong></div><div><span>Просрочено</span><strong>{data.overdue_assignments}</strong></div></div>
        <p className="learning-analytics-note">Выполнение = завершённые назначения / все назначения демо сотрудников. Просрочка считается отдельно и может совпадать со статусом «Не начат» или «В процессе».</p>
        <div className="learning-chart-grid"><div className="panel"><h3>Назначения по статусу</h3>{(["completed", "in_progress", "not_started"] as LearningStatus[]).map((key) => <div className="learning-chart-row" key={key}><span>{statusLabel[key]}</span><PercentBar value={data.total_assignments ? data.status_counts[key] / data.total_assignments * 100 : 0} label={statusLabel[key]} /><strong>{data.status_counts[key]}</strong></div>)}</div><div className="panel"><h3>Выполнение по курсам</h3>{data.course_completion.length ? data.course_completion.map((row) => <div className="learning-chart-row" key={row.course_id}><span title={row.course_title}>{row.course_title}</span><PercentBar value={row.rate} label={row.course_title} /><strong>{row.rate}%</strong></div>) : <p className="learning-analytics-note">Назначений пока нет.</p>}</div><div className="panel"><h3>Активность за 14 дней</h3><div className="learning-activity-chart">{data.daily_activity.map((day) => <div key={day.date} title={`${shortDate(day.date)}: ${day.count}`}><span style={{ height: `${day.count ? Math.max(10, day.count / Math.max(1, ...data.daily_activity.map((entry) => entry.count)) * 100) : 2}%` }} /><small>{day.date.slice(8)}</small></div>)}</div><p className="learning-analytics-note">События изучения и завершения курсов из журнала аудита.</p></div><div className="panel"><h3>Просрочка по отделам</h3>{data.overdue_by_department.length ? data.overdue_by_department.map((row) => <div className="learning-chart-row" key={row.department}><span>{row.department}</span><PercentBar value={row.count / Math.max(1, data.overdue_assignments) * 100} label={row.department} /><strong>{row.count}</strong></div>) : <p className="learning-analytics-note">Просроченных назначений нет.</p>}</div></div>
      </>)}
      <div className="panel learning-directory"><div className="learning-directory-heading"><div><span className="small-label">СОТРУДНИКИ</span><h3>Учебные профили</h3></div><div className="learning-directory-tools"><span>{visibleEmployees.length} из {employees.length}</span>{hasFilters && <button type="button" onClick={clearFilters}>Сбросить фильтры</button>}</div></div>
        <div className="learning-filter-row"><label>Поиск по имени<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Имя сотрудника" /></label><label>Отдел<select value={department} onChange={(event) => setDepartment(event.target.value)}><option value="all">Все отделы</option>{departments.map((name) => <option key={name} value={name}>{name}</option>)}</select></label><label>Курс<select value={courseId} onChange={(event) => setCourseId(event.target.value)}><option value="all">Все курсы</option>{courses.map((course) => <option key={course.course_id} value={course.course_id}>{course.course_title}</option>)}</select></label><label>Статус<select value={status} onChange={(event) => setStatus(event.target.value as FilterStatus)}>{statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label></div>
        {filtersHideName && <p className="learning-filter-explanation" role="status">Сотрудник найден по имени, но скрыт выбранными фильтрами. Показаны совпадения по имени; чтобы применить фильтры заново, сбросьте или измените их.</p>}
        {directory.error ? <ErrorBox message={directory.error} retry={directory.reload} /> : directory.loading && !directory.data ? <Loading /> : visibleEmployees.length ? <div className="learning-directory-grid">{visibleEmployees.map((person) => <button type="button" className="learning-person-card" key={person.employee_id} onClick={() => setSelectedId(person.employee_id)}><strong>{person.employee_name}</strong><span>{person.position} · {person.department}</span><small>{person.completed}/{person.total_assigned} завершено · {person.xp} XP{person.overdue ? ` · ${person.overdue} просрочено` : ""}</small><PercentBar value={person.completion_rate} label={person.employee_name} /></button>)}</div> : <Empty icon="book" title="Сотрудники не найдены" text="Измените фильтры или строку поиска." />}</div>
      {data && <div className="panel learning-monitoring"><h3>Мониторинг назначений</h3>{visibleRows.length ? <div className="learning-table-wrap"><table className="learning-table"><thead><tr><th>Сотрудник</th><th>Отдел</th><th>Курс</th><th>Прогресс</th><th>Срок</th><th>Статус</th><th>Активность</th></tr></thead><tbody>{visibleRows.map((row) => <tr key={`${row.employee_id}-${row.course_id}`}><td><button type="button" className="learning-table-link" onClick={() => setSelectedId(row.employee_id)}>{row.employee_name}</button></td><td>{row.department}</td><td>{row.course_title}</td><td>{row.progress}%</td><td>{shortDate(row.deadline)}</td><td><StatusBadge row={row} /></td><td>{row.last_activity_at ? shortDate(row.last_activity_at.slice(0, 10)) : "—"}</td></tr>)}</tbody></table></div> : <Empty icon="book" title="Назначения не найдены" text="Измените фильтры мониторинга." />}</div>}
    </>}
  </section>;
}
