"use client";

import { useId, useMemo, useState } from "react";
import { initials, roleLabel, type Profile } from "@/lib/api";
import { Icon } from "./ui";
import styles from "./jana-people.module.css";

function employeeCount(value: number) {
  const word = value % 10 === 1 && value % 100 !== 11 ? "сотрудник" : value % 10 >= 2 && value % 10 <= 4 && (value % 100 < 12 || value % 100 > 14) ? "сотрудника" : "сотрудников";
  return `${value} ${word}`;
}

function chartModel(people: Profile[], matches: Profile[]) {
  const byId = new Map(people.map(person => [person.id, person]));
  const parents = new Map(people.map(person => [person.id,
    person.manager_id !== person.id && person.manager_id !== null && byId.has(person.manager_id) ? person.manager_id : null,
  ]));
  // An incomplete hierarchy is a forest. Break malformed cycles so every
  // authorized profile remains reachable, without inventing a manager.
  const checked = new Set<number>();
  for (const person of people) {
    const path = new Set<number>();
    let id: number | null = person.id;
    while (id !== null && !checked.has(id)) {
      if (path.has(id)) { parents.set(id, null); break; }
      path.add(id);
      id = parents.get(id) ?? null;
    }
    path.forEach(value => checked.add(value));
  }
  const matching = new Set(matches.map(person => person.id));
  const visible = new Set(matching);
  const ancestors = new Set<number>();
  for (const person of matches) {
    let id = parents.get(person.id) ?? null;
    while (id !== null) {
      visible.add(id);
      ancestors.add(id);
      id = parents.get(id) ?? null;
    }
  }
  const children = new Map<number, Profile[]>();
  const roots: Profile[] = [];
  for (const person of people) {
    if (!visible.has(person.id)) continue;
    const parent = parents.get(person.id) ?? null;
    if (parent === null) roots.push(person);
    else children.set(parent, [...(children.get(parent) || []), person]);
  }
  const sort = (left: Profile, right: Profile) => Number(children.has(right.id)) - Number(children.has(left.id)) || left.full_name.localeCompare(right.full_name, "ru");
  roots.sort(sort);
  children.forEach(reports => reports.sort(sort));
  return { roots, children, matching, ancestors, count: visible.size };
}

export function OrgChart({ people, matches, filtered, meId, view, onSelect, onCalendar }: {
  people: Profile[]; matches: Profile[]; filtered: boolean; meId: number; view: "reporting" | "departments";
  onSelect: (id: number) => void; onCalendar: (id: number) => void;
}) {
  const model = useMemo(() => chartModel(people, matches), [people, matches]);
  const [expanded, setExpanded] = useState(new Map<number, boolean>());
  const [zoom, setZoom] = useState(100);
  const prefix = useId();
  const isOpen = (id: number) => expanded.get(id) ?? (filtered && model.ancestors.has(id));
  const managers = [...model.children.keys()];
  const hasOpen = managers.some(isOpen);

  function branch(person: Profile): React.ReactNode {
    const reports = model.children.get(person.id) || [];
    const hasReports = reports.length > 0;
    const open = hasReports && isOpen(person.id);
    const childrenId = `${prefix}-reports-${person.id}`;
    return <li key={person.id} className="org-chart-branch">
      <article className={`org-chart-card${open ? " is-expanded" : ""}${filtered && !model.matching.has(person.id) ? " is-context" : ""}`}>
        <button type="button" className="org-chart-person" aria-label={hasReports ? `${open ? "Скрыть" : "Показать"} подчинённых: ${person.full_name}` : `Открыть профиль: ${person.full_name}`}
          aria-expanded={hasReports ? open : undefined} aria-controls={open ? childrenId : undefined}
          onClick={() => hasReports ? setExpanded(current => new Map(current).set(person.id, !open)) : onSelect(person.id)}>
          <span className="avatar avatar-small">{initials(person.full_name)}</span>
          <span className="org-chart-identity"><strong>{person.full_name}{person.id === meId && <span className="org-chart-me"> · вы</span>}</strong><span>{person.position}</span><small>{person.department}</small></span>
          {hasReports && <span className={`org-chart-toggle${open ? " is-open" : ""}`}><Icon name="chevron" size={16} /></span>}
        </button>
        <div className="org-chart-card-footer">
          {hasReports ? <span className="org-chart-count"><Icon name="people" size={13} />{reports.length} {reports.length % 10 === 1 && reports.length % 100 !== 11 ? "подчинённый" : "подчинённых"}</span> : <span className="org-chart-role">{roleLabel[person.role]}</span>}
          <div className="org-chart-person-actions"><button type="button" className="org-chart-profile" aria-label={`Открыть календарь: ${person.full_name}`} onClick={() => onCalendar(person.id)}><Icon name="calendar" size={13} />Календарь</button><button type="button" className="org-chart-profile" aria-label={`Открыть профиль: ${person.full_name}`} onClick={() => onSelect(person.id)}>Профиль<Icon name="arrow" size={13} /></button></div>
        </div>
      </article>
      {open && <ul id={childrenId} className="org-chart-children" aria-label={`Подчинённые: ${person.full_name}`}>{reports.map(branch)}</ul>}
    </li>;
  }

  if (view === "departments") return <DepartmentStructure people={people} matches={matches} onSelect={onSelect} onCalendar={onCalendar} />;

  return <div className={`org-chart ${styles.reporting}`}>
    <div className="org-chart-toolbar">
      <div className="org-chart-heading"><span className="org-chart-heading-icon"><Icon name="people" size={21} /></span><div><h2>Структура команды</h2><p>Нажмите на руководителя, чтобы раскрыть подчинённых.</p></div></div>
      <div className="org-chart-actions"><button type="button" className="button button-secondary button-small" disabled={!managers.length || managers.every(isOpen)} onClick={() => setExpanded(new Map(managers.map(id => [id, true])))}>Развернуть всё</button><button type="button" className="button button-secondary button-small" disabled={!hasOpen} onClick={() => setExpanded(new Map(managers.map(id => [id, false])))}>Свернуть всё</button></div>
    </div>
    <div className="org-chart-viewport" role="region" aria-label="Схема подчинения сотрудников" tabIndex={0}>
      <div className="org-chart-canvas" style={{ zoom: zoom / 100 }}><ul className="org-chart-roots" aria-label="Руководители и самостоятельные сотрудники">{model.roots.map(branch)}</ul></div>
    </div>
    <div className="org-chart-footer"><p>{filtered ? "Найдены сотрудники и показаны их доступные руководители." : "Показаны сотрудники в пределах вашего доступа."}<span>В структуре: {model.count}. Счётчики учитывают доступные ветки{filtered ? " и фильтры" : ""}.</span></p>
      <div className="org-chart-zoom" role="group" aria-label="Масштаб структуры"><button type="button" className="icon-button" aria-label="Уменьшить масштаб" disabled={zoom <= 50} onClick={() => setZoom(value => value - 25)}>−</button><button type="button" className="org-chart-zoom-reset" aria-label="Сбросить масштаб" onClick={() => setZoom(100)}>{zoom}%</button><button type="button" className="icon-button" aria-label="Увеличить масштаб" disabled={zoom >= 150} onClick={() => setZoom(value => value + 25)}><Icon name="plus" size={18} /></button></div>
    </div>
  </div>;
}

