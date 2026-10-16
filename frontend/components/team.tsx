"use client";

import { useMemo, useState } from "react";
import { date, initials, roleLabel, statusLabel, type LeaveRequest, type Profile } from "@/lib/api";
import { Empty, ErrorBox, Icon, Loading, Modal, Status } from "./ui";
import { PageHeading, ProfileCard } from "./workspace";
import type { Resource } from "./use-resource";

export function TeamDirectory({ resource, me, selectedId, onSelect }: { resource: Resource<Profile[]>; me: Profile; selectedId: number | null; onSelect: (id: number | null) => void }) {
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [role, setRole] = useState("");
  const [view, setView] = useState<"cards" | "structure">("cards");
  const people = resource.data || [];
  const filtered = people.filter(person => (!department || person.department === department) && (!role || person.role === role) && `${person.full_name} ${person.email} ${person.position}`.toLocaleLowerCase("ru").includes(search.toLocaleLowerCase("ru")));
  const selected = people.find(person => person.id === selectedId);
  const manager = selected ? people.find(person => person.id === selected.manager_id) : null;
  const reports = selected ? people.filter(person => person.manager_id === selected.id && person.id !== selected.id) : [];
  function card(person: Profile) { return <button className="person-card" key={person.id} onClick={() => onSelect(person.id)}><span className="avatar">{initials(person.full_name)}</span><strong>{person.full_name}{person.id === me.id && <small> · вы</small>}</strong><span>{person.position}</span><small>{person.department}</small><span className="tag">{roleLabel[person.role]}</span></button>; }
  function branch(person: Profile, visited = new Set<number>()): React.ReactNode {
    const next = new Set(visited).add(person.id);
    const children = filtered.filter(child => child.manager_id === person.id && !next.has(child.id));
    return <li key={person.id}><button className="org-person" onClick={() => onSelect(person.id)}><span className="avatar avatar-small">{initials(person.full_name)}</span><span><strong>{person.full_name}</strong><small>{person.position} · {person.department}</small></span><span className="tag">{roleLabel[person.role]}</span></button>{children.length > 0 && <ul>{children.map(child => branch(child, next))}</ul>}</li>;
  }
  const roots = filtered.filter(person => !filtered.some(parent => parent.id === person.manager_id) || person.manager_id === person.id);
  return <><PageHeading eyebrow="ЛЮДИ JANA" title={me.role === "hr_admin" ? "Сотрудники" : "Моя команда"} description="Поиск и структура в пределах вашего доступа. Кадровые данные доступны для просмотра." />
    <div className="filter-grid"><label>Поиск<input type="search" placeholder="Имя, почта или должность" value={search} onChange={event => setSearch(event.target.value)} /></label><label>Подразделение<select value={department} onChange={event => setDepartment(event.target.value)}><option value="">Все подразделения</option>{[...new Set(people.map(person => person.department))].sort().map(value => <option key={value}>{value}</option>)}</select></label><label>Роль<select value={role} onChange={event => setRole(event.target.value)}><option value="">Все роли</option>{Object.entries(roleLabel).map(([value, title]) => <option key={value} value={value}>{title}</option>)}</select></label></div>
    <div className="list-toolbar"><div className="segmented"><button className={view === "cards" ? "selected" : ""} onClick={() => setView("cards")}>Карточки</button><button className={view === "structure" ? "selected" : ""} onClick={() => setView("structure")}>Структура</button></div><span className="muted small-text">Найдено: {filtered.length}</span></div>
    <section className="panel">{resource.error ? <ErrorBox message={resource.error} retry={resource.reload} /> : resource.loading && !resource.data ? <Loading /> : !filtered.length ? <Empty icon="people" title="Сотрудники не найдены" text="Измените запрос или фильтры." /> : view === "cards" ? <div className="team-grid">{filtered.map(card)}</div> : <div className="org-tree"><p className="muted small-text">Показаны только доступные профили; отсутствие узла не означает отсутствие руководителя в компании.</p><ul>{(roots.length ? roots : filtered).map(person => branch(person))}</ul></div>}</section>
    {selected && <Modal title="Профиль сотрудника" wide onClose={() => onSelect(null)}><ProfileCard me={selected} /><div className="related-people"><h3>Связи в команде</h3><p>Руководитель: {manager ? <button className="text-button" onClick={() => onSelect(manager.id)}>{manager.full_name}</button> : selected.manager_name || "Не назначен"}</p><p>Прямых подчинённых в вашей области доступа: {reports.length}</p>{reports.map(person => <button key={person.id} className="button button-secondary button-small" onClick={() => onSelect(person.id)}>{person.full_name}<Icon name="chevron" size={15} /></button>)}</div></Modal>}
  </>;
}

