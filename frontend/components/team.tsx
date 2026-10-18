"use client";

import { useMemo, useState } from "react";
import { date, initials, roleLabel, statusLabel, type LeaveRequest, type Profile, type SharedCalendar } from "@/lib/api";
import { Empty, ErrorBox, Icon, Loading, Modal, Status } from "./ui";
import { PageHeading, ProfileCard } from "./workspace";
import type { Resource } from "./use-resource";
import { OrgChart } from "./org-chart";
import { EmployeeCalendar } from "./employee-calendar";
import styles from "./jana-people.module.css";

const weekdays = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];
const pageSize = 12;

function ContactActions({ person }: { person: Profile }) {
  const email = person.email.trim();
  const hasEmail = /^[^\s@]+@[^\s@]+$/.test(email);
  return <div className={styles.contactActions}>
    {hasEmail ? <a href={`mailto:${email}`} aria-label={`Написать на рабочую почту: ${person.full_name}`}><Icon name="mail" size={15} />Написать</a>
      : <span className={styles.unavailable} title="Рабочая почта недоступна">Почта недоступна</span>}
    <span className={styles.unavailable} title="Рабочий телефон отсутствует в доступном профиле">Телефон недоступен</span>
  </div>;
}

export function TeamDirectory({ resource, requests, me, selectedId, selectedView, onSelect, onRequest }: {
  resource: Resource<Profile[]>; requests: Resource<LeaveRequest[]>; me: Profile; selectedId: number | null;
  selectedView: "profile" | "calendar"; onSelect: (id: number | null, view?: "profile" | "calendar") => void; onRequest: (id: number) => void;
}) {
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [role, setRole] = useState("");
  const [view, setView] = useState<"cards" | "list" | "structure">("cards");
  const [structureView, setStructureView] = useState<"reporting" | "departments">("reporting");
  const [page, setPage] = useState(1);
  const [calendarMonths, setCalendarMonths] = useState(new Map<number, string>());
  const people = resource.data || [];
  const query = search.toLocaleLowerCase("ru").replace(/ё/g, "е").trim();
  const filtered = people.filter(person => (!department || person.department === department) && (!role || person.role === role)
    && `${person.full_name} ${person.email} ${person.position}`.toLocaleLowerCase("ru").replace(/ё/g, "е").includes(query));
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pagePeople = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const selected = people.find(person => person.id === selectedId);
  const manager = selected ? people.find(person => person.id === selected.manager_id) : null;
  const reports = selected ? people.filter(person => person.manager_id === selected.id && person.id !== selected.id) : [];
  const hasFilters = Boolean(search || department || role);
  function card(person: Profile) { return <article className={styles.personCard} key={person.id}>
    <button type="button" className={styles.cardMain} onClick={() => onSelect(person.id)} aria-label={`Открыть профиль: ${person.full_name}`}>
      <span className={styles.avatar} aria-hidden="true">{initials(person.full_name)}</span>
      <span className={styles.cardIdentity}><strong>{person.full_name}{person.id === me.id && <small> · вы</small>}</strong><span>{person.position}</span><small>{person.department}</small></span>
      <span className={styles.rolePill}>{roleLabel[person.role]}</span>
    </button>
    <div className={styles.cardFooter}><ContactActions person={person} /><button type="button" className={styles.calendarLink} onClick={() => onSelect(person.id, "calendar")} aria-label={`Открыть календарь: ${person.full_name}`}><Icon name="calendar" size={16} />Календарь</button></div>
  </article>; }
  return <div className={styles.directory}><PageHeading eyebrow="ЛЮДИ JANA" title={me.role === "hr_admin" ? "Сотрудники" : "Моя команда"} description="Профили и структура сотрудников в пределах вашего доступа." />
    <div className={styles.filters}><label>Поиск<input type="search" placeholder="Имя, должность или рабочая почта" value={search} onChange={event => { setSearch(event.target.value); setPage(1); }} /></label><label>Подразделение<select value={department} onChange={event => { setDepartment(event.target.value); setPage(1); }}><option value="">Все подразделения</option>{[...new Set(people.map(person => person.department))].sort().map(value => <option key={value}>{value}</option>)}</select></label><label>Роль<select value={role} onChange={event => { setRole(event.target.value); setPage(1); }}><option value="">Все роли</option>{Object.entries(roleLabel).map(([value, title]) => <option key={value} value={value}>{title}</option>)}</select></label></div>
    <div className={styles.toolbar}><div className={styles.viewTabs} role="group" aria-label="Вид каталога"><button type="button" aria-pressed={view === "cards"} className={view === "cards" ? styles.active : ""} onClick={() => setView("cards")}>Карточки</button><button type="button" aria-pressed={view === "list"} className={view === "list" ? styles.active : ""} onClick={() => setView("list")}>Список</button><button type="button" aria-pressed={view === "structure"} className={view === "structure" ? styles.active : ""} onClick={() => setView("structure")}>Структура</button></div><span className={styles.resultCount}>{filtered.length} из {people.length} сотрудников</span></div>
    <section className={`panel ${styles.results}`} aria-label="Каталог сотрудников">
      {resource.error ? <ErrorBox message={resource.error} retry={resource.reload} /> : resource.loading && !resource.data ? <Loading /> : !filtered.length ? <Empty icon="people" title={hasFilters ? "Сотрудники не найдены" : "Доступных сотрудников пока нет"} text={hasFilters ? "Измените поиск или фильтры." : "Каталог появится после загрузки разрешённых профилей."} /> : view === "cards" ? <div className={styles.cardGrid}>{pagePeople.map(card)}</div> : view === "list" ? <div className={styles.tableScroll}><table className={styles.table}><caption className="sr-only">Сотрудники в пределах вашего доступа</caption><thead><tr><th scope="col">Сотрудник</th><th scope="col">Должность</th><th scope="col">Подразделение</th><th scope="col">Роль</th><th scope="col">Контакты и календарь</th></tr></thead><tbody>{pagePeople.map(person => <tr key={person.id}><td><button type="button" className={styles.tablePerson} onClick={() => onSelect(person.id)}><span className={styles.avatar} aria-hidden="true">{initials(person.full_name)}</span><span><strong>{person.full_name}{person.id === me.id && " · вы"}</strong><small>{person.email}</small></span></button></td><td>{person.position}</td><td>{person.department}</td><td><span className={styles.rolePill}>{roleLabel[person.role]}</span></td><td><div className={styles.listActions}><ContactActions person={person} /><button type="button" className={styles.calendarLink} onClick={() => onSelect(person.id, "calendar")} aria-label={`Открыть календарь: ${person.full_name}`}><Icon name="calendar" size={16} />Календарь</button></div></td></tr>)}</tbody></table></div> : <><div className={styles.structureTabs} role="group" aria-label="Вид структуры"><button type="button" aria-pressed={structureView === "reporting"} className={structureView === "reporting" ? styles.active : ""} onClick={() => setStructureView("reporting")}>Подчинение</button><button type="button" aria-pressed={structureView === "departments"} className={structureView === "departments" ? styles.active : ""} onClick={() => setStructureView("departments")}>Подразделения</button></div><OrgChart key={JSON.stringify([search, department, role])} people={people} matches={filtered} filtered={hasFilters} meId={me.id} view={structureView} onSelect={onSelect} onCalendar={id => onSelect(id, "calendar")} /></>}
    </section>
    {view !== "structure" && filtered.length > pageSize && !resource.error && <nav className={styles.pagination} aria-label="Страницы каталога"><span>Страница {currentPage} из {pageCount}</span><div><button type="button" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>Назад</button><button type="button" disabled={currentPage === pageCount} onClick={() => setPage(currentPage + 1)}>Далее</button></div></nav>}
    {selected && <Modal title="Профиль сотрудника" wide onClose={() => onSelect(null)}><div className={styles.profileDialog}><div className={styles.profileTop}><div><strong>{selected.full_name}</strong><span>{selected.position} · {selected.department}</span></div><ContactActions person={selected} /></div><div className="segmented employee-profile-tabs" role="group" aria-label="Раздел профиля сотрудника"><button type="button" className={selectedView === "profile" ? "selected" : ""} aria-pressed={selectedView === "profile"} onClick={() => onSelect(selected.id, "profile")}>Профиль</button><button type="button" className={selectedView === "calendar" ? "selected" : ""} aria-pressed={selectedView === "calendar"} onClick={() => onSelect(selected.id, "calendar")}>Календарь</button></div>{selectedView === "calendar" ? <EmployeeCalendar key={selected.id} employee={selected} requests={requests} initialMonth={calendarMonths.get(selected.id)} onOpen={(id, month) => { setCalendarMonths(current => new Map(current).set(selected.id, month)); onRequest(id); }} /> : <><ProfileCard me={selected} /><div className="related-people"><h3>Связи в команде</h3><p>Руководитель: {manager ? <button className="text-button" onClick={() => onSelect(manager.id)}>{manager.full_name}</button> : selected.manager_name || "Не назначен"}</p><p>Прямых подчинённых в вашей области доступа: {reports.length}</p>{reports.map(person => <button key={person.id} className="button button-secondary button-small" onClick={() => onSelect(person.id)}>{person.full_name}<Icon name="chevron" size={15} /></button>)}</div></>}</div></Modal>}
  </div>;
}

