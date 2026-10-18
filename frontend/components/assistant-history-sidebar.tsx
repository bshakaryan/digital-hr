"use client";

import { useState } from "react";
import type { ConversationSummary } from "./assistant-history-adapter";
import styles from "./assistant-ux.module.css";

export function AssistantHistorySidebar({
  conversations, selectedId, loading, loadingMore, error, nextPage, busy, compact = false,
  onNew, onSelect, onRetry, onMore,
}: {
  conversations: ConversationSummary[];
  selectedId: number | null;
  loading: boolean;
  loadingMore: boolean;
  error: string;
  nextPage: number | null;
  busy: boolean;
  compact?: boolean;
  onNew: () => void;
  onSelect: (id: number) => void;
  onRetry: () => void;
  onMore: () => void;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const closeAfter = (action: () => void) => { action(); setMobileOpen(false); };
  return <>
    <button type="button" className={styles.historyToggle} aria-expanded={mobileOpen} aria-controls={compact ? "course-jana-history" : "jana-history"} onClick={() => setMobileOpen((open) => !open)}>
      {mobileOpen ? "Скрыть историю" : "История диалогов"}
    </button>
    <aside id={compact ? "course-jana-history" : "jana-history"} className={`${styles.historySidebar} ${compact ? styles.historyCompact : ""} ${mobileOpen ? styles.historyOpen : ""}`} aria-label="История диалогов AI Jana">
      <div className={styles.historyHeader}><strong>Диалоги</strong><button type="button" className={styles.newChat} onClick={() => closeAfter(onNew)} disabled={busy}>+ Новый чат</button></div>
      <div className={styles.historyList}>
        {loading && <p className={styles.historyState} role="status">Загружаем диалоги…</p>}
        {!loading && conversations.length === 0 && !error && <p className={styles.historyState}>{nextPage ? "На этой странице нет диалогов этого раздела. Загрузите ещё." : "Пока нет сохранённых диалогов. Начните новый чат."}</p>}
        {conversations.map((item) => <button type="button" key={item.id} className={`${styles.historyItem} ${selectedId === item.id ? styles.historySelected : ""}`} aria-current={selectedId === item.id ? "true" : undefined} onClick={() => closeAfter(() => onSelect(item.id))} disabled={busy}>
          <span>{item.title || "Без названия"}</span><small>{new Date(item.updated_at).toLocaleDateString("ru-RU")}</small>
        </button>)}
        {error && <div className={styles.historyError} role="alert"><span>Не удалось загрузить историю: {error}</span><button type="button" onClick={onRetry}>Повторить</button></div>}
        {nextPage && <button type="button" className={styles.historyMore} onClick={onMore} disabled={loadingMore}>{loadingMore ? "Загружаем…" : "Ещё диалоги"}</button>}
      </div>
    </aside>
  </>;
}
