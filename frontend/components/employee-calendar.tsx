"use client";

import { useState } from "react";
import { date, initials, statusLabel, type Profile, type LeaveRequest } from "@/lib/api";
import { ErrorBox, Icon, Loading, Status } from "./ui";
import type { Resource } from "./use-resource";

const weekdays = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];
const activeStatuses = new Set(["submitted", "manager_approved", "approved", "cancellation_requested"]);
const monthTitle = new Intl.DateTimeFormat("ru-RU", { month: "long", year: "numeric", timeZone: "UTC" });
const fullDate = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric", weekday: "long", timeZone: "UTC" });

export function EmployeeCalendar({ employee, requests, onOpen, initialMonth, month: controlledMonth, onMonthChange }: {
  employee: Profile; requests: Resource<LeaveRequest[]>; onOpen: (id: number, month: string) => void; initialMonth?: string;
  month?: string; onMonthChange?: (month: string) => void;
}) {
  const today = new Date().toLocaleDateString("sv-SE");
  const [localMonth, setLocalMonth] = useState(() => initialMonth || today.slice(0, 7));
  const month = controlledMonth ?? localMonth;
  function setMonth(value: string) { setLocalMonth(value); onMonthChange?.(value); }
  const [history, setHistory] = useState(false);
  const [year, number] = month.split("-").map(Number);
  const first = new Date(Date.UTC(year, number - 1, 1));
  const days = new Date(Date.UTC(year, number, 0)).getUTCDate();
  const leading = (first.getUTCDay() + 6) % 7;
  const last = `${month}-${String(days).padStart(2, "0")}`;
  const items = (requests.data || []).filter(item => item.employee_id === employee.id
    && (history || activeStatuses.has(item.status)) && item.start_date <= last && item.end_date >= `${month}-01`);

  function moveMonth(offset: number) {
    const next = new Date(Date.UTC(year, number - 1 + offset, 1)).toISOString().slice(0, 7);
    if (/^[1-9]\d{3}-\d{2}$/.test(next)) setMonth(next);
  }

  return <section className="panel employee-calendar" aria-label={`Календарь сотрудника: ${employee.full_name}`}>
    <div className="employee-calendar-heading"><span className="avatar">{initials(employee.full_name)}</span><div><h2>Календарь отпусков</h2><strong>{employee.full_name}</strong><p>{employee.position} · {employee.department}</p></div></div>
    <div className="employee-calendar-toolbar"><div className="employee-calendar-navigation"><button type="button" className="icon-button calendar-previous" aria-label="Предыдущий месяц" onClick={() => moveMonth(-1)}><Icon name="chevron" size={18} /></button><label><span className="sr-only">Месяц личного календаря</span><input type="month" value={month} onChange={event => { if (/^[1-9]\d{3}-(0[1-9]|1[0-2])$/.test(event.target.value)) setMonth(event.target.value); }} /></label><button type="button" className="icon-button" aria-label="Следующий месяц" onClick={() => moveMonth(1)}><Icon name="chevron" size={18} /></button><button type="button" className="text-button" onClick={() => setMonth(today.slice(0, 7))}>Сегодня</button></div><label className="checkbox-label"><input type="checkbox" checked={history} onChange={event => setHistory(event.target.checked)} /> Показывать отклонённые, отозванные и отменённые</label></div>
    <div className="employee-calendar-legend" aria-label="Статусы отпусков"><Status value="approved" /><Status value="submitted" /><Status value="manager_approved" /><Status value="cancellation_requested" /></div>
    {requests.error && <ErrorBox message={`Не удалось обновить календарь: ${requests.error}`} retry={requests.reload} />}
    {requests.loading && !requests.data ? <Loading label="Загружаем календарь…" /> : requests.data && <>
      <table className="employee-calendar-month"><caption>{monthTitle.format(first)}</caption><thead><tr>{weekdays.map(day => <th key={day} scope="col">{day}</th>)}</tr></thead><tbody>{Array.from({ length: Math.ceil((leading + days) / 7) }, (_, week) => <tr key={week}>{weekdays.map((_, weekday) => {
        const day = week * 7 + weekday - leading + 1;
        if (day < 1 || day > days) return <td key={weekday} className="employee-calendar-empty" aria-hidden="true" />;
        const value = `${month}-${String(day).padStart(2, "0")}`;
        const entries = items.filter(item => item.start_date <= value && item.end_date >= value);
        const label = fullDate.format(new Date(`${value}T00:00:00Z`));
        return <td key={weekday} className={`${weekday > 4 ? "is-weekend" : ""}${value === today ? " is-today" : ""}`} aria-label={label}>
          <time dateTime={value} aria-current={value === today ? "date" : undefined}>{day}</time>
          {entries.map(item => <button type="button" key={item.id} className={`employee-calendar-event event-${item.status}`} title={`№${item.id} · ${statusLabel[item.status]}`} aria-label={`Отпуск №${item.id}, ${statusLabel[item.status]}, ${label}`} onClick={() => onOpen(item.id, month)}><span className="employee-calendar-event-label">Отпуск </span><span>№{item.id}</span></button>)}
        </td>;
      })}</tr>)}</tbody></table>
      <div className="employee-calendar-requests">{!items.length ? <p className="muted">В этом месяце {history ? "заявок на отпуск" : "действующих заявок на отпуск"} нет.</p> : items.map(item => <button type="button" key={item.id} className="employee-calendar-request" onClick={() => onOpen(item.id, month)} aria-label={`Открыть заявку №${item.id}`}><span><strong>Отпуск №{item.id}</strong><small>{date(item.start_date)} — {date(item.end_date)} · {item.days_count} дней к списанию</small></span><Status value={item.status} /><Icon name="chevron" size={17} /></button>)}</div>
    </>}
  </section>;
}
