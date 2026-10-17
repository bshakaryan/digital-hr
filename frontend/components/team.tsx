"use client";

import { useMemo, useState } from "react";
import { date, initials, roleLabel, statusLabel, type LeaveRequest, type Profile, type SharedCalendar } from "@/lib/api";
import { Empty, ErrorBox, Icon, Loading, Modal, Status } from "./ui";
import { PageHeading, ProfileCard } from "./workspace";
import type { Resource } from "./use-resource";
import { OrgChart } from "./org-chart";
import { EmployeeCalendar } from "./employee-calendar";

const weekdays = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];

export function TeamDirectory({ resource, requests, me, selectedId, selectedView, onSelect, onRequest }: {
  resource: Resource<Profile[]>; requests: Resource<LeaveRequest[]>; me: Profile; selectedId: number | null;
  selectedView: "profile" | "calendar"; onSelect: (id: number | null, view?: "profile" | "calendar") => void; onRequest: (id: number) => void;
}) {
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [role, setRole] = useState("");
  const [view, setView] = useState<"cards" | "structure">("cards");
  const [calendarMonths, setCalendarMonths] = useState(new Map<number, string>());
  const people = resource.data || [];
  const filtered = people.filter(person => (!department || person.department === department) && (!role || person.role === role) && `${person.full_name} ${person.email} ${person.position}`.toLocaleLowerCase("ru").includes(search.toLocaleLowerCase("ru")));
  const selected = people.find(person => person.id === selectedId);
  const manager = selected ? people.find(person => person.id === selected.manager_id) : null;
  const reports = selected ? people.filter(person => person.manager_id === selected.id && person.id !== selected.id) : [];
  function card(person: Profile) { return <div className="person-card-entry" key={person.id}><button className="person-card" onClick={() => onSelect(person.id)}><span className="avatar">{initials(person.full_name)}</span><strong>{person.full_name}{person.id === me.id && <small> · вы</small>}</strong><span>{person.position}</span><small>{person.department}</small><span className="tag">{roleLabel[person.role]}</span></button><button type="button" className="person-calendar-link" aria-label={`Открыть календарь: ${person.full_name}`} onClick={() => onSelect(person.id, "calendar")}><Icon name="calendar" size={16} />Календарь сотрудника<Icon name="chevron" size={14} /></button></div>; }
  return <><PageHeading eyebrow="ЛЮДИ JANA" title={me.role === "hr_admin" ? "Сотрудники" : "Моя команда"} description="Поиск и структура в пределах вашего доступа. Кадровые данные доступны для просмотра." />
    <div className="filter-grid"><label>Поиск<input type="search" placeholder="Имя, почта или должность" value={search} onChange={event => setSearch(event.target.value)} /></label><label>Подразделение<select value={department} onChange={event => setDepartment(event.target.value)}><option value="">Все подразделения</option>{[...new Set(people.map(person => person.department))].sort().map(value => <option key={value}>{value}</option>)}</select></label><label>Роль<select value={role} onChange={event => setRole(event.target.value)}><option value="">Все роли</option>{Object.entries(roleLabel).map(([value, title]) => <option key={value} value={value}>{title}</option>)}</select></label></div>
    <div className="list-toolbar"><div className="segmented"><button className={view === "cards" ? "selected" : ""} onClick={() => setView("cards")}>Карточки</button><button className={view === "structure" ? "selected" : ""} onClick={() => setView("structure")}>Структура</button></div><span className="muted small-text">Найдено: {filtered.length}</span></div>
    <section className="panel">{resource.error ? <ErrorBox message={resource.error} retry={resource.reload} /> : resource.loading && !resource.data ? <Loading /> : !filtered.length ? <Empty icon="people" title="Сотрудники не найдены" text="Измените запрос или фильтры." /> : view === "cards" ? <div className="team-grid">{filtered.map(card)}</div> : <OrgChart key={JSON.stringify([search, department, role])} people={people} matches={filtered} filtered={Boolean(search || department || role)} meId={me.id} onSelect={onSelect} onCalendar={id => onSelect(id, "calendar")} />}</section>
    {selected && <Modal title="Профиль сотрудника" wide onClose={() => onSelect(null)}><div className="segmented employee-profile-tabs" role="group" aria-label="Раздел профиля сотрудника"><button type="button" className={selectedView === "profile" ? "selected" : ""} aria-pressed={selectedView === "profile"} onClick={() => onSelect(selected.id, "profile")}>Профиль</button><button type="button" className={selectedView === "calendar" ? "selected" : ""} aria-pressed={selectedView === "calendar"} onClick={() => onSelect(selected.id, "calendar")}>Календарь</button></div>{selectedView === "calendar" ? <EmployeeCalendar key={selected.id} employee={selected} requests={requests} initialMonth={calendarMonths.get(selected.id)} onOpen={(id, month) => { setCalendarMonths(current => new Map(current).set(selected.id, month)); onRequest(id); }} /> : <><ProfileCard me={selected} /><div className="related-people"><h3>Связи в команде</h3><p>Руководитель: {manager ? <button className="text-button" onClick={() => onSelect(manager.id)}>{manager.full_name}</button> : selected.manager_name || "Не назначен"}</p><p>Прямых подчинённых в вашей области доступа: {reports.length}</p>{reports.map(person => <button key={person.id} className="button button-secondary button-small" onClick={() => onSelect(person.id)}>{person.full_name}<Icon name="chevron" size={15} /></button>)}</div></>}</Modal>}
  </>;
}

