"use client";

import { useRef, useState, type FormEvent } from "react";
import { ApiClient, errorMessage, type AssistantAnswer } from "@/lib/api";
import { ErrorBox } from "./ui";
import styles from "./assistant-ux.module.css";

const suggestions = ["О чём этот материал?", "Что важно запомнить?"];

export function CourseAssistant({ api, courseId }: { api: ApiClient; courseId: number }) {
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [result, setResult] = useState<AssistantAnswer | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const busy = useRef(false);

  async function askQuestion(value: string) {
    const trimmed = value.trim();
    if (busy.current || trimmed.length < 3) return;
    busy.current = true;
    setPending(true);
    setError("");
    try {
      const answer = await api.post<AssistantAnswer>(`/courses/${courseId}/ask`, { question: trimmed });
      setResult(answer);
      setAsked(trimmed);
      setQuestion("");
    } catch (cause) {
      setQuestion(value);
      setError(errorMessage(cause));
    } finally {
      busy.current = false;
      setPending(false);
    }
  }

  function submit(event: FormEvent) { event.preventDefault(); void askQuestion(question); }

  return <section className="course-ai" aria-label="AI Jana по материалу курса">
    <p className={styles.courseIntro}><strong>Сәлем! Я AI Jana.</strong> Спросите о материале этого курса — покажу ответ и фрагмент документа, на котором он основан.</p>
    <div className={styles.courseSuggestions} aria-label="Примеры вопросов">{suggestions.map((suggestion) => <button type="button" key={suggestion} disabled={pending} onClick={() => void askQuestion(suggestion)}>{suggestion}</button>)}</div>
    <form onSubmit={submit}><label htmlFor={`course-ai-${courseId}`}>Ваш вопрос по курсу</label><input id={`course-ai-${courseId}`} value={question} onChange={(event) => setQuestion(event.target.value)} minLength={3} maxLength={1000} required placeholder="Например, что отражает статус отправления?" disabled={pending} /><button className="button button-primary" disabled={pending || question.trim().length < 3}>{pending ? "Ищем…" : "Спросить"}</button></form>
    {error && <ErrorBox message={error} />}
    {result && <div className={styles.courseAnswer} aria-live="polite"><span>AI JANA · ОТВЕТ ПО МАТЕРИАЛАМ КУРСА</span><p><strong>Вы спросили:</strong> {asked}</p><p>{result.answer}</p>{result.sources.length > 0 && <div className={styles.courseSources}><strong>Проверить источники · {result.sources.length}</strong>{result.sources.map((source, index) => <details key={`${source.document_id}-${index}`}><summary>[{index + 1}] {source.source_filename || source.title} · {source.page_number ? `стр. ${source.page_number}` : source.section}</summary><div>{source.content}</div></details>)}</div>}{result.escalate_to_hr && <small>В прикреплённых документах нет надёжного ответа. Обратитесь в HR.</small>}</div>}
  </section>;
}
