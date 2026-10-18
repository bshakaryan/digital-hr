"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { ApiClient, errorMessage, type AssistantAnswer, type Knowledge } from "@/lib/api";
import { Icon, Loading, Modal } from "./ui";
import { useResource } from "./use-resource";
import { createAssistantHistoryAdapter, type ChatHistoryAdapter, type ChatScope } from "./assistant-history-adapter";
import { AssistantHistorySidebar } from "./assistant-history-sidebar";
import { exchangesFromMessages, useAssistantHistory } from "./use-assistant-history";
import styles from "./assistant-ux.module.css";

const suggestions = ["Как подать заявку на отпуск?", "Как устроено обучение?", "Какие документы есть в базе знаний?"];
const leaveQuestion = /(отпуск|демалыс|leave)/i;

interface Exchange { id?: string; question: string; result: AssistantAnswer }
const generalScope: ChatScope = { kind: "general" };

export function Assistant({ api, onCreateLeave, historyAdapter }: { api: ApiClient; onCreateLeave?: () => void; historyAdapter?: ChatHistoryAdapter | null }) {
  const [question, setQuestion] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [sourceId, setSourceId] = useState<number | null>(null);
  const busy = useRef(false);
  const transcript = useRef<HTMLDivElement>(null);
  const followConversation = useRef(true);
  const olderAnchor = useRef<number | null>(null);
  const defaultHistoryAdapter = useMemo(() => createAssistantHistoryAdapter(api), [api]);
  const history = useAssistantHistory(historyAdapter === undefined ? defaultHistoryAdapter : historyAdapter ?? undefined, generalScope);
  const visibleExchanges: Exchange[] = history.enabled ? exchangesFromMessages(history.messages) : exchanges;

  useEffect(() => {
    if (!followConversation.current) return;
    const frame = requestAnimationFrame(() => {
      const container = transcript.current;
      if (container && followConversation.current) container.scrollTop = container.scrollHeight;
    });
    return () => cancelAnimationFrame(frame);
  }, [visibleExchanges.length, pending, error, history.messagesLoading, history.sendError]);

  useLayoutEffect(() => {
    if (olderAnchor.current === null || !transcript.current) return;
    transcript.current.scrollTop = transcript.current.scrollHeight - olderAnchor.current;
    olderAnchor.current = null;
  }, [visibleExchanges.length]);

  async function showOlder() {
    followConversation.current = false;
    const container = transcript.current;
    if (container) olderAnchor.current = container.scrollHeight - container.scrollTop;
    if (!(await history.loadOlderMessages())) olderAnchor.current = null;
  }

  function trackReadingPosition() {
    const container = transcript.current;
    if (container) followConversation.current = container.scrollHeight - container.scrollTop - container.clientHeight < 72;
  }

  function revealSource(details: HTMLDetailsElement) {
    if (!details.open) return;
    requestAnimationFrame(() => {
      const container = transcript.current;
      if (container && details.open) container.scrollTop += details.getBoundingClientRect().top - container.getBoundingClientRect().top - 8;
    });
  }

  async function ask(value: string) {
    const trimmed = value.trim();
    if (busy.current || trimmed.length < 3) return;
    busy.current = true;
    followConversation.current = true;
    setPending(true);
    setError("");
    try {
      if (history.enabled) {
        if (await history.send(trimmed)) setQuestion("");
        else setQuestion(trimmed);
      } else {
        const result = await api.post<AssistantAnswer>("/assistant/query", { question: trimmed });
        setExchanges((old) => [...old, { question: trimmed, result }]);
        setQuestion("");
      }
    } catch (cause) {
      setQuestion(value);
      setError(errorMessage(cause));
    } finally {
      busy.current = false;
      setPending(false);
    }
  }

  function submit(event: FormEvent) { event.preventDefault(); void ask(question); }

  function leaveAction() {
    return onCreateLeave
      ? <button type="button" className={styles.action} onClick={onCreateLeave}>Оформить отпуск <Icon name="arrow" size={15} /></button>
      : <a className={styles.action} href="#requests">Оформить отпуск <Icon name="arrow" size={15} /></a>;
  }

  return <>
    <section className={`panel assistant-panel ${styles.chat}`} aria-label="Диалог с AI Jana">
      <header className={styles.header}>
        <span className={styles.brandMark} aria-hidden="true"><Icon name="spark" size={22} /></span>
        <div className={styles.identity}><h1>AI Jana</h1><span>Помощник по доступным документам</span></div>
        <span className={styles.headerBadge}>Демо</span>
      </header>
      <div className={styles.chatBody}>
      {history.enabled && <AssistantHistorySidebar conversations={history.conversations} selectedId={history.selectedId} loading={history.listLoading} loadingMore={history.listMoreLoading} error={history.listError} nextPage={history.nextPage} busy={pending} onNew={() => { history.newConversation(); setQuestion(""); followConversation.current = true; }} onSelect={(id) => { void history.openConversation(id); setQuestion(""); setSourceId(null); followConversation.current = true; }} onRetry={() => void history.refreshList()} onMore={() => void history.loadMoreConversations()} />}
      <div className={styles.chatMain}>
      <div className={styles.transcript} ref={transcript} onScroll={trackReadingPosition} aria-label="Сообщения">
        <div className={styles.thread}>
          {history.enabled && history.previousPage && <button type="button" className={styles.olderMessages} onClick={() => void showOlder()} disabled={history.olderLoading}>{history.olderLoading ? "Загружаем…" : "Показать предыдущие сообщения"}</button>}
          {history.enabled && history.olderError && <div className={styles.error} role="alert">Не удалось загрузить предыдущие сообщения: {history.olderError} <button type="button" onClick={() => void showOlder()}>Повторить</button></div>}
          {history.enabled && history.messagesLoading && <p className={styles.threadState} role="status">Открываем диалог…</p>}
          {history.enabled && history.messagesError && <div className={styles.error} role="alert">Не удалось открыть историю: {history.messagesError} <button type="button" onClick={() => history.selectedId && void history.openConversation(history.selectedId)}>Повторить</button></div>}
          {!history.messagesLoading && visibleExchanges.length === 0 && !history.messagesError && <div className={styles.intro}>
            <span className={styles.introMark} aria-hidden="true"><Icon name="spark" size={21} /></span>
            <div className={styles.introText}><strong>Сәлем! Чем могу помочь?</strong><p>Спросите о заявках, обучении или документах. Я покажу, на чём основан ответ.</p></div>
            <div className={styles.introOptions}>
              <span>Попробуйте спросить</span>
              <div className={styles.suggestions}>{suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => void ask(suggestion)} disabled={pending}>{suggestion}</button>)}</div>
              <span>Быстрые действия</span>
              <div className={styles.quickActions}>{leaveAction()}<a className={styles.secondaryAction} href="#academy">Мои курсы <Icon name="arrow" size={15} /></a></div>
            </div>
          </div>}
          {visibleExchanges.map((exchange, index) => <div className={styles.turn} key={exchange.id || index}>
            <div className={styles.userRow}><div className={styles.userBubble}>{exchange.question}</div></div>
            <div className={styles.assistantRow}>
              <span className={styles.avatar} aria-label="AI Jana"><Icon name="spark" size={15} /></span>
              <div className={styles.messageContent}>
                <div className={`${styles.assistantBubble} ${exchange.result.escalate_to_hr ? styles.refusalBubble : ""}`}>{exchange.result.answer}</div>
                {exchange.result.sources.length > 0 && <div className={styles.sourceList} aria-label="Источники ответа">{exchange.result.sources.map((source, sourceIndex) => <details className={styles.source} key={`${source.document_id}-${sourceIndex}`} onToggle={(event) => revealSource(event.currentTarget)}><summary><span className={styles.sourceNumber}>[{sourceIndex + 1}]</span><span className={styles.sourceTitle}>{source.source_filename || source.title}</span><Icon name="chevron" size={13} /></summary><div className={styles.sourceDetail}><strong>{source.title}</strong><span>{source.section}{source.page_number ? ` · стр. ${source.page_number}` : ""}{source.version ? ` · версия ${source.version}` : ""}</span><p>{source.content}</p>{source.classification === "synthetic_demo" && <small>Демонстрационный материал, не кадровое правило компании.</small>}<button type="button" onClick={() => setSourceId(source.document_id)}>Открыть полный источник <Icon name="arrow" size={13} /></button></div></details>)}</div>}
                {exchange.result.sources.some((source) => source.classification === "external_legal_snapshot") && <p className={styles.safetyNote}>Копия закона: актуальность нормы не проверена.</p>}
                {exchange.result.escalate_to_hr && <p className={styles.refusalNote}><Icon name="people" size={15} /> Обратитесь к HR лично. Помощник не отправляет обращения автоматически.</p>}
                {leaveQuestion.test(exchange.question) && <div className={styles.contextAction}><span>Хотите перейти к заявке?</span>{leaveAction()}</div>}
              </div>
            </div>
          </div>)}
          {pending && <div className={styles.assistantRow} role="status"><span className={styles.avatar} aria-hidden="true"><Icon name="spark" size={15} /></span><span className={styles.loadingBubble}><span className={styles.loadingDots} aria-hidden="true"><i /><i /><i /></span> Ищу ответ в документах…</span></div>}
          {error && <div className={styles.error} role="alert"><span>Не удалось получить ответ: {error}</span><button type="button" onClick={() => void ask(question)} disabled={pending}>Повторить</button></div>}
          {history.enabled && history.sendError && <div className={styles.error} role="alert"><span>Не удалось сохранить ответ: {history.sendError}</span><button type="button" onClick={() => void ask(question)} disabled={pending}>Повторить</button></div>}
        </div>
      </div>
      <div className={styles.composer}>
        <form onSubmit={submit}><label className="sr-only" htmlFor="assistant-question">Ваш вопрос</label><textarea id="assistant-question" rows={2} placeholder="Напишите вопрос AI Jana…" minLength={3} maxLength={1000} required value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void ask(question); } }} disabled={pending || history.messagesLoading || Boolean(history.selectedId && history.messagesError)} /><button type="submit" aria-label="Отправить вопрос" disabled={pending || history.messagesLoading || Boolean(history.selectedId && history.messagesError) || question.trim().length < 3}><Icon name="send" size={19} /></button></form>
        <div className={styles.composerMeta}><span>Ответы могут опираться на демонстрационные материалы. Проверяйте источники.</span><span>{question.length}/1000</span></div>
      </div>
      </div>
      </div>
    </section>
    {sourceId !== null && <KnowledgeReader key={sourceId} api={api} id={sourceId} onClose={() => setSourceId(null)} />}
  </>;
}

