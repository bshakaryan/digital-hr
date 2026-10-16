"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiClient, ApiError, date, dateTime, errorMessage, initials, statusLabel, type LeaveRequest, type Profile, type RequestStatus } from "@/lib/api";
import { Empty, ErrorBox, Icon, Loading, Modal, Status } from "./ui";
import { useResource, type Resource } from "./use-resource";
import { canReview, PageHeading } from "./workspace";
import { DocumentologDocument } from "./documentolog";
import { RequestLifecycle } from "./request-lifecycle";

export function Requests({ me, employees, resource, onCreate, onOpen }: {
  me: Profile; employees: Profile[] | null; resource: Resource<LeaveRequest[]>; onCreate: () => void; onOpen: (id: number) => void;
}) {
  const [scope, setScope] = useState<"own" | "team" | "review">(me.role === "employee" ? "own" : "review");
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const items = resource.data?.filter((item) => (scope === "own" ? item.employee_id === me.id : scope === "review" ? item.can_review : item.employee_id !== me.id) && (filter === "all" || item.status === filter) && (!from || item.end_date >= from) && (!to || item.start_date <= to) && `${item.id} ${item.employee_name}`.toLocaleLowerCase("ru").includes(search.toLocaleLowerCase("ru"))).sort((a, b) => scope === "review" ? stageTime(a).localeCompare(stageTime(b)) : b.id - a.id);
  const reviewCount = resource.data?.filter(item => item.can_review).length || 0;
  return <><PageHeading eyebrow="КАДРОВЫЕ СЕРВИСЫ" title="Заявки" action={<button className="button button-primary" onClick={onCreate}><Icon name="plus" size={18} /> Новая заявка</button>} />
    <div className="list-toolbar"><div className="segmented">{me.role !== "employee" && <button className={scope === "review" ? "selected" : ""} onClick={() => { setScope("review"); setFilter("all"); }}>Требуют моего решения · {reviewCount}</button>}<button className={scope === "own" ? "selected" : ""} onClick={() => setScope("own")}>Мои заявки</button>{me.role !== "employee" && <button className={scope === "team" ? "selected" : ""} onClick={() => setScope("team")}>Заявки команды</button>}</div><button className="icon-button" onClick={resource.reload} disabled={resource.loading} aria-label="Обновить заявки"><Icon name="refresh" size={18} /></button></div>
    <div className="filter-grid"><label>Поиск заявки<input type="search" placeholder="Номер или сотрудник" value={search} onChange={event => setSearch(event.target.value)} /></label><label>Статус заявки<select value={filter} onChange={event => setFilter(event.target.value)}><option value="all">Все статусы</option>{Object.entries(statusLabel).map(([value, title]) => <option key={value} value={value}>{title}</option>)}</select></label><label>Период с<input type="date" value={from} onChange={event => setFrom(event.target.value)} /></label><label>Период по<input type="date" min={from} value={to} onChange={event => setTo(event.target.value)} /></label></div>
    {scope === "review" && <p className="queue-hint">Сначала показаны заявки, которые дольше ждут вашего решения. Права и актуальный этап проверяются сервером.</p>}
    <section className="panel">{resource.error ? <ErrorBox message={resource.error} retry={resource.reload} /> : resource.loading && !resource.data ? <Loading /> : !items?.length ? <Empty title={scope === "review" ? "Нет заявок для вашего решения" : "Здесь пока нет заявок"} text={filter !== "all" || search || from || to ? "Измените фильтры поиска." : scope === "own" ? "Создайте заявку, чтобы спланировать отпуск." : "Новые задачи появятся после перехода на ваш этап."} action={scope === "own" && filter === "all" ? <button className="button button-secondary" onClick={onCreate}>Создать заявку <Icon name="plus" size={16} /></button> : undefined} /> : <div className="table-scroll"><table className="requests-table"><thead><tr><th>Заявка</th>{scope !== "own" && <th>Сотрудник</th>}<th>Период отпуска</th><th>Статус</th>{scope === "review" && <th>Ожидание на этапе</th>}<th><span className="sr-only">Действие</span></th></tr></thead><tbody>{items.map((request) => <tr key={request.id}><td><button className="request-title-link" onClick={() => onOpen(request.id)}><span className="request-type-icon"><Icon name="calendar" size={19} /></span><span><strong>Ежегодный отпуск</strong><small>№{request.id} · {request.calendar_days} календарных дней</small><small>{request.days_count} дней к списанию</small></span></button></td>{scope !== "own" && <td><div className="table-person"><span className="avatar avatar-mini">{initials(request.employee_name)}</span>{request.employee_name}</div></td>}<td className="period-cell">{date(request.start_date)}<br /><span>по {date(request.end_date)}</span></td><td><Status value={request.status} /></td>{scope === "review" && <td><strong>{waiting(request)}</strong><small className="cell-note">с {dateTime(stageTime(request))}</small></td>}<td><button className="text-button" onClick={() => onOpen(request.id)}>{canReview(me, request, employees) ? "Рассмотреть" : "Подробнее"}<Icon name="chevron" size={15} /></button></td></tr>)}</tbody></table></div>}</section>
    <div className="inline-disclaimer"><Icon name="info" size={16} /><p>Считаются календарные дни без праздничных дат Казахстана. Остаток списывается только после финального одобрения HR; заявки в ожидании его не резервируют.</p></div>
  </>;
}

