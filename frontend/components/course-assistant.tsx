"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { ApiClient, errorMessage, type AssistantAnswer } from "@/lib/api";
import { Icon } from "./ui";
import { createAssistantHistoryAdapter, type ChatHistoryAdapter, type ChatScope } from "./assistant-history-adapter";
import { AssistantHistorySidebar } from "./assistant-history-sidebar";
import { exchangesFromMessages, useAssistantHistory } from "./use-assistant-history";
import styles from "./assistant-ux.module.css";

const suggestions = ["О чём этот материал?", "Что важно запомнить?"];
interface CourseExchange { id?: string; courseId?: number; question: string; result: AssistantAnswer }

export function CourseAssistant({ api, courseId, historyAdapter }: { api: ApiClient; courseId: number; historyAdapter?: ChatHistoryAdapter | null }) {
  const [question, setQuestion] = useState("");
  const [exchanges, setExchanges] = useState<CourseExchange[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const busy = useRef(false);
  const transcript = useRef<HTMLDivElement>(null);
  const followConversation = useRef(true);
  const olderAnchor = useRef<number | null>(null);
  const currentCourseId = useRef(courseId);
  currentCourseId.current = courseId;
  const scope = useMemo<ChatScope>(() => ({ kind: "course", courseId }), [courseId]);
  const defaultHistoryAdapter = useMemo(() => createAssistantHistoryAdapter(api), [api]);
  const history = useAssistantHistory(historyAdapter === undefined ? defaultHistoryAdapter : historyAdapter ?? undefined, scope);
  const visibleExchanges: CourseExchange[] = history.enabled ? exchangesFromMessages(history.messages) : exchanges.filter((exchange) => exchange.courseId === courseId);

  useEffect(() => {
    setQuestion("");
    setError("");
    followConversation.current = true;
    olderAnchor.current = null;
  }, [courseId]);

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

  async function askQuestion(value: string) {
    const trimmed = value.trim();
    if (busy.current || trimmed.length < 3) return;
    const requestedCourseId = courseId;
    busy.current = true;
    followConversation.current = true;
    setPending(true);
    setError("");
    try {
      if (history.enabled) {
        const saved = await history.send(trimmed);
        if (currentCourseId.current === requestedCourseId) setQuestion(saved ? "" : trimmed);
      } else {
        const answer = await api.post<AssistantAnswer>(`/courses/${courseId}/ask`, { question: trimmed });
        if (currentCourseId.current === requestedCourseId) {
          setExchanges((old) => [...old, { courseId, question: trimmed, result: answer }]);
          setQuestion("");
        }
      }
    } catch (cause) {
      if (currentCourseId.current === requestedCourseId) {
        setQuestion(value);
        setError(errorMessage(cause));
      }
    } finally {
      busy.current = false;
      setPending(false);
    }
  }

  function submit(event: FormEvent) { event.preventDefault(); void askQuestion(question); }

  return <section className={`course-ai ${styles.courseChat} ${history.enabled ? styles.courseWithHistory : ""}`} aria-label="AI Jana по материалу курса">
    <div className={styles.courseHeader}><span className={styles.brandMark} aria-hidden="true"><Icon name="spark" size={17} /></span><div><strong>AI Jana</strong><span>Ответы только по материалам этого курса</span></div></div>
    <div className={styles.courseBody}>
    {history.enabled && <AssistantHistorySidebar compact conversations={history.conversations} selectedId={history.selectedId} loading={history.listLoading} loadingMore={history.listMoreLoading} error={history.listError} nextPage={history.nextPage} busy={pending} onNew={() => { history.newConversation(); setQuestion(""); followConversation.current = true; }} onSelect={(id) => { void history.openConversation(id); setQuestion(""); followConversation.current = true; }} onRetry={() => void history.refreshList()} onMore={() => void history.loadMoreConversations()} />}
    <div className={styles.courseMain}>
    <div className={styles.courseTranscript} ref={transcript} onScroll={trackReadingPosition} aria-label="Вопросы и ответы по курсу">
      {history.enabled && history.previousPage && <button type="button" className={styles.olderMessages} onClick={() => void showOlder()} disabled={history.olderLoading}>{history.olderLoading ? "Загружаем…" : "Предыдущие сообщения"}</button>}
      {history.enabled && history.olderError && <div className={styles.error} role="alert">Не удалось загрузить предыдущие сообщения: {history.olderError} <button type="button" onClick={() => void showOlder()}>Повторить</button></div>}
      {history.enabled && history.messagesLoading && <p className={styles.threadState} role="status">Открываем диалог…</p>}
      {history.enabled && history.messagesError && <div className={styles.error} role="alert">Не удалось открыть историю: {history.messagesError} <button type="button" onClick={() => history.selectedId && void history.openConversation(history.selectedId)}>Повторить</button></div>}
      {!history.messagesLoading && visibleExchanges.length === 0 && !history.messagesError && <div className={styles.courseWelcome}><strong>Сәлем! Спросите о материале курса.</strong><p>Я покажу ответ вместе с фрагментом источника.</p><div className={styles.suggestions}>{suggestions.map((suggestion) => <button type="button" key={suggestion} disabled={pending} onClick={() => void askQuestion(suggestion)}>{suggestion}</button>)}</div></div>}
      {visibleExchanges.map((exchange, index) => <div className={styles.turn} key={exchange.id || index}>
        <div className={styles.userRow}><div className={styles.userBubble}>{exchange.question}</div></div>
        <div className={styles.assistantRow}><span className={styles.avatar} aria-label="AI Jana"><Icon name="spark" size={15} /></span><div className={styles.messageContent}><div className={`${styles.assistantBubble} ${exchange.result.escalate_to_hr ? styles.refusalBubble : ""}`}>{exchange.result.answer}</div>
          {exchange.result.sources.length > 0 && <div className={styles.sourceList} aria-label="Источники ответа">{exchange.result.sources.map((source, sourceIndex) => <details className={styles.source} key={`${source.document_id}-${sourceIndex}`} onToggle={(event) => revealSource(event.currentTarget)}><summary><span className={styles.sourceNumber}>[{sourceIndex + 1}]</span><span className={styles.sourceTitle}>{source.source_filename || source.title}</span><Icon name="chevron" size={13} /></summary><div className={styles.sourceDetail}><strong>{source.title}</strong><span>{source.section}{source.page_number ? ` · стр. ${source.page_number}` : ""}</span><p>{source.content}</p>{source.classification === "synthetic_demo" && <small>Демонстрационный материал, не кадровое правило компании.</small>}</div></details>)}</div>}
          {exchange.result.sources.some((source) => source.classification === "external_legal_snapshot") && <p className={styles.safetyNote}>Копия закона: актуальность нормы не проверена.</p>}
          {exchange.result.escalate_to_hr && <p className={styles.refusalNote}><Icon name="people" size={15} /> Обратитесь к HR. В материалах курса нет надёжного ответа.</p>}
        </div></div>
      </div>)}
      {pending && <div className={styles.assistantRow} role="status"><span className={styles.avatar} aria-hidden="true"><Icon name="spark" size={15} /></span><span className={styles.loadingBubble}><span className={styles.loadingDots} aria-hidden="true"><i /><i /><i /></span> Ищу в материалах курса…</span></div>}
      {error && <div className={styles.error} role="alert"><span>Не удалось получить ответ: {error}</span><button type="button" onClick={() => void askQuestion(question)} disabled={pending}>Повторить</button></div>}
      {history.enabled && history.sendError && <div className={styles.error} role="alert"><span>Не удалось сохранить ответ: {history.sendError}</span><button type="button" onClick={() => void askQuestion(question)} disabled={pending}>Повторить</button></div>}
    </div>
    <form className={styles.courseComposer} onSubmit={submit}><label className="sr-only" htmlFor={`course-ai-${courseId}`}>Ваш вопрос по курсу</label><input id={`course-ai-${courseId}`} value={question} onChange={(event) => setQuestion(event.target.value)} minLength={3} maxLength={1000} required placeholder="Спросите о материале курса…" disabled={pending || history.messagesLoading || Boolean(history.selectedId && history.messagesError)} /><button type="submit" aria-label="Отправить вопрос по курсу" disabled={pending || history.messagesLoading || Boolean(history.selectedId && history.messagesError) || question.trim().length < 3}><Icon name="send" size={18} /></button></form>
    </div>
    </div>
  </section>;
}
