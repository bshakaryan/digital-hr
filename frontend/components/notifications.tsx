"use client";

import { useRef, useState } from "react";
import { ApiClient, dateTime, errorMessage, type Notification } from "@/lib/api";
import { Empty, ErrorBox, Icon, Loading } from "./ui";
import { PageHeading } from "./workspace";
import type { Resource } from "./use-resource";

export function Notifications({ api, resource, onOpen }: { api: ApiClient; resource: Resource<Notification[]>; onOpen: (item: Notification) => void }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"unread" | "read">("unread");
  const busy = useRef(false);
  const unread = resource.data?.filter(item => !item.read) ?? [];
  const read = resource.data?.filter(item => item.read) ?? [];
  const items = filter === "unread" ? unread : read;
  const disabled = pending || resource.loading || !!resource.error;
  async function update(path: string) {
    if (busy.current) return;
    busy.current = true; setPending(true); setError("");
    try { await api.patch(path, {}); resource.reload(); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { busy.current = false; setPending(false); }
  }
  return <>
    <PageHeading eyebrow="НА СВЯЗИ" title="Уведомления" description="Прочитанные события переходят в отдельную вкладку. Их можно убрать из списка." action={filter === "unread"
      ? <button className="button button-secondary" disabled={disabled || !unread.length} onClick={() => update("/notifications/read-all")}>Прочитать все<Icon name="check" size={17} /></button>
      : <button className="button button-secondary" disabled={disabled || !read.length} onClick={() => update("/notifications/clear-read")}>Очистить прочитанные<Icon name="close" size={17} /></button>} />
    <div className="list-toolbar notification-toolbar">
      <div className="segmented" aria-label="Фильтр уведомлений">
        <button className={filter === "unread" ? "selected" : ""} aria-pressed={filter === "unread"} onClick={() => setFilter("unread")}>Непрочитанные</button>
        <button className={filter === "read" ? "selected" : ""} aria-pressed={filter === "read"} onClick={() => setFilter("read")}>Прочитанные</button>
      </div>
      <button className="text-button" onClick={resource.reload} disabled={pending || resource.loading}><Icon name="refresh" size={16} /> Обновить</button>
    </div>
    {error && <ErrorBox message={error} />}
    <section className="panel">
      {resource.error ? <ErrorBox message={resource.error} retry={resource.reload} /> : resource.loading && !resource.data ? <Loading /> : !items.length
        ? <Empty icon="bell" title={filter === "unread" ? "Всё прочитано" : "Нет прочитанных уведомлений"} text={filter === "unread" ? "Новые события появятся автоматически." : "Здесь появятся события после прочтения. Список можно очистить."} />
        : <div className="notification-list">{items.map(item => <article className={`notification-card ${item.read ? "" : "is-unread"}`} key={item.id}>
          <span className="metric-icon mint"><Icon name={item.kind.includes("course") ? "book" : item.kind.includes("documentolog") ? "document" : "bell"} /></span>
          <div>
            <div className="notification-title"><h3>{item.title}</h3>{!item.read && <span className="tag">Новое</span>}</div>
            <p>{item.body}</p><time dateTime={item.created_at}>{dateTime(item.created_at)}{item.actor_name && ` · ${item.actor_name}`}</time>
            {item.entity_id && <button className="text-button notification-link" disabled={pending} onClick={() => onOpen(item)}>{item.entity_type === "course" ? "Открыть курс" : item.entity_type === "employee" ? "Открыть профиль" : item.kind.includes("documentolog") ? "Открыть заявку и документ" : `Открыть заявку №${item.entity_id}`}<Icon name="arrow" size={15} /></button>}
          </div>
          {!item.read && <button className="button button-secondary button-small" disabled={disabled} onClick={() => update(`/notifications/${item.id}/read`)}>Прочитано<Icon name="check" size={15} /></button>}
        </article>)}</div>}
    </section>
  </>;
}