export function RequestDetail({ id, api, me, employees, onClose, onChanged, notify, onReplace }: {
  id: number; api: ApiClient; me: Profile; employees: Profile[] | null; onClose: () => void; onChanged: () => void; notify: (message: string) => void; onReplace: (item: LeaveRequest) => void;
}) {
  const resource = useResource<LeaveRequest>(api, `/requests/${id}`);
  const [decision, setDecision] = useState<"approved" | "rejected">("approved");
  const [comment, setComment] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const busy = useRef(false);
  const cancellationKey = useRef<string | null>(null);
  const item = resource.data;
  useEffect(() => {
    const timer = setInterval(() => { if (document.visibilityState === "visible" && !busy.current) resource.reload(); }, 30000);
    return () => clearInterval(timer);
  }, [resource.reload]);
  async function retrySync() {
    if (busy.current) return;
    busy.current = true; setPending(true); setError("");
    try {
      const updated = await api.post<LeaveRequest>(`/requests/${id}/sync`, {});
      resource.reload(); onChanged();
      notify(updated.zup_sync_status === "synced" ? "Передача в 1С:ЗУП подтверждена" : "Передача пока не подтверждена; автоматический повтор сохранён");
    } catch (cause) { setError(errorMessage(cause)); }
    finally { busy.current = false; setPending(false); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!item || busy.current) return;
    busy.current = true; setPending(true); setError("");
    try {
      if (!cancellationKey.current) cancellationKey.current = crypto.randomUUID();
      const body = { status: decision, version: item.version, comment };
      const updated = item.status === "cancellation_requested" ? await api.post<LeaveRequest>(`/requests/${id}/cancellation-decision`, body, { "Idempotency-Key": cancellationKey.current }) : await api.patch<LeaveRequest>(`/requests/${id}/status`, body);
      cancellationKey.current = null;
      resource.reload(); onChanged(); setComment(""); notify(item.status === "cancellation_requested" ? (decision === "approved" ? "Отмена подтверждена" : "Отмена отклонена") : updated.status === "manager_approved" ? `Заявка №${id} передана в HR` : decision === "approved" ? `Заявка №${id} согласована` : `Заявка №${id} отклонена`);
    } catch (cause) {
      setError(errorMessage(cause));
      cancellationKey.current = null;
      // Refresh after any uncertain outcome, especially a stale-version conflict.
      if (!(cause instanceof ApiError) || cause.status === 0 || cause.status === 409 || cause.status >= 500) { resource.reload(); onChanged(); }
    } finally { busy.current = false; setPending(false); }
  }
  return <Modal title={`Заявка №${id}`} wide onClose={() => { if (!pending) onClose(); }}>
    {resource.error && <ErrorBox message={resource.error} retry={resource.reload} />}
    {resource.loading && !item ? <Loading /> : item && <><div className="request-detail-heading"><div><span className="eyebrow">ЕЖЕГОДНЫЙ ОТПУСК · {item.calendar_days} КАЛЕНДАРНЫХ ДНЕЙ · {item.days_count} К СПИСАНИЮ</span><h3>{item.employee_name}</h3></div><Status value={item.status} /></div><dl className="request-detail-dates"><div><dt>Начало отпуска</dt><dd>{date(item.start_date, true)}</dd></div><Icon name="arrow" /><div><dt>Окончание отпуска</dt><dd>{date(item.end_date, true)}</dd></div></dl><div className="request-comment"><span className="small-label">КОММЕНТАРИЙ СОТРУДНИКА</span><p>{item.comment || "Без комментария"}</p></div><section className="history"><h3>История заявки</h3><ol>{item.history.map((entry, index) => <li key={`${entry.created_at}-${index}`}><span className={`history-dot ${entry.status}`} /><div><div className="history-top"><strong>{historyTitle(entry.status, item.history[index - 1]?.status)}</strong><time dateTime={entry.created_at}>{dateTime(entry.created_at)}</time></div><span>{entry.actor_name}</span>{entry.comment && <p>{entry.comment}</p>}</div></li>)}</ol></section>
    {error && <ErrorBox message={error} />}
    <div className="notice"><Icon name="calendar" /><span>Списываемые дни: <strong>{item.days_count}</strong>.{item.calendar_version === "legacy-deducted" ? " Историческое списание по прежнему правилу; новый календарь к нему не применяется." : <>{item.excluded_dates.length > 0 ? <> Исключены праздники: {item.excluded_dates.map((day) => date(day)).join(", ")}.</> : " Праздничных дат в периоде нет."} Обычные и перенесённые выходные учитываются.</>}</span></div>
    {item.status === "approved" && <div className={`notice ${item.zup_sync_status === "error" ? "warning" : ""}`}><Icon name="info" /><span>{item.zup_sync_status === "synced" ? <>Передано в 1С:ЗУП. Документ: <strong>{item.zup_reference}</strong>.</> : item.zup_sync_status === "legacy" ? "Историческая заявка: автоматическая передача в 1С не выполняется." : <>HR одобрил заявку; дни учтены локально. Передача в 1С:ЗУП {item.zup_sync_status === "error" ? "ожидает повтора" : "в очереди"}. Повтор не спишет дни ещё раз.</>}{me.role === "hr_admin" && (item.zup_sync_status === "pending" || item.zup_sync_status === "error") && <button className="text-button" onClick={retrySync} disabled={pending}>Повторить передачу</button>}</span></div>}
    {canReview(me, item, employees) && <form className="decision-form stack-form" onSubmit={submit}><h3>{item.status === "cancellation_requested" ? "Решение HR об отмене" : item.status === "submitted" ? "Решение руководителя" : "Финальное решение HR"}</h3><p>{item.status === "cancellation_requested" ? `Подтвердите отмену всего периода. ${item.days_count} дней вернутся после подтверждения 1С.` : item.status === "submitted" ? "После согласования заявка будет передана HR. Остаток пока не изменится." : `При согласовании спишется ${item.days_count} дней без праздничных дат. Сервер повторно проверит доступный остаток.`}</p><fieldset disabled={pending || resource.loading || !!resource.error} className="decision-options"><legend className="sr-only">Решение</legend><label className={decision === "approved" ? "decision-selected approve" : ""}><input type="radio" name="decision" value="approved" checked={decision === "approved"} onChange={() => setDecision("approved")} /><Icon name="check" size={17} /> {item.status === "cancellation_requested" ? "Подтвердить отмену" : "Согласовать"}</label><label className={decision === "rejected" ? "decision-selected reject" : ""}><input type="radio" name="decision" value="rejected" checked={decision === "rejected"} onChange={() => setDecision("rejected")} /><Icon name="close" size={17} /> {item.status === "cancellation_requested" ? "Сохранить отпуск" : "Отклонить"}</label></fieldset><label>Комментарий к решению {item.status !== "cancellation_requested" && <span className="optional">· необязательно</span>}<textarea required={item.status === "cancellation_requested"} maxLength={2000} value={comment} onChange={(event) => setComment(event.target.value)} rows={3} placeholder="Поясните ваше решение сотруднику" disabled={pending} /></label><div className="form-actions"><span className="muted small-text">Решение сохранится от вашего имени</span><button className={`button ${decision === "approved" ? "button-primary" : "button-danger"}`} disabled={pending || resource.loading || !!resource.error}>{pending ? "Сохраняем…" : "Подтвердить решение"}<Icon name="check" size={17} /></button></div></form>}
    {item.employee_id === me.id && item.status === "submitted" && <div className="notice"><Icon name="clock" /><span>Заявка ожидает решения непосредственного руководителя. Согласование собственной заявки недоступно.</span></div>}
    {item.employee_id === me.id && item.status === "manager_approved" && <div className="notice"><Icon name="clock" /><span>Руководитель согласовал заявку. Она ожидает финального решения HR.</span></div>}
    {me.role === "hr_admin" && item.status === "submitted" && item.employee_id !== me.id && <div className="notice"><Icon name="clock" /><span>HR сможет принять решение после согласования непосредственного руководителя.</span></div>}
    {item.status === "approved" && <DocumentologDocument api={api} id={id} me={me} />}
    <RequestLifecycle api={api} item={item} me={me} onReplace={onReplace} onChanged={() => { resource.reload(); onChanged(); }} notify={notify} />
    <div className="detail-footnote">Создана {dateTime(item.created_at)} · Решение сохраняется внутри прототипа</div></>}
  </Modal>;
}
function historyTitle(status: RequestStatus, previous?: RequestStatus) {
  if (status === "approved" && previous === "cancellation_requested") return "HR отклонил отмену, отпуск сохранён";
  return { submitted: "Заявка отправлена", manager_approved: "Руководитель согласовал заявку", approved: "HR согласовал заявку", rejected: "Заявка отклонена", withdrawn: "Заявка отозвана", cancellation_requested: "Запрошена отмена отпуска", cancelled: "HR подтвердил отмену" }[status];
}
function stageTime(item: LeaveRequest) { return item.history.at(-1)?.created_at || item.created_at; }
function waiting(item: LeaveRequest) {
  const hours = Math.max(0, Math.floor((Date.now() - new Date(stageTime(item)).getTime()) / 3600000));
  return hours < 1 ? "Меньше часа" : hours < 24 ? `${hours} ч` : `${Math.floor(hours / 24)} дн. ${hours % 24} ч`;
}