function KnowledgeReader({ api, id, onClose }: { api: ApiClient; id: number; onClose: () => void }) {
  const resource = useResource<Knowledge>(api, `/knowledge/${id}`);
  return <Modal title="Источник ответа" wide onClose={onClose}>{resource.error ? <div role="alert">Не удалось открыть источник: {resource.error} <button type="button" onClick={resource.reload}>Повторить</button></div> : resource.loading ? <Loading /> : resource.data && <article className="knowledge-content"><span className="eyebrow">ФРАГМЕНТ №{resource.data.document_id}</span><h2>{resource.data.title}</h2><span className="tag">{resource.data.section}{resource.data.page_number ? ` · стр. ${resource.data.page_number}` : ""}</span><div>{resource.data.content}</div>{resource.data.source_filename && <p className="muted small-text">Файл: {resource.data.source_filename} · версия: {resource.data.version}. {resource.data.source_note}</p>}{resource.data.file_id && <button className="button button-secondary" onClick={() => api.download(`/knowledge-files/${resource.data!.file_id}/download`, resource.data!.source_filename || "source").catch(() => {})}>Скачать оригинал</button>}{!resource.data.source_filename && <p className="muted small-text">Ранее созданная запись демонстрационной базы знаний.</p>}</article>}</Modal>;
}
