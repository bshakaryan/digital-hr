"use client";

import { useState, type FormEvent } from "react";
import { ApiClient, errorMessage, type KnowledgeFile } from "@/lib/api";
import { ErrorBox } from "./ui";
import { useResource } from "./use-resource";

export function KnowledgeAdmin({ api, notify, onUploaded, compact = false }: { api: ApiClient; notify: (message: string) => void; onUploaded?: () => void; compact?: boolean }) {
  const files = useResource<KnowledgeFile[]>(api, "/knowledge-files");
  const [chosenFile, setChosenFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [version, setVersion] = useState("1.0");
  const [classification, setClassification] = useState<KnowledgeFile["classification"]>("synthetic_demo");
  const [language, setLanguage] = useState("ru");
  const [scope, setScope] = useState<KnowledgeFile["access_scope"]>("all");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!chosenFile || busy) return;
    setBusy(true); setError("");
    const form = new FormData();
    form.set("file", chosenFile);
    form.set("title", title.trim());
    form.set("version", version.trim());
    form.set("language", language);
    form.set("classification", classification);
    form.set("access_scope", scope);
    form.set("source_note", note.trim());
    try {
      const result = await api.upload<KnowledgeFile>("/knowledge-files", form);
      files.reload();
      onUploaded?.();
      notify(result.duplicate ? "Этот файл уже загружен: существующая запись сохранена." : `Документ загружен: ${result.chunk_count} фрагментов.`);
      setChosenFile(null); setTitle("");
      (event.target as HTMLFormElement).reset();
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  }

  return <section className={`panel knowledge-admin ${compact ? "knowledge-admin-compact" : ""}`}>
    <h2>{compact ? "Новый документ" : "Документы Academy · HR"}</h2>
    <p>PDF и DOCX сохраняются в базе без изменения. Повтор того же файла определяется по SHA-256.</p>
    {error && <ErrorBox message={error} />}
    <form onSubmit={upload} className="knowledge-admin-form">
      <div className="knowledge-file-field"><span>Файл PDF/DOCX</span><div className="knowledge-file-picker"><input id="knowledge-document-file" className="knowledge-file-input" type="file" accept=".pdf,.docx" required onChange={(event) => { const next = event.target.files?.[0] || null; setChosenFile(next); if (next && !title) setTitle(next.name.replace(/\.(pdf|docx)$/i, "")); }} /><label htmlFor="knowledge-document-file" className="button button-secondary">Выбрать файл</label><span className="knowledge-file-name" title={chosenFile?.name || "Файл не выбран"}>{chosenFile?.name || "Файл не выбран"}</span></div></div>
      <label>Название<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} required /></label>
      <label>Версия файла<input value={version} onChange={(event) => setVersion(event.target.value)} maxLength={80} required /></label>
      <label>Классификация<select value={classification} onChange={(event) => setClassification(event.target.value as KnowledgeFile["classification"])}><option value="synthetic_demo">DEMO / SYNTHETIC</option><option value="external_legal_snapshot">Внешний правовой текст · копия</option><option value="external_reference">Внешний справочный материал</option></select></label>
      <label>Язык<select value={language} onChange={(event) => setLanguage(event.target.value)}><option value="ru">Русский</option><option value="kk">Қазақша</option><option value="en">English</option></select></label>
      <label>Доступ<select value={scope} onChange={(event) => setScope(event.target.value as KnowledgeFile["access_scope"])}><option value="all">Все роли</option><option value="employee">Только сотрудник</option><option value="manager">Только руководитель</option><option value="hr_admin">Только HR</option></select></label>
      <label className="knowledge-admin-wide">Примечание об источнике<input value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} placeholder="Для правового текста укажите дату копии и источник; актуальность проверьте отдельно" /></label>
      <button className="button button-primary" disabled={busy || !chosenFile}>{busy ? "Сохраняем…" : "Загрузить документ"}</button>
    </form>
    {files.error && <ErrorBox message={files.error} retry={files.reload} />}
    <small>{compact ? "После загрузки выберите документ в списке выше и прикрепите его к курсу." : "Прикрепление загруженных документов выполняется в карточке курса выше."}</small>
  </section>;
}