export function TeamCalendar({ resource, onOpen, onEmployee, month, onMonthChange }: {
  resource: Resource<SharedCalendar>; onOpen: (id: number) => void;
  onEmployee: (id: number) => void; month: string; onMonthChange: (month: string) => void;
}) {
  const [department, setDepartment] = useState("");
  const [pending, setPending] = useState(true);
  const [year, number] = month.split("-").map(Number);
  const days = new Date(Date.UTC(year, number, 0)).getUTCDate();
  // Never paint the previous month's response under a newly selected month.
  const data = resource.data?.month === month ? resource.data : null;
  const people = (data?.employees || []).filter(person => !department || person.department === department);
  const items = (data?.absences || []).filter(item => (pending || ["approved", "cancellation_requested"].includes(item.status))
    && people.some(person => person.id === item.employee_id));
  const names = new Map(data?.employees.map(person => [person.id, person.full_name]));
  const overlaps = useMemo(() => items.flatMap((left, index) => items.slice(index + 1)
    .filter(right => left.employee_id !== right.employee_id && left.start_date <= right.end_date && right.start_date <= left.end_date)
    .map(right => ({ left, right }))), [items]);
  function period(item: SharedCalendar["absences"][number]) {
    const label = `${names.get(item.employee_id)} · №${item.id}`;
    return item.can_open_request ? <button className="text-button" onClick={() => onOpen(item.id)}>{label}</button> : <span>{label}</span>;
  }
  return <>
    <div className="filter-grid"><label>Месяц<input type="month" value={month} onChange={event => { if (/^[1-9]\d{3}-(0[1-9]|1[0-2])$/.test(event.target.value)) onMonthChange(event.target.value); }} /></label><label>Подразделение<select value={department} onChange={event => setDepartment(event.target.value)}><option value="">Все подразделения</option>{[...new Set(data?.employees.map(person => person.department))].map(value => <option key={value}>{value}</option>)}</select></label><label className="checkbox-label"><input type="checkbox" checked={pending} onChange={event => setPending(event.target.checked)} /> Показывать ожидающие заявки</label></div>
    {resource.error && <ErrorBox message={`Не удалось обновить общий календарь: ${resource.error}`} retry={resource.reload} />}
    <div className="calendar-legend"><Status value="approved" /><Status value="submitted" /><Status value="manager_approved" /><Status value="cancellation_requested" /></div>
    <section className="panel table-scroll">{!data && resource.loading ? <Loading label="Загружаем общий календарь…" /> : data ? <table className="team-calendar"><caption className="sr-only">Отпуска за {month}</caption><thead><tr><th scope="col">Сотрудник</th>{Array.from({ length: days }, (_, index) => <th key={index} scope="col">{index + 1}<small>{weekdays[new Date(Date.UTC(year, number - 1, index + 1)).getUTCDay()]}</small></th>)}</tr></thead><tbody>{people.map(person => <tr key={person.id}><th scope="row">{person.can_open_profile ? <button type="button" className="team-calendar-person" aria-label={`Открыть календарь: ${person.full_name}`} onClick={() => onEmployee(person.id)}>{person.full_name}</button> : <span className="team-calendar-person">{person.full_name}</span>}<small>{person.department}</small></th>{Array.from({ length: days }, (_, index) => {
      const day = `${month}-${String(index + 1).padStart(2, "0")}`;
      const entries = items.filter(item => item.employee_id === person.id && item.start_date <= day && item.end_date >= day);
      const weekend = [0, 6].includes(new Date(`${day}T00:00:00Z`).getUTCDay());
      return <td key={day} className={weekend ? "weekend" : ""}>{entries.map(item => {
        const label = `${person.full_name}, ${date(day)}, ${statusLabel[item.status]}, заявка №${item.id}`;
        const className = `absence absence-${item.status}`;
        return item.can_open_request ? <button type="button" key={item.id} className={className} onClick={() => onOpen(item.id)} aria-label={label} title={label}>{index + 1}</button>
          : <span key={item.id} className={className} role="img" aria-label={label} title={label}>{index + 1}</span>;
      })}</td>;
    })}</tr>)}</tbody></table> : null}</section>
    {data && !items.length && <p className="muted calendar-note">В выбранном месяце заявок нет.</p>}
    {overlaps.length > 0 && <section className="panel overlap-list"><h2>Пересекающиеся периоды · {overlaps.length}</h2><p className="muted small-text">Подсказка для планирования; пересечение сотрудников само по себе не запрещает отпуск.</p>{overlaps.map(({ left, right }) => <div key={`${left.id}-${right.id}`}>{period(left)}<span> и </span>{period(right)}<small>{date(left.start_date > right.start_date ? left.start_date : right.start_date)} — {date(left.end_date < right.end_date ? left.end_date : right.end_date)}</small></div>)}</section>}
  </>;
}
