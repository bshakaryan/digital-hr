"use client";

import { useState, type FormEvent } from "react";
import { ApiClient, errorMessage, type AssistantAnswer } from "@/lib/api";
import { ErrorBox } from "./ui";

export function CourseAssistant({ api, courseId }: { api: ApiClient; courseId: number }) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AssistantAnswer | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  async function ask(event: FormEvent) {
    event.preventDefault();
    if (pending || question.trim().length < 3) return;
    setPending(true); setError(""); setResult(null);
    try { setResult(await api.post<AssistantAnswer>(`/courses/${courseId}/ask`, { question: question.trim() })); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setPending(false); }
  }
  return <section className="course-ai">
    <form onSubmit={ask}><label htmlFor={`course-ai-${courseId}`}>Вопрос о материале</label><input id={`course-ai-${courseId}`} value={question} onChange={(event) => setQuestion(event.target.value)} minLength={3} maxLength={1000} required placeholder="Например, что отражает статус отправления?" /><button className="button button-primary" disabled={pending || question.trim().length < 3}>{pending ? "Ищем…" : "Спросить"}</button></form>
      {error && <ErrorBox message={error} />}
      {result && <div className="course-ai-answer"><p>{result.answer}</p>{result.sources.map((source) => <details key={source.document_id}><summary>Источник: {source.source_filename || source.title} · {source.page_number ? `стр. ${source.page_number}` : source.section}</summary><div>{source.content}</div></details>)}{result.escalate_to_hr && <small>В прикреплённых документах нет надёжного ответа. Обратитесь в HR.</small>}</div>}
  </section>;
}