function DepartmentStructure({ people, matches, onSelect, onCalendar }: {
  people: Profile[]; matches: Profile[]; onSelect: (id: number) => void; onCalendar: (id: number) => void;
}) {
  const prefix = useId();
  const [expanded, setExpanded] = useState(new Set<string>());
  const byId = useMemo(() => new Map(people.map(person => [person.id, person])), [people]);
  const departments = useMemo(() => {
    const groups = new Map<string, Profile[]>();
    for (const person of matches) groups.set(person.department, [...(groups.get(person.department) || []), person]);
    return [...groups].sort(([left], [right]) => left.localeCompare(right, "ru"))
      .map(([name, members]) => ({ name, members: members.sort((left, right) => left.full_name.localeCompare(right.full_name, "ru")) }));
  }, [matches]);
  function toggle(name: string) {
    setExpanded(current => {
      const next = new Set(current);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  }
  return <section className={styles.departments} aria-label="Подразделения сотрудников">
    <header className={styles.departmentHeader}><div><h2>Подразделения</h2><p>Группы сотрудников из доступных профилей. Линии подчинения показаны во вкладке «Подчинение».</p></div><div className={styles.departmentControls}><button type="button" disabled={departments.every(group => expanded.has(group.name))} onClick={() => setExpanded(new Set(departments.map(group => group.name)))}>Развернуть всё</button><button type="button" disabled={!expanded.size} onClick={() => setExpanded(new Set())}>Свернуть всё</button></div></header>
    <div className={styles.departmentGrid}>{departments.map((group, index) => {
      const managers = [...new Map(group.members.map(member => member.manager_id === null ? null : byId.get(member.manager_id))
        .filter((manager): manager is Profile => Boolean(manager && manager.department === group.name))
        .map(manager => [manager.id, manager])).values()];
      const open = expanded.has(group.name);
      const membersId = `${prefix}-department-${index}`;
      return <section className={styles.departmentCard} key={group.name}>
        <button type="button" className={styles.departmentToggle} aria-expanded={open} aria-controls={open ? membersId : undefined} onClick={() => toggle(group.name)}><span><strong>{group.name}</strong><small>{employeeCount(group.members.length)}</small></span><Icon name="chevron" size={18} /></button>
        {managers.length > 0 && <p className={styles.departmentManagers}>Руководители сотрудников: {managers.map(manager => manager.full_name).join(", ")}</p>}
        {open && <ul id={membersId} className={styles.departmentMembers}>{group.members.map(person => <li key={person.id}><span className={styles.avatar} aria-hidden="true">{initials(person.full_name)}</span><div><button type="button" onClick={() => onSelect(person.id)}>{person.full_name}</button><small>{person.position} · {roleLabel[person.role]}</small></div><button type="button" className={styles.departmentCalendar} aria-label={`Открыть календарь: ${person.full_name}`} onClick={() => onCalendar(person.id)}><Icon name="calendar" size={16} /></button></li>)}</ul>}
      </section>;
    })}</div>
  </section>;
}