export function TeamCalendar({ requests, employees, onOpen }: { requests: Resource<LeaveRequest[]>; employees: Resource<Profile[]>; onOpen: (id: number) => void }) {
  const [month, setMonth] = useState(() => new Date().toLocaleDateString("sv-SE").slice(0, 7));
  const [department, setDepartment] = useState("");
  const [pending, setPending] = useState(true);
  const safeMonth = /^\d{4}-\d{2}$/.test(month) ? month : new Date().toISOString().slice(0, 7);
  const [year, number] = safeMonth.split("-").map(Number);
  const days = new Date(Date.UTC(year, number, 0)).getUTCDate();
  const start = `${safeMonth}-01`, end = `${safeMonth}-${days}`;
  const people = (employees.data || []).filter(person => !department || person.department === department);
  const items = (requests.data || []).filter(item => ["approved", "cancellation_requested", ...(pending ? ["submitted", "manager_approved"] : [])].includes(item.status) && item.start_date <= end && item.end_date >= start && people.some(person => person.id === item.employee_id));
  const overlaps = useMemo(() => items.flatMap((left, index) => items.slice(index + 1).filter(right => left.employee_id !== right.employee_id && left.start_date <= right.end_date && right.start_date <= left.end_date).map(right => ({ left, right }))), [items]);
  return <><PageHeading eyebrow="ПЛАНИРОВАНИЕ" title="Календарь команды" description="Отсутствия и пересечения периодов. Решение по каждой заявке принимает согласующий." />
    <div className="filter-grid"><label>Месяц<input type="month" min="2026-01" max="2028-12" value={month} onChange={event => setMonth(event.target.value)} /></label><label>Подразделение<select value={department} onChange={event => setDepartment(event.target.value)}><option value="">Все доступные</option>{[...new Set(employees.data?.map(person => person.department))].map(value => <option key={value}>{value}</option>)}</select></label><label className="checkbox-label"><input type="checkbox" checked={pending} onChange={event => setPending(event.target.checked)} /> Показывать ожидающие заявки</label></div>
    {requests.error && <ErrorBox message={requests.error} retry={requests.reload} />}{employees.error && <ErrorBox message={employees.error} retry={employees.reload} />}
    <div className="calendar-legend"><Status value="approved" /><Status value="submitted" /><Status value="manager_approved" /><Status value="cancellation_requested" /></div>
    <section className="panel table-scroll">{requests.loading && !requests.data ? <Loading /> : <table className="team-calendar"><caption className="sr-only">Отпуска за {safeMonth}</caption><thead><tr><th>Сотрудник</th>{Array.from({ length: days }, (_, index) => <th key={index}>{index + 1}</th>)}</tr></thead><tbody>{people.map(person => <tr key={person.id}><th scope="row">{person.full_name}<small>{person.department}</small></th>{Array.from({ length: days }, (_, index) => {
      const day = `${safeMonth}-${String(index + 1).padStart(2, "0")}`;
      const item = items.find(item => item.employee_id === person.id && item.start_date <= day && item.end_date >= day);
      const weekend = [0, 6].includes(new Date(`${day}T00:00:00Z`).getUTCDay());
      return <td key={day} className={weekend ? "weekend" : ""}>{item && <button className={`absence absence-${item.status}`} onClick={() => onOpen(item.id)} aria-label={`${person.full_name}, ${date(day)}, ${statusLabel[item.status]}, заявка №${item.id}`} title={`${person.full_name} · №${item.id} · ${statusLabel[item.status]}`}>{index + 1}</button>}</td>;
    })}</tr>)}</tbody></table>}</section>
    {!items.length && <p className="muted calendar-note">В выбранном месяце заявок нет.</p>}
    {overlaps.length > 0 && <section className="panel overlap-list"><h2>Пересекающиеся периоды · {overlaps.length}</h2><p className="muted small-text">Подсказка для планирования; пересечение сотрудников само по себе не запрещает отпуск.</p>{overlaps.map(({ left, right }) => <div key={`${left.id}-${right.id}`}><button className="text-button" onClick={() => onOpen(left.id)}>{left.employee_name} · №{left.id}</button><span> и </span><button className="text-button" onClick={() => onOpen(right.id)}>{right.employee_name} · №{right.id}</button><small>{date(left.start_date > right.start_date ? left.start_date : right.start_date)} — {date(left.end_date < right.end_date ? left.end_date : right.end_date)}</small></div>)}</section>}
  </>;
}
