"use client";
import { useEmployeeI18n } from "@/lib/employee-i18n";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiClient, ApiError, errorMessage, initials, statusLabel, type LeaveRequest, type Profile, type RequestStatus } from "@/lib/api";
import { Empty, ErrorBox, Icon, Loading, Modal, Status } from "./ui";
import { useResource, type Resource } from "./use-resource";
import { canReview, PageHeading } from "./workspace";
import { DocumentologDocument } from "./documentolog";
import { RequestLifecycle } from "./request-lifecycle";
export function Requests({ me, employees, resource, onCreate, onOpen }: {
    me: Profile;
    employees: Profile[] | null;
    resource: Resource<LeaveRequest[]>;
    onCreate: () => void;
    onOpen: (id: number) => void;
}) {
    const { t, date, dateTime, locale } = useEmployeeI18n();
    const [scope, setScope] = useState<"own" | "team" | "review">(me.role === "employee" ? "own" : "review");
    const [filter, setFilter] = useState("all");
    const [search, setSearch] = useState("");
    const [from, setFrom] = useState("");
    const [to, setTo] = useState("");
    const items = resource.data?.filter((item) => (scope === "own" ? item.employee_id === me.id : scope === "review" ? item.can_review : item.employee_id !== me.id) && (filter === "all" || item.status === filter) && (!from || item.end_date >= from) && (!to || item.start_date <= to) && `${item.id} ${item.employee_name}`.toLocaleLowerCase(locale).includes(search.toLocaleLowerCase(locale))).sort((a, b) => scope === "review" ? stageTime(a).localeCompare(stageTime(b)) : b.id - a.id);
    const reviewCount = resource.data?.filter(item => item.can_review).length || 0;
    return <><PageHeading eyebrow={t("КАДРОВЫЕ СЕРВИСЫ")} title={t("Заявки")} action={<button className="button button-primary" onClick={onCreate}><Icon name="plus" size={18}/>{t(" Новая заявка")}</button>}/>
    <div className="list-toolbar"><div className="segmented">{me.role !== "employee" && <button className={scope === "review" ? "selected" : ""} onClick={() => { setScope("review"); setFilter("all"); }}>{t("Требуют моего решения · ")}{reviewCount}</button>}<button className={scope === "own" ? "selected" : ""} onClick={() => setScope("own")}>{t("Мои заявки")}</button>{me.role !== "employee" && <button className={scope === "team" ? "selected" : ""} onClick={() => setScope("team")}>{t("Заявки команды")}</button>}</div><button className="icon-button" onClick={resource.reload} disabled={resource.loading} aria-label={t("Обновить заявки")}><Icon name="refresh" size={18}/></button></div>
    <div className="filter-grid"><label>{t("Поиск заявки")}<input type="search" placeholder={t("Номер или сотрудник")} value={search} onChange={event => setSearch(event.target.value)}/></label><label>{t("Статус заявки")}<select value={filter} onChange={event => setFilter(event.target.value)}><option value="all">{t("Все статусы")}</option>{Object.entries(statusLabel).map(([value, title]) => <option key={value} value={value}>{t(title)}</option>)}</select></label><label>{t("Период с")}<input type="date" value={from} onChange={event => setFrom(event.target.value)}/></label><label>{t("Период по")}<input type="date" min={from} value={to} onChange={event => setTo(event.target.value)}/></label></div>
    {scope === "review" && <p className="queue-hint">{t("Сначала показаны заявки, которые дольше ждут вашего решения. Права и актуальный этап проверяются сервером.")}</p>}
    <section className="panel">{resource.error ? <ErrorBox message={resource.error} retry={resource.reload}/> : resource.loading && !resource.data ? <Loading /> : !items?.length ? <Empty title={scope === "review" ? t("Нет заявок для вашего решения") : t("Здесь пока нет заявок")} text={filter !== "all" || search || from || to ? t("Измените фильтры поиска.") : scope === "own" ? t("Создайте заявку, чтобы спланировать отпуск.") : t("Новые задачи появятся после перехода на ваш этап.")} action={scope === "own" && filter === "all" ? <button className="button button-secondary" onClick={onCreate}>{t("Создать заявку ")}<Icon name="plus" size={16}/></button> : undefined}/> : <div className="table-scroll"><table className="requests-table"><thead><tr><th>{t("Заявка")}</th>{scope !== "own" && <th>{t("Сотрудник")}</th>}<th>{t("Период отпуска")}</th><th>{t("Статус")}</th>{scope === "review" && <th>{t("Ожидание на этапе")}</th>}<th><span className="sr-only">{t("Действие")}</span></th></tr></thead><tbody>{items.map((request) => <tr key={request.id}><td><button className="request-title-link" onClick={() => onOpen(request.id)}><span className="request-type-icon"><Icon name="calendar" size={19}/></span><span><strong>{t("Ежегодный отпуск")}</strong><small>№{request.id} · {request.calendar_days}{t(" календарных дней")}</small><small>{request.days_count}{t(" дней к списанию")}</small></span></button></td>{scope !== "own" && <td><div className="table-person"><span className="avatar avatar-mini">{initials(request.employee_name)}</span>{request.employee_name}</div></td>}<td className="period-cell">{date(request.start_date)}<br /><span>{t("по {0}", date(request.end_date))}</span></td><td><Status value={request.status}/></td>{scope === "review" && <td><strong>{waiting(request)}</strong><small className="cell-note">{t("с ")}{dateTime(stageTime(request))}</small></td>}<td><button className="text-button" onClick={() => onOpen(request.id)}>{canReview(me, request, employees) ? t("Рассмотреть") : t("Подробнее")}<Icon name="chevron" size={15}/></button></td></tr>)}</tbody></table></div>}</section>
    <div className="inline-disclaimer"><Icon name="info" size={16}/><p>{t("Считаются календарные дни без праздничных дат Казахстана. Остаток списывается только после финального решения; заявки в ожидании его не резервируют.")}</p></div>
  </>;
}
export function RequestDetail({ id, api, me, employees, onClose, onChanged, notify, onReplace }: {
    id: number;
    api: ApiClient;
    me: Profile;
    employees: Profile[] | null;
    onClose: () => void;
    onChanged: () => void;
    notify: (message: string) => void;
    onReplace: (item: LeaveRequest) => void;
}) {
    const { t, date, dateTime, locale } = useEmployeeI18n();
    const resource = useResource<LeaveRequest>(api, `/requests/${id}`);
    const [decision, setDecision] = useState<"approved" | "rejected">("approved");
    const [comment, setComment] = useState("");
    const [pending, setPending] = useState(false);
    const [error, setError] = useState("");
    const busy = useRef(false);
    const cancellationKey = useRef<string | null>(null);
    const item = resource.data;
    useEffect(() => {
        const timer = setInterval(() => { if (document.visibilityState === "visible" && !busy.current)
            resource.reload(); }, 30000);
        return () => clearInterval(timer);
    }, [resource.reload]);
    async function retrySync() {
        if (busy.current)
            return;
        busy.current = true;
        setPending(true);
        setError("");
        try {
            const updated = await api.post<LeaveRequest>(`/requests/${id}/sync`, {});
            resource.reload();
            onChanged();
            notify(updated.zup_sync_status === "synced" ? "Передача в 1С:ЗУП подтверждена" : "Передача пока не подтверждена; автоматический повтор сохранён");
        }
        catch (cause) {
            setError(errorMessage(cause));
        }
        finally {
            busy.current = false;
            setPending(false);
        }
    }
    async function submit(event: FormEvent) {
        event.preventDefault();
        if (!item || busy.current)
            return;
        busy.current = true;
        setPending(true);
        setError("");
        try {
            if (!cancellationKey.current)
                cancellationKey.current = crypto.randomUUID();
            const body = { status: decision, version: item.version, comment };
            const updated = item.status === "cancellation_requested" ? await api.post<LeaveRequest>(`/requests/${id}/cancellation-decision`, body, { "Idempotency-Key": cancellationKey.current }) : await api.patch<LeaveRequest>(`/requests/${id}/status`, body);
            cancellationKey.current = null;
            resource.reload();
            onChanged();
            setComment("");
            notify(item.status === "cancellation_requested" ? (decision === "approved" ? "Отмена подтверждена" : "Отмена отклонена") : updated.status === "manager_approved" ? `Заявка №${id} передана в HR` : decision === "approved" ? `Заявка №${id} согласована` : `Заявка №${id} отклонена`);
        }
        catch (cause) {
            setError(errorMessage(cause));
            cancellationKey.current = null;
            // Refresh after any uncertain outcome, especially a stale-version conflict.
            if (!(cause instanceof ApiError) || cause.status === 0 || cause.status === 409 || cause.status >= 500) {
                resource.reload();
                onChanged();
            }
        }
        finally {
            busy.current = false;
            setPending(false);
        }
    }
    return <Modal title={t("Заявка №{0}", id)} wide onClose={() => { if (!pending)
        onClose(); }}>
    {resource.error && <ErrorBox message={resource.error} retry={resource.reload}/>}
    {resource.loading && !item ? <Loading /> : item && <><div className="request-detail-heading"><div><span className="eyebrow">{t("ЕЖЕГОДНЫЙ ОТПУСК · ")}{item.calendar_days}{t(" КАЛЕНДАРНЫХ ДНЕЙ · ")}{item.days_count}{t(" К СПИСАНИЮ")}</span><h3>{item.employee_name}</h3></div><Status value={item.status}/></div><dl className="request-detail-dates"><div><dt>{t("Начало отпуска")}</dt><dd>{date(item.start_date, true)}</dd></div><Icon name="arrow"/><div><dt>{t("Окончание отпуска")}</dt><dd>{date(item.end_date, true)}</dd></div></dl><div className="request-comment"><span className="small-label">{t("КОММЕНТАРИЙ СОТРУДНИКА")}</span><p>{item.comment || t("Без комментария")}</p></div><section className="history"><h3>{t("История заявки")}</h3><ol>{item.history.map((entry, index) => <li key={`${entry.created_at}-${index}`}><span className={`history-dot ${entry.status}`}/><div><div className="history-top"><strong>{t(historyTitle(entry.status, item.history[index - 1]?.status, item.approval_route))}</strong><time dateTime={entry.created_at}>{dateTime(entry.created_at)}</time></div><span>{entry.actor_name}</span>{entry.comment && <p>{entry.comment}</p>}</div></li>)}</ol></section>
    {error && <ErrorBox message={error}/>}
    <div className="notice"><Icon name="calendar"/><span>{t("Списываемые дни: ")}<strong>{item.days_count}</strong>.{item.calendar_version === "legacy-deducted" ? t(" Историческое списание по прежнему правилу; новый календарь к нему не применяется.") : <>{item.excluded_dates.length > 0 ? <>{t(" Исключены праздники: ")}{item.excluded_dates.map((day) => date(day)).join(", ")}.</> : t(" Праздничных дат в периоде нет.")}{t(" Обычные и перенесённые выходные учитываются.")}</>}</span></div>
    {item.status === "approved" && <div className={`notice ${item.zup_sync_status === "error" ? "warning" : ""}`}><Icon name="info"/><span>{item.zup_sync_status === "synced" ? <>{t("Передано в 1С:ЗУП. Документ: ")}<strong>{item.zup_reference}</strong>.</> : item.zup_sync_status === "legacy" ? t("Историческая заявка: автоматическая передача в 1С не выполняется.") : <>{t("Заявка одобрена; дни учтены локально. Передача в 1С:ЗУП ")}{item.zup_sync_status === "error" ? t("ожидает повтора") : t("в очереди")}{t(". Повтор не спишет дни ещё раз.")}</>}{me.role === "hr_admin" && (item.zup_sync_status === "pending" || item.zup_sync_status === "error") && <button className="text-button" onClick={retrySync} disabled={pending}>{t("Повторить передачу")}</button>}</span></div>}
    {canReview(me, item, employees) && <form className="decision-form stack-form" onSubmit={submit}><h3>{decisionTitle(item)}</h3><p>{decisionDescription(item)}</p><fieldset disabled={pending || resource.loading || !!resource.error} className="decision-options"><legend className="sr-only">{t("Решение")}</legend><label className={decision === "approved" ? "decision-selected approve" : ""}><input type="radio" name="decision" value="approved" checked={decision === "approved"} onChange={() => setDecision("approved")}/><Icon name="check" size={17}/> {item.status === "cancellation_requested" ? t("Подтвердить отмену") : t("Согласовать")}</label><label className={decision === "rejected" ? "decision-selected reject" : ""}><input type="radio" name="decision" value="rejected" checked={decision === "rejected"} onChange={() => setDecision("rejected")}/><Icon name="close" size={17}/> {item.status === "cancellation_requested" ? t("Сохранить отпуск") : t("Отклонить")}</label></fieldset><label>{t("Комментарий к решению ")}{item.status !== "cancellation_requested" && <span className="optional">{t("· необязательно")}</span>}<textarea required={item.status === "cancellation_requested"} maxLength={2000} value={comment} onChange={(event) => setComment(event.target.value)} rows={3} placeholder={t("Поясните ваше решение сотруднику")} disabled={pending}/></label><div className="form-actions"><span className="muted small-text">{t("Решение сохранится от вашего имени")}</span><button className={`button ${decision === "approved" ? "button-primary" : "button-danger"}`} disabled={pending || resource.loading || !!resource.error}>{pending ? t("Сохраняем…") : t("Подтвердить решение")}<Icon name="check" size={17}/></button></div></form>}
    {item.employee_id === me.id && item.status === "submitted" && <div className="notice"><Icon name="clock"/><span>{item.approval_route === "hr_to_manager" ? t("Заявка ожидает одноэтапного решения руководителя.") : t("Заявка ожидает решения непосредственного руководителя.")}{t(" Согласование собственной заявки недоступно.")}</span></div>}
    {item.employee_id === me.id && item.status === "manager_approved" && <div className="notice"><Icon name="clock"/><span>{item.approval_route === "manager_to_hr" ? t("Заявка ожидает одноэтапного решения HR.") : t("Руководитель согласовал заявку. Она ожидает финального решения HR.")}</span></div>}
    {me.role === "hr_admin" && item.status === "submitted" && item.employee_id !== me.id && item.approval_route === "standard" && <div className="notice"><Icon name="clock"/><span>{t("HR сможет принять решение после согласования непосредственного руководителя.")}</span></div>}
    {item.status === "approved" && <DocumentologDocument api={api} id={id} me={me} employeeId={item.employee_id}/>}
    <RequestLifecycle api={api} item={item} me={me} onReplace={onReplace} onChanged={() => { resource.reload(); onChanged(); }} notify={notify}/>
    <div className="detail-footnote">{t("Создана ")}{dateTime(item.created_at)}{t(" · Решение сохраняется внутри прототипа")}</div></>}
  </Modal>;
}
function decisionTitle(item: LeaveRequest) {
    if (item.status === "cancellation_requested")
        return item.approval_route === "hr_to_manager" ? "Решение руководителя об отмене" : "Решение HR об отмене";
    if (item.status === "submitted")
        return item.approval_route === "hr_to_manager" ? "Финальное решение руководителя" : "Решение руководителя";
    return "Финальное решение HR";
}
function decisionDescription(item: LeaveRequest) {
    if (item.status === "cancellation_requested")
        return `Подтвердите отмену всего периода. ${item.days_count} дней вернутся после подтверждения 1С.`;
    if (item.status === "submitted" && item.approval_route === "standard")
        return "После согласования заявка будет передана HR. Остаток пока не изменится.";
    return `При согласовании спишется ${item.days_count} дней без праздничных дат. Сервер повторно проверит доступный остаток.`;
}
function historyTitle(status: RequestStatus, previous: RequestStatus | undefined, route: LeaveRequest["approval_route"]) {
    const managerFinal = route === "hr_to_manager";
    if (status === "approved" && previous === "cancellation_requested")
        return `${managerFinal ? "Руководитель" : "HR"} отклонил отмену, отпуск сохранён`;
    return { submitted: "Заявка отправлена", manager_approved: "Руководитель согласовал заявку", approved: managerFinal ? "Руководитель согласовал заявку" : "HR согласовал заявку", rejected: "Заявка отклонена", withdrawn: "Заявка отозвана", cancellation_requested: "Запрошена отмена отпуска", cancelled: managerFinal ? "Руководитель подтвердил отмену" : "HR подтвердил отмену" }[status];
}
function stageTime(item: LeaveRequest) { return item.history.at(-1)?.created_at || item.created_at; }
function waiting(item: LeaveRequest) {
    const hours = Math.max(0, Math.floor((Date.now() - new Date(stageTime(item)).getTime()) / 3600000));
    return hours < 1 ? "Меньше часа" : hours < 24 ? `${hours} ч` : `${Math.floor(hours / 24)} дн. ${hours % 24} ч`;
}
