"use client";
import { useEmployeeI18n } from "@/lib/employee-i18n";
import { useEffect, useState } from "react";
import { ApiClient, errorMessage, type Profile } from "@/lib/api";
import { ErrorBox, Icon, Loading } from "./ui";
import { useResource } from "./use-resource";
interface DocumentStatus {
    status: string;
    mode: "disabled" | "mock" | "real";
    external_id?: string;
    view_url?: string;
    file_sha256?: string;
    last_error?: string;
    session_url?: string;
}
const labels: Record<string, string> = {
    not_created: "Документ ещё не подготовлен", prepared: "Подготовлен", creating: "Отправка начата — при зависании нужна сверка",
    signing: "Ожидает подписания", completed: "Имитация подписания завершена",
    completed_reported: "Сервис сообщил о завершении — HR должен проверить документ",
    declined: "Подписант отказал", needs_review: "Результат отправки неизвестен — нужна сверка",
};
export function DocumentologDocument({ api, id, me, employeeId }: {
    api: ApiClient;
    id: number;
    me: Profile;
    employeeId: number;
}) {
    const { t } = useEmployeeI18n();
    const resource = useResource<DocumentStatus>(api, `/requests/${id}/documentolog`);
    const [pending, setPending] = useState(false);
    const [error, setError] = useState("");
    const [recipient, setRecipient] = useState("");
    const [link, setLink] = useState("");
    const item = resource.data;
    const canManage = me.role === "hr_admin" && employeeId !== me.id;
    useEffect(() => {
        if (!item || !["signing", "creating", "needs_review", "completed_reported"].includes(item.status))
            return;
        const timer = setInterval(() => { if (document.visibilityState === "visible")
            resource.reload(); }, 15000);
        return () => clearInterval(timer);
    }, [item?.status, resource.reload]);
    async function create() {
        setPending(true);
        setError("");
        try {
            const result = await api.post<DocumentStatus>(`/requests/${id}/documentolog`, recipient ? { recipient } : {});
            setLink(result.session_url || "");
            resource.reload();
        }
        catch (cause) {
            setError(errorMessage(cause));
            resource.reload();
        }
        finally {
            setPending(false);
        }
    }
    async function getLink() {
        setPending(true);
        setError("");
        try {
            setLink((await api.call<{
                url: string;
            }>(`/requests/${id}/documentolog/session`)).url);
        }
        catch (cause) {
            setError(errorMessage(cause));
        }
        finally {
            setPending(false);
        }
    }
    return <section className="request-comment stack-form"><div className="panel-heading"><h3>{t("Документ в Documentolog")}</h3><button className="text-button" disabled={pending || resource.loading} onClick={resource.reload}><Icon name="refresh" size={16}/>{t("Обновить статус")}</button></div>
    {resource.error ? <ErrorBox message={resource.error} retry={resource.reload}/> : !item ? <Loading /> : <>
      <p>{item.mode === "mock" ? t("Демонстрационный API · подпись имитируется, ЭЦП не используется") : item.mode === "real" ? t("Documentolog Business · состояние документа проверяется отдельно") : t("Documentolog не настроен")}</p>
      <strong>{t(labels[item.status] || item.status)}</strong>
      {item.external_id && <p>{t("Номер: ")}{item.external_id}</p>}
      {item.file_sha256 && <p className="muted small-text" style={{ overflowWrap: "anywhere" }}>{t("SHA-256 документа: ")}{item.file_sha256}</p>}
      <p className="muted small-text">{t("Подписание отслеживается отдельно от финального решения и учёта дней отпуска.")}</p>
      {item.last_error && <ErrorBox message={item.last_error}/>}
      {canManage && item.mode !== "disabled" && item.status === "not_created" && <>
        {item.mode === "real" && <label>{t("ИИН получателя")}<input value={recipient} onChange={event => setRecipient(event.target.value)} inputMode="numeric" maxLength={12} disabled={pending}/></label>}
        <button className="button button-secondary" disabled={pending || (item.mode === "real" && !/^\d{12}$/.test(recipient))} onClick={create}>{pending ? t("Подготавливаем…") : item.mode === "mock" ? t("Создать демонстрационный документ") : t("Передать документ в Documentolog")}</button>
      </>}
      {canManage && item.status !== "not_created" && !link && <button className="text-button" disabled={pending} onClick={getLink}>{t("Получить ссылку на сессию")}</button>}
      {link && <a className="button button-primary" href={link} target="_blank" rel="noopener noreferrer">{item.mode === "mock" ? t("Открыть имитацию подписания") : t("Открыть Documentolog")}<Icon name="arrow" size={16}/></a>}
      {item.view_url && <a className="text-button" href={item.view_url} target="_blank" rel="noopener noreferrer">{t("Открыть документ")}<Icon name="arrow" size={16}/></a>}
    </>}{error && <ErrorBox message={error}/>}
  </section>;
}
interface Integration {
    mode: string;
    connected: boolean;
    counts: Record<string, number>;
}
export function DocumentologIntegration({ api }: {
    api: ApiClient;
}) {
    const resource = useResource<Integration>(api, "/integrations/documentolog");
    const item = resource.data;
    return <section className="panel"><div className="panel-heading"><h2>Интеграция Documentolog</h2><button className="text-button" onClick={resource.reload} disabled={resource.loading}><Icon name="refresh" size={16}/>Проверить связь</button></div><div className="request-comment">{resource.error ? <ErrorBox message={resource.error} retry={resource.reload}/> : !item ? <Loading /> : <div className="notice"><Icon name="info"/><span>{item.mode === "mock" ? `Mock Documentolog ${item.connected ? "доступен по HTTP" : "недоступен"}. Подпись имитируется.` : item.mode === "disabled" ? "Documentolog отключён." : "Выбран реальный API Documentolog Business. Соединение и права организации ещё требуют проверки."} Документ создаётся HR из карточки согласованной заявки. Завершено: <strong>{item.counts.completed || 0}</strong>; ожидают подписания: {item.counts.signing || 0}; требуют сверки: {(item.counts.needs_review || 0) + (item.counts.completed_reported || 0)}.</span></div>}</div></section>;
}
