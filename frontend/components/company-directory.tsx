"use client";

import { useState } from "react";
import { initials, roleLabel, type DirectoryPerson, type LeaveRequest, type Profile } from "@/lib/api";
import { Empty, ErrorBox, Icon, Loading, Modal } from "./ui";
import { PageHeading, ProfileCard } from "./workspace";
import { OrgChart } from "./org-chart";
import { EmployeeCalendar } from "./employee-calendar";
import type { Resource } from "./use-resource";
import styles from "./jana-people.module.css";

const pageSize = 12;

export function CompanyDirectory({ directory, profiles, requests, me, selectedId, selectedView, onSelect, onRequest }: {
  directory: Resource<DirectoryPerson[]>; profiles: Resource<Profile[]>; requests: Resource<LeaveRequest[]>;
  me: Profile; selectedId: number | null; selectedView: "profile" | "calendar";
  onSelect: (id: number | null, view?: "profile" | "calendar") => void; onRequest: (id: number) => void;
}) {
  const [query, setQuery] = useState("");
  const [department, setDepartment] = useState("");
  const [role, setRole] = useState("");
  const [view, setView] = useState<"cards" | "list" | "structure">("cards");
  const [structureView, setStructureView] = useState<"reporting" | "departments">("reporting");
  const [page, setPage] = useState(1);
  const people = directory.data || [];
  const details = new Map((profiles.data || []).map(person => [person.id, person]));
  const normalized = query.toLocaleLowerCase("ru").replace(/ё/g, "е").trim();
  const filtered = people.filter(person => (!department || person.department === department)
    && (!role || details.get(person.id)?.role === role)
    && `${person.full_name} ${person.position} ${details.get(person.id)?.email || ""}`.toLocaleLowerCase("ru").replace(/ё/g, "е").includes(normalized));
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pagePeople = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const selected = people.find(person => person.id === selectedId);
  const detail = selected?.can_open_profile ? profiles.data?.find(person => person.id === selected.id) : undefined;
  const manager = selected ? people.find(person => person.id === selected.manager_id) : undefined;
  const reports = selected ? people.filter(person => person.manager_id === selected.id) : [];
  const hasFilters = Boolean(query || department || role);
  function contact(person: DirectoryPerson) {
    const profile = person.can_open_profile ? profiles.data?.find(item => item.id === person.id) : undefined;
    return <div className={styles.contactActions}>{profile?.email && /^[^\s@]+@[^\s@]+$/.test(profile.email)
      ? <a href={`mailto:${profile.email}`} aria-label={`Написать: ${person.full_name}`}><Icon name="mail" size={15} />Написать</a>
      : <span className={styles.unavailable} title="Рабочая почта не предоставлена каталогом">Почта недоступна</span>}
      <span className={styles.unavailable} title="Рабочий телефон не предоставлен">Телефон недоступен</span></div>;
  }
  function calendar(person: DirectoryPerson) {
    return person.can_open_profile && <button type="button" className={styles.calendarLink} onClick={() => onSelect(person.id, "calendar")}><Icon name="calendar" size={16} />Календарь</button>;
  }
  return <div className={styles.directory}>
    <PageHeading eyebrow="ЛЮДИ JANA" title="Сотрудники" description="Корпоративный каталог и структура подчинения." />
    <div className={styles.filters}><label>Поиск<input type="search" placeholder={me.role === "hr_admin" ? "Имя, должность или доступная почта" : "Имя или должность"} value={query} onChange={event => { setQuery(event.target.value); setPage(1); }} /></label>
      <label>Подразделение<select value={department} onChange={event => { setDepartment(event.target.value); setPage(1); }}><option value="">Все подразделения</option>{[...new Set(people.map(person => person.department))].sort().map(value => <option key={value}>{value}</option>)}</select></label>
      {me.role === "hr_admin" && <label>Роль<select value={role} onChange={event => { setRole(event.target.value); setPage(1); }}><option value="">Все роли</option>{Object.entries(roleLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}</div>
    <div className={styles.toolbar}><div className={styles.viewTabs} role="group" aria-label="Вид каталога">{(["cards", "list", "structure"] as const).map((option, index) => <button key={option} type="button" aria-pressed={view === option} className={view === option ? styles.active : ""} onClick={() => setView(option)}>{["Карточки", "Список", "Структура"][index]}</button>)}</div><span className={styles.resultCount}>{filtered.length} из {people.length} сотрудников</span></div>
    <section className={`panel ${styles.results}`} aria-label="Каталог сотрудников">
      {directory.error ? <ErrorBox message={directory.error} retry={directory.reload} /> : directory.loading && !directory.data ? <Loading /> : !filtered.length ? <Empty icon="people" title={hasFilters ? "Сотрудники не найдены" : "Каталог пока пуст"} text={hasFilters ? "Измените поиск или фильтр." : "Данные появятся после загрузки сотрудников."} />
        : view === "cards" ? <div className={styles.cardGrid}>{pagePeople.map(person => <article className={styles.personCard} key={person.id}><button type="button" className={styles.cardMain} onClick={() => onSelect(person.id)}><span className={styles.avatar} aria-hidden="true">{initials(person.full_name)}</span><span className={styles.cardIdentity}><strong>{person.full_name}{person.id === me.id && <small> · вы</small>}</strong><span>{person.position}</span><small>{person.department}</small></span>{me.role === "hr_admin" && details.get(person.id) && <span className={styles.rolePill}>{roleLabel[details.get(person.id)!.role]}</span>}</button><div className={styles.cardFooter}>{contact(person)}{calendar(person)}</div></article>)}</div>
        : view === "list" ? <div className={styles.tableScroll}><table className={styles.table}><caption className="sr-only">Сотрудники компании</caption><thead><tr><th scope="col">Сотрудник</th><th scope="col">Должность</th><th scope="col">Подразделение</th><th scope="col">Контакты</th></tr></thead><tbody>{pagePeople.map(person => <tr key={person.id}><td><button type="button" className={styles.tablePerson} onClick={() => onSelect(person.id)}><span className={styles.avatar} aria-hidden="true">{initials(person.full_name)}</span><strong>{person.full_name}{person.id === me.id && " · вы"}</strong></button></td><td>{person.position}</td><td>{person.department}</td><td><div className={styles.listActions}>{contact(person)}{calendar(person)}</div></td></tr>)}</tbody></table></div>
        : <><div className={styles.structureTabs} role="group" aria-label="Вид структуры"><button type="button" className={structureView === "reporting" ? styles.active : ""} aria-pressed={structureView === "reporting"} onClick={() => setStructureView("reporting")}>Подчинение</button><button type="button" className={structureView === "departments" ? styles.active : ""} aria-pressed={structureView === "departments"} onClick={() => setStructureView("departments")}>Подразделения</button></div><OrgChart key={`${query}-${department}-${role}`} people={people} matches={filtered} filtered={hasFilters} meId={me.id} view={structureView} onSelect={onSelect} onCalendar={id => onSelect(id, "calendar")} /></>}
    </section>
    {view !== "structure" && filtered.length > pageSize && <nav className={styles.pagination} aria-label="Страницы каталога"><span>Страница {currentPage} из {pageCount}</span><div><button type="button" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>Назад</button><button type="button" disabled={currentPage === pageCount} onClick={() => setPage(currentPage + 1)}>Далее</button></div></nav>}
    {selected && <Modal title="Карточка сотрудника" wide onClose={() => onSelect(null)}><div className={styles.profileDialog}><div className={styles.profileTop}><div><strong>{selected.full_name}</strong><span>{selected.position} · {selected.department}</span></div>{contact(selected)}</div>
      {detail && <div className="segmented employee-profile-tabs" role="group" aria-label="Раздел профиля сотрудника"><button type="button" className={selectedView === "profile" ? "selected" : ""} onClick={() => onSelect(selected.id, "profile")}>Профиль</button><button type="button" className={selectedView === "calendar" ? "selected" : ""} onClick={() => onSelect(selected.id, "calendar")}>Календарь</button></div>}
      {selectedView === "calendar" && detail ? <EmployeeCalendar key={detail.id} employee={detail} requests={requests} onOpen={onRequest} /> : <>{detail && <ProfileCard me={detail} />}<div className="related-people"><h3>Связи в команде</h3><p>Руководитель: {manager ? <button className="text-button" onClick={() => onSelect(manager.id)}>{manager.full_name}</button> : "Не назначен"}</p><p>Прямых подчинённых: {reports.length}</p>{reports.map(person => <button key={person.id} className="button button-secondary button-small" onClick={() => onSelect(person.id)}>{person.full_name}<Icon name="chevron" size={15} /></button>)}</div></>}</div></Modal>}
  </div>;
}
