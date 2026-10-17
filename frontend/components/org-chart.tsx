"use client";

import { useId, useMemo, useState } from "react";
import { initials, roleLabel, type Profile } from "@/lib/api";
import { Icon } from "./ui";

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

export function OrgChart({ people, matches, filtered, meId, onSelect, onCalendar }: {
  people: Profile[]; matches: Profile[]; filtered: boolean; meId: number; onSelect: (id: number) => void; onCalendar: (id: number) => void;
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

  return <div className="org-chart">
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
