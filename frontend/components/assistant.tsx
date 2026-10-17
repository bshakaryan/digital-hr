"use client";

import { useRef, useState, type FormEvent } from "react";
import { ApiClient, errorMessage, type AssistantAnswer, type Knowledge } from "@/lib/api";
import { ErrorBox, Icon, Loading, Modal } from "./ui";
import { useResource } from "./use-resource";
import { PageHeading } from "./workspace";
import styles from "./assistant-ux.module.css";

const suggestions = [
  "Как подать заявку на отпуск?",
  "Как устроено обучение?",
  "Какие документы есть в базе знаний?",
];
const leaveQuestion = /(отпуск|демалыс|leave)/i;

interface Exchange { question: string; result: AssistantAnswer }

export function Assistant({ api, onCreateLeave }: { api: ApiClient; onCreateLeave?: () => void }) {
  const [question, setQuestion] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [sourceId, setSourceId] = useState<number | null>(null);
  const busy = useRef(false);
  const end = useRef<HTMLDivElement>(null);

  async function ask(value: string) {
    const trimmed = value.trim();
    if (busy.current || trimmed.length < 3) return;
    busy.current = true;
    setPending(true);
    setError("");
    try {
      const result = await api.post<AssistantAnswer>("/assistant/query", { question: trimmed });
      setExchanges((old) => [...old, { question: trimmed, result }]);
      setQuestion("");
      requestAnimationFrame(() => end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
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
      ? <button type="button" className="button button-primary" onClick={onCreateLeave}>Оформить отпуск <Icon name="arrow" size={16} /></button>
      : <a className="button button-primary" href="#requests">Оформить отпуск <Icon name="arrow" size={16} /></a>;
  }

  return <>
    <PageHeading eyebrow="ПОМОЩНИК ПО ДОКУМЕНТАМ" title="AI Jana" description="Спросите о заявках, обучении и доступных документах." />
    <section className={`panel assistant-panel ${styles.chat}`} aria-label="Диалог с AI Jana">
      <div className="assistant-panel-header"><span className="assistant-mark"><Icon name="spark" size={23} /></span><div><strong>AI Jana</strong><span><span className="live-dot" /> Поиск по доступным документам</span></div><span className="tag">С источниками</span></div>
      <div className="chat-body" aria-live="polite" aria-relevant="additions text">
        {exchanges.length === 0 && <div className={styles.welcome}>
          <span className={styles.welcomeIcon}><Icon name="spark" size={34} /></span>
          <span className={styles.eyebrow}>AI JANA · РЯДОМ, КОГДА НУЖЕН ОТВЕТ</span>
          <h2>Сәлем! Чем могу помочь?</h2>
          <p>Задайте вопрос — я найду ответ в доступных вам документах и покажу, где его проверить.</p>
          <div className={styles.promptGroup}><span className={styles.groupLabel}>Можно спросить</span><div className={styles.suggestions}>{suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => void ask(suggestion)} disabled={pending}>{suggestion}<Icon name="arrow" size={16} /></button>)}</div></div>
          <div className={styles.quickActions}><span className={styles.groupLabel}>Или перейти сразу</span><div className={styles.actionRow}>{leaveAction()}<a className="button button-secondary" href="#academy"><Icon name="book" size={17} /> Мои курсы <Icon name="arrow" size={15} /></a></div></div>
          <small className={styles.guidance}>AI Jana отвечает по документам. Заявку вы оформляете сами; решение принимает человек.</small>
        </div>}
        {exchanges.map((exchange, index) => <div className="exchange" key={index}>
          <div className="user-message"><span className="small-label">ВЫ</span><p>{exchange.question}</p></div>
          <div className="assistant-message"><span className="assistant-message-icon"><Icon name="spark" size={20} /></span><div className={styles.answerContent}>
            <span className="small-label">AI JANA · ОТВЕТ ПО ДОКУМЕНТАМ</span><div className={styles.answerCard}><p>{exchange.result.answer}</p></div>
            {exchange.result.sources.length > 0 && <div className="sources"><span className="small-label">ПРОВЕРИТЬ ИСТОЧНИКИ · {exchange.result.sources.length}</span>{exchange.result.sources.map((source, sourceIndex) => <button type="button" className="source-link" key={`${source.document_id}-${sourceIndex}`} onClick={() => setSourceId(source.document_id)}><span>{sourceIndex + 1}</span><div><strong>{source.title}</strong><small>{source.source_filename ? `${source.source_filename} · ` : ""}{source.page_number ? `стр. ${source.page_number} · ` : ""}{source.section}</small></div><Icon name="arrow" size={16} /></button>)}</div>}
            {leaveQuestion.test(exchange.question) && <div className={styles.contextAction}><div><strong>Хотите перейти к заявке?</strong><span>{onCreateLeave ? "Выберите даты и проверьте расчёт в форме." : "В разделе заявок откройте форму и проверьте расчёт."}</span></div>{leaveAction()}</div>}
            {exchange.result.escalate_to_hr && <div className="notice warning"><Icon name="people" size={18} /><span>По этому вопросу обратитесь к HR лично. Помощник не отправляет обращения автоматически.</span></div>}
            <small className="answer-mode">Проверьте ответ по указанному источнику; копия закона не подтверждает актуальность нормы.</small>
          </div></div>
        </div>)}
        {pending && <Loading label="Ищем в базе знаний…" />}<div ref={end} />
      </div>
      <div className="chat-composer">{error && <ErrorBox message={error} />}<form onSubmit={submit}><label className="sr-only" htmlFor="assistant-question">Ваш вопрос</label><textarea id="assistant-question" rows={2} placeholder="Например, как подать заявку на отпуск?" minLength={3} maxLength={1000} required value={question} onChange={(event) => setQuestion(event.target.value)} disabled={pending} /><button className="button button-primary" aria-label="Отправить вопрос" disabled={pending || question.trim().length < 3}><Icon name="send" size={20} /></button></form><div className="composer-footnote"><span>Ответ основан на доступных документах</span><span>{question.length}/1000</span></div></div>
    </section>
    {sourceId !== null && <KnowledgeReader key={sourceId} api={api} id={sourceId} onClose={() => setSourceId(null)} />}
  </>;
}

function KnowledgeReader({ api, id, onClose }: { api: ApiClient; id: number; onClose: () => void }) {
  const resource = useResource<Knowledge>(api, `/knowledge/${id}`);
  return <Modal title="Источник ответа" wide onClose={onClose}>{resource.error ? <ErrorBox message={resource.error} retry={resource.reload} /> : resource.loading ? <Loading /> : resource.data && <article className="knowledge-content"><span className="eyebrow">ФРАГМЕНТ №{resource.data.document_id}</span><h2>{resource.data.title}</h2><span className="tag">{resource.data.section}{resource.data.page_number ? ` · стр. ${resource.data.page_number}` : ""}</span><div>{resource.data.content}</div>{resource.data.source_filename && <p className="muted small-text">Файл: {resource.data.source_filename} · версия: {resource.data.version}. {resource.data.source_note}</p>}{resource.data.file_id && <button className="button button-secondary" onClick={() => api.download(`/knowledge-files/${resource.data!.file_id}/download`, resource.data!.source_filename || "source").catch(() => {})}>Скачать оригинал</button>}{!resource.data.source_filename && <p className="muted small-text">Ранее созданная запись демонстрационной базы знаний.</p>}</article>}</Modal>;
}
