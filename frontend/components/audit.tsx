"use client";

import { useState } from "react";
import { ApiClient, dateTime, errorMessage, type AuditPage, type Profile } from "@/lib/api";
import { Empty, ErrorBox, Icon, Loading } from "./ui";
import { useResource } from "./use-resource";
import { PageHeading } from "./workspace";

const actions: Record<string, string> = {
  "auth.login": "Вход в систему", "request.created": "Заявка отправлена",
  "request.manager_approved": "Решение руководителя", "request.approved": "Согласование HR",
  "request.rejected": "Заявка отклонена", "request.withdrawn": "Заявка отозвана",
  "request.replaced": "Заявка заменена", "request.cancellation_requested": "Запрос отмены",
  "request.cancelled": "Отмена подтверждена", "request.cancellation_rejected": "Отмена отклонена",
  "leave.deducted": "Учёт дней", "zup.leave_registered": "Передача в 1С",
  "zup.leave_cancelled": "Возврат дней", "notification.read": "Прочтение уведомления",
  "notification.cleared": "Очистка прочитанного уведомления",
  "course.assigned": "Назначение курса", "course.progressed": "Прогресс курса", "course.completed": "Завершение курса",
  "documentolog.prepared": "Подготовка документа", "documentolog.creation_started": "Отправка документа",
  "documentolog.session_created": "Сессия подписания", "documentolog.needs_review": "Сверка документа",
  "documentolog.signing": "Ожидание подписи", "documentolog.completed": "Имитация подписи завершена",
  "documentolog.completed_reported": "Сообщение о подписи", "documentolog.declined": "Отказ подписанта",
};
export function Audit({ api, employees, onRequest, onEmployee }: { api: ApiClient; employees: Profile[]; onRequest: (id: number) => void; onEmployee: (id: number) => void }) {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ employee_id: "", actor_id: "", action: "", start_date: "", end_date: "" });
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
  const resource = useResource<AuditPage>(api, `/audit/page?${query}&page=${page}&page_size=25`);
  function change(key: keyof typeof filters, value: string) { setFilters({ ...filters, [key]: value }); setPage(1); }
  async function download() {
    setExporting(true); setError("");
    try { await api.download(`/audit/export?${query}`, "jana-audit.csv"); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setExporting(false); }
  }
  const data = resource.data;
  const peopleOptions = employees.map(person => <option key={person.id} value={person.id}>{person.full_name}</option>);
  return <><PageHeading eyebrow="КОНТРОЛЬ И ПРОЗРАЧНОСТЬ" title="Журнал аудита" description="Действия, авторы и связанные заявки. Период фильтруется по UTC." action={<button className="button button-secondary" disabled={exporting || resource.loading} onClick={download}>{exporting ? "Готовим CSV…" : "Скачать CSV"}</button>} />
    <div className="filter-grid audit-filters"><label>Сотрудник<select value={filters.employee_id} onChange={event => change("employee_id", event.target.value)}><option value="">Все сотрудники</option>{peopleOptions}</select></label><label>Автор действия<select value={filters.actor_id} onChange={event => change("actor_id", event.target.value)}><option value="">Все пользователи</option>{peopleOptions}</select></label><label>Тип события<select value={filters.action} onChange={event => change("action", event.target.value)}><option value="">Все события</option>{Object.entries(actions).map(([value, title]) => <option key={value} value={value}>{title}</option>)}</select></label><label>С даты<input type="date" value={filters.start_date} onChange={event => change("start_date", event.target.value)} /></label><label>По дату<input type="date" min={filters.start_date} value={filters.end_date} onChange={event => change("end_date", event.target.value)} /></label></div>
    {error && <ErrorBox message={error} />}<section className="panel">{resource.error ? <ErrorBox message={resource.error} retry={resource.reload} /> : resource.loading ? <Loading /> : !data?.items.length ? <Empty icon="shield" title="Событий не найдено" text="Измените период или фильтры." /> : <div className="table-scroll"><table><thead><tr><th>Событие</th><th>Автор действия</th><th>Сотрудник</th><th>Объект</th><th>Время</th></tr></thead><tbody>{data.items.map(entry => <tr key={entry.id}><td><strong>{entry.action_label}</strong><small className="cell-note">Событие №{entry.id}</small></td><td><button className="text-button" onClick={() => onEmployee(entry.actor_id)}>{entry.actor_name}</button></td><td>{entry.employee_name || "—"}</td><td>{entry.entity_type === "request" ? <button className="text-button" onClick={() => onRequest(entry.entity_id)}>Заявка №{entry.entity_id}</button> : entry.entity_type === "employee" ? <button className="text-button" onClick={() => onEmployee(entry.entity_id)}>Профиль №{entry.entity_id}</button> : `${({ course: "Курс", notification: "Уведомление" } as Record<string, string>)[entry.entity_type] || entry.entity_type} №${entry.entity_id}`}</td><td>{dateTime(entry.created_at)}</td></tr>)}</tbody></table></div>}</section>
    <div className="list-toolbar pagination"><span className="muted small-text">Событий: {data?.total ?? "—"} · Страница {page} из {Math.max(1, Math.ceil((data?.total || 0) / 25))}</span><div className="lifecycle-actions"><button className="button button-secondary button-small" disabled={page === 1 || resource.loading} onClick={() => setPage(page - 1)}>Назад</button><button className="button button-secondary button-small" disabled={!data || page * 25 >= data.total || resource.loading} onClick={() => setPage(page + 1)}>Далее</button><button className="icon-button" aria-label="Обновить журнал" onClick={resource.reload} disabled={resource.loading}><Icon name="refresh" size={17} /></button></div></div>
  </>;
}