export function TeamCalendar({ resource, onOpen, onEmployee, month, onMonthChange }: {
  resource: Resource<SharedCalendar>; onOpen: (id: number) => void;
  onEmployee: (id: number) => void; month: string; onMonthChange: (month: string) => void;
}) {
  const [department, setDepartment] = useState("");
  const [pending, setPending] = useState(true);
  const [year, number] = month.split("-").map(Number);
  const days = new Date(Date.UTC(year, number, 0)).getUTCDate();
  const monthLabel = new Intl.DateTimeFormat("ru-RU", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${month}-01T00:00:00Z`));
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
    <section className="panel team-calendar-window" aria-labelledby="team-calendar-title">
      <header className="team-calendar-toolbar"><div><h2 id="team-calendar-title">Отпуска · {monthLabel}</h2><p id="team-calendar-scroll-hint">Прокручивайте календарь внутри окна ↔ ↕</p></div>{data && <span className="team-calendar-count">Сотрудников: {people.length}</span>}</header>
      <div className="team-calendar-viewport" role="region" aria-label="Общий календарь отпусков с прокруткой" aria-describedby="team-calendar-scroll-hint" tabIndex={data && people.length ? 0 : undefined}>
      {!data && resource.loading ? <Loading label="Загружаем общий календарь…" /> : data && !people.length ? <Empty icon="people" title="Сотрудники не найдены" text="Попробуйте выбрать другое подразделение." /> : data ? <table className="team-calendar"><caption className="sr-only">Отпуска за {month}</caption><thead><tr><th scope="col">Сотрудник</th>{Array.from({ length: days }, (_, index) => <th key={index} scope="col">{index + 1}<small>{weekdays[new Date(Date.UTC(year, number - 1, index + 1)).getUTCDay()]}</small></th>)}</tr></thead><tbody>{people.map(person => <tr key={person.id}><th scope="row">{person.can_open_profile ? <button type="button" className="team-calendar-person" aria-label={`Открыть календарь: ${person.full_name}`} onClick={() => onEmployee(person.id)}>{person.full_name}</button> : <span className="team-calendar-person">{person.full_name}</span>}<small>{person.department}</small></th>{Array.from({ length: days }, (_, index) => {
      const day = `${month}-${String(index + 1).padStart(2, "0")}`;
      const entries = items.filter(item => item.employee_id === person.id && item.start_date <= day && item.end_date >= day);
      const weekend = [0, 6].includes(new Date(`${day}T00:00:00Z`).getUTCDay());
      return <td key={day} className={weekend ? "weekend" : ""}>{entries.map(item => {
        const label = `${person.full_name}, ${date(day)}, ${statusLabel[item.status]}, заявка №${item.id}`;
        const className = `absence absence-${item.status}`;
        return item.can_open_request ? <button type="button" key={item.id} className={className} onClick={() => onOpen(item.id)} aria-label={label} title={label}>{index + 1}</button>
          : <span key={item.id} className={className} role="img" aria-label={label} title={label}>{index + 1}</span>;
      })}</td>;
    })}</tr>)}</tbody></table> : null}</div></section>
    {data && !items.length && <p className="muted calendar-note">В выбранном месяце заявок нет.</p>}
    {overlaps.length > 0 && <section className="panel overlap-list"><h2>Пересекающиеся периоды · {overlaps.length}</h2><p className="muted small-text">Подсказка для планирования; пересечение сотрудников само по себе не запрещает отпуск.</p>{overlaps.map(({ left, right }) => <div key={`${left.id}-${right.id}`}>{period(left)}<span> и </span>{period(right)}<small>{date(left.start_date > right.start_date ? left.start_date : right.start_date)} — {date(left.end_date < right.end_date ? left.end_date : right.end_date)}</small></div>)}</section>}
  </>;
}
