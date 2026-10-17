"use client";

import { useRef, useState, type FormEvent } from "react";
import { ApiClient, ApiError, errorMessage, type LeaveRequest, type Profile } from "@/lib/api";
import { ErrorBox, Icon } from "./ui";

export function RequestLifecycle({ api, item, me, onReplace, onChanged, notify }: { api: ApiClient; item: LeaveRequest; me: Profile; onReplace: (item: LeaveRequest) => void; onChanged: () => void; notify: (message: string) => void }) {
  const [action, setAction] = useState<"withdraw" | "cancel" | null>(null);
  const [comment, setComment] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const attempt = useRef<{ key: string; action: string; body: { version: number; comment: string } } | null>(null);
  const busy = useRef(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy.current || !action) return;
    busy.current = true; setPending(true); setError("");
    try {
      if (!attempt.current) attempt.current = { key: crypto.randomUUID(), action, body: { version: item.version, comment } };
      await api.post(`/requests/${item.id}/${attempt.current.action}`, attempt.current.body, { "Idempotency-Key": attempt.current.key });
      attempt.current = null; setUncertain(false); setAction(null); setComment(""); onChanged(); notify(action === "withdraw" ? "Заявка отозвана" : "Запрос отмены передан согласующему");
    } catch (cause) {
      const ambiguous = !(cause instanceof ApiError) || cause.status === 0 || cause.status >= 500;
      setUncertain(ambiguous); if (!ambiguous) { attempt.current = null; onChanged(); }
      setError(errorMessage(cause));
    } finally { busy.current = false; setPending(false); }
  }
  async function retryRefund() {
    if (busy.current) return;
    busy.current = true; setPending(true); setError("");
    try { await api.post(`/requests/${item.id}/cancellation-sync`, {}); onChanged(); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { busy.current = false; setPending(false); }
  }
  const own = me.id === item.employee_id;
  const awaiting = ["submitted", "manager_approved"].includes(item.status);
  return <section className="lifecycle-section">
    {own && awaiting && !action && <div className="lifecycle-actions"><button className="button button-secondary" onClick={() => onReplace(item)}>Изменить даты</button><button className="text-button danger-text" onClick={() => setAction("withdraw")}>Отозвать заявку</button></div>}
    {own && item.status === "approved" && !action && (item.cancellation_allowed ? <button className="button button-secondary" onClick={() => setAction("cancel")}>Запросить отмену отпуска</button> : <p className="muted small-text">Отмена недоступна: {item.cancellation_block_reason}</p>)}
    {action && <form onSubmit={submit} className="stack-form"><h3>{action === "withdraw" ? "Отозвать заявку" : "Запросить отмену отпуска"}</h3><p className="muted small-text">{action === "withdraw" ? "Заявка завершится без списания дней. Её период и история сохранятся." : "Независимый согласующий рассмотрит отмену всего периода. Дни вернутся после подтверждения источником."}</p><label>Причина<textarea required maxLength={2000} rows={3} value={comment} disabled={pending || uncertain} onChange={event => setComment(event.target.value)} /></label>{uncertain && <p className="muted small-text">Результат не подтверждён. Повтор отправит ту же команду.</p>}<div className="lifecycle-actions"><button className="button button-primary" disabled={pending}>{pending ? "Отправляем…" : uncertain ? "Повторить команду" : "Подтвердить"}</button><button type="button" className="text-button" disabled={pending || uncertain} onClick={() => { setAction(null); setError(""); }}>Назад</button></div></form>}
    {item.status === "cancellation_requested" && <div className="notice warning"><Icon name="clock" /><span>Согласующий рассматривает отмену. До подтверждения отпуск и списанные дни остаются действующими.</span></div>}
    {item.status === "cancelled" && <div className={`notice ${item.cancellation_sync_status !== "synced" ? "warning" : ""}`}><Icon name="info" /><span>{item.cancellation_sync_status === "synced" ? <>Возврат подтверждён: <strong>{item.days_count} дн.</strong> Квитанция: <strong>{item.cancellation_reference}</strong>.</> : "Отмена подтверждена. Возврат дней ожидает подтверждения 1С; автоматический повтор сохранён."}{me.role === "hr_admin" && item.cancellation_sync_status !== "synced" && <button className="text-button" disabled={pending} onClick={retryRefund}>Повторить возврат</button>}</span></div>}
    {own && ["withdrawn", "rejected", "cancelled"].includes(item.status) && (item.status !== "cancelled" || item.cancellation_sync_status === "synced") && <button className="button button-secondary" onClick={() => onReplace(item)}>Новая заявка на другие даты<Icon name="calendar" size={17} /></button>}
    {error && <ErrorBox message={error} />}
  </section>;
}
