"use client";

import { useRef, useState, type FormEvent } from "react";
import { ApiClient, errorMessage, type Profile } from "@/lib/api";
import { Brand, ErrorBox, Icon, Loading } from "@/components/ui";
import { Workspace } from "@/components/workspace";
import { useSession, type Session } from "@/components/use-session";

const demoAccounts = [
  ["Сотрудник", "employee@example.com"], ["Руководитель", "manager@example.com"],
  ["HR", "hr@example.com"], ["Другая команда", "outsider@example.com"],
];

export default function Home() {
  const { session, api, message, restoring, restoreError, login, logout, retry } = useSession();
  if (restoring || restoreError) return <main className="login-page">
    <header className="login-header"><a className="brand-home" href="/" aria-label="JanaМен — главная"><Brand /></a></header>
    {restoring ? <Loading label="Восстанавливаем сессию…" /> : <section className="empty-state">
      <h1>Не удалось загрузить профиль</h1>
      <ErrorBox message={restoreError} retry={retry} />
      <button className="text-button" onClick={logout}>Перейти ко входу</button>
    </section>}
  </main>;
  if (!session || !api) return <Login message={message} onLogin={login} />;
  return <Workspace key={session.token} api={api} me={session.profile} onLogout={logout} />;
}

function Login({ onLogin, message }: { onLogin: (session: Session) => void; message: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const busy = useRef(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy.current) return;
    busy.current = true; setPending(true); setError("");
    try {
      const auth = await new ApiClient().post<{ access_token: string; token_type: "bearer" }>("/auth/login", { email: email.trim(), password });
      const profile = await new ApiClient(auth.access_token).call<Profile>("/me");
      setPassword("");
      onLogin({ token: auth.access_token, profile });
    } catch (cause) { setError(errorMessage(cause)); }
    finally { busy.current = false; setPending(false); }
  }
  return <main className="login-page">
    <header className="login-header"><a className="brand-home" href="/" aria-label="JanaМен — главная"><Brand /></a></header>
    <div className="login-layout">
    <section className="login-story">
      <div className="login-story-main"><span className="eyebrow">С ЗАБОТОЙ О КОМАНДЕ</span><h1>Всё для работы.<br /><span>Больше для вас.</span></h1><p>Ваши возможности — в одном пространстве.<br />Планируйте отдых, учитесь и двигайтесь вперёд.</p><div className="login-features"><div><Icon name="user" size={27} /><strong>Ваш профиль</strong><span>Важное под рукой</span></div><div><Icon name="calendar" size={27} /><strong>Ваш отдых</strong><span>Заявки без рутины</span></div><div><Icon name="book" size={27} /><strong>Ваше развитие</strong><span>Новые знания рядом</span></div></div></div>
    </section>
    <section className="login-form-side"><div className="login-form-wrap"><span className="eyebrow">ВАШЕ ЛИЧНОЕ ПРОСТРАНСТВО</span><h2>Добро пожаловать</h2><p className="muted">Войдите в своё пространство JanaМен.</p>
      {message && <div className="notice"><Icon name="info" />{message}</div>}
      <form onSubmit={submit} className="login-form"><label htmlFor="email">Рабочая почта</label><div className="input-with-icon"><Icon name="mail" /><input id="email" type="email" autoComplete="username" placeholder="name@example.com" value={email} onChange={(event) => setEmail(event.target.value)} required disabled={pending} /></div><label htmlFor="password">Пароль</label><div className="input-with-icon"><Icon name="shield" /><input id="password" type={visible ? "text" : "password"} autoComplete="current-password" placeholder="Введите пароль" value={password} onChange={(event) => setPassword(event.target.value)} required disabled={pending} /><button type="button" className="password-toggle" onClick={() => setVisible(!visible)} aria-label={visible ? "Скрыть пароль" : "Показать пароль"} aria-pressed={visible}><Icon name="eye" size={18} /></button></div>
        {error && <ErrorBox message={error} />}<button className="button button-primary login-submit" disabled={pending}>{pending ? <><span className="spinner" /> Входим…</> : <>Войти в JanaМен <Icon name="arrow" size={18} /></>}</button>
      </form>
      <div className="demo-accounts"><span className="small-label">ДЕМО-ДОСТУП</span><p>Выберите роль и введите настроенный демо-пароль.</p><div>{demoAccounts.map(([label, address]) => <button key={address} className={email === address ? "demo-choice selected" : "demo-choice"} onClick={() => setEmail(address)} disabled={pending}>{label}</button>)}</div><small>Демо-профили вымышлены. Пароль задаётся при запуске сервера.</small></div>
    </div><div className="login-footer"><Icon name="shield" size={15} /> Вход сохраняется до выхода или завершения сессии</div></section></div>
  </main>;
}
