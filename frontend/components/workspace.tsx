"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiClient, ApiError, date, errorMessage, initials, roleLabel, type Course, type DirectoryPerson, type LeaveCalculation, type LeaveRequest, type Notification, type Profile, type RequestDraft, type SharedCalendar } from "@/lib/api";
import { Brand, ErrorBox, Icon, Loading, Modal, type IconName } from "./ui";
import { useResource } from "./use-resource";
import { Requests, RequestDetail } from "./requests";
import { Academy } from "./academy-dashboard";
import { Assistant } from "./assistant";
import { Audit } from "./audit";
import { ZupIntegration } from "./zup-integration";
import { DocumentologIntegration } from "./documentolog";
import { LeaveCalendar } from "./leave-calendar";
import { TeamCalendar } from "./team";
import { CompanyDirectory } from "./company-directory";
import { Notifications } from "./notifications";
import { IntegrationQueue } from "./integration-queue";
import { EmployeeCalendar } from "./employee-calendar";
import { FloatingJana } from "./floating-jana";
import { EmployeeHomeDashboard } from "./employee-home-dashboard";

type Tab = "home" | "profile" | "requests" | "academy" | "assistant" | "notifications" | "team" | "calendar" | "integrations" | "audit";
const navigation: { tab: Tab; title: string; icon: IconName }[] = [
  { tab: "home", title: "Главная", icon: "home" }, { tab: "profile", title: "Мой профиль", icon: "user" },
  { tab: "requests", title: "Заявки", icon: "document" }, { tab: "academy", title: "Jana Academy", icon: "book" },
  { tab: "assistant", title: "AI Jana", icon: "spark" }, { tab: "notifications", title: "Уведомления", icon: "bell" },
  { tab: "calendar", title: "Календарь сотрудников", icon: "calendar" },
];
const blankDraft: RequestDraft = { start_date: "", end_date: "", comment: "" };
const currentMonth = () => new Date().toLocaleDateString("sv-SE").slice(0, 7);

export function Workspace({ api, me: initialProfile, onLogout }: { api: ApiClient; me: Profile; onLogout: () => void }) {
  const profile = useResource<Profile>(api, "/me");
  const me = profile.data || initialProfile;
  const [tab, setTab] = useState<Tab>("home");
  const [menu, setMenu] = useState(false);
  const [language, setLanguage] = useState("ru");
  const [create, setCreate] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [employeeId, setEmployeeId] = useState<number | null>(null);
  const [employeeView, setEmployeeView] = useState<"profile" | "calendar">("profile");
  const [calendarMode, setCalendarMode] = useState<"employees" | "mine">("employees");
  const [calendarMonth, setCalendarMonth] = useState(currentMonth);
  const [homeMonth, setHomeMonth] = useState(currentMonth);
  const requestReturn = useRef<string | null>(null);
  const [courseId, setCourseId] = useState<number | null>(null);
  const [replacement, setReplacement] = useState<LeaveRequest | null>(null);
  const [draft, setDraft] = useState<RequestDraft>(blankDraft);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const [toast, setToast] = useState("");
  const attempt = useRef<{ key: string; body: RequestDraft } | null>(null);
  const busy = useRef(false);
  const requests = useResource<LeaveRequest[]>(api, "/requests");
  const courses = useResource<Course[]>(api, "/courses");
  const notifications = useResource<Notification[]>(api, "/notifications");
  const employees = useResource<Profile[]>(api, "/employees");
  const directory = useResource<DirectoryPerson[]>(api, "/directory");
  const sharedCalendar = useResource<SharedCalendar>(api, `/calendar?month=${calendarMonth}`);
  const homeCalendar = useResource<SharedCalendar>(api, `/calendar?month=${homeMonth}`);
  const currentHomeCalendar = homeCalendar.data?.month === homeMonth ? homeCalendar : { ...homeCalendar, data: null, loading: true };
  const [calculation, setCalculation] = useState<LeaveCalculation | null>(null);
  const [calculationError, setCalculationError] = useState("");
  const [calculationRevision, setCalculationRevision] = useState(0);
  const currentCalculation = calculation?.start_date === draft.start_date && calculation.end_date === draft.end_date ? calculation : null;
  const sourceTitle = me.data_source === "zup" ? "1С:ЗУП" : "mock 1С:ЗУП";
  const missingRoute = me.role === "employee" && me.manager_id === null;
  const routeDescription = me.role === "manager" ? "Заявка сразу поступит на одноэтапное решение HR."
    : me.role === "hr_admin" ? "Заявка сразу поступит на одноэтапное решение руководителя."
    : "Сначала заявку согласует руководитель, затем финальное решение примет HR.";
  useEffect(() => {
    let active = true;
    setCalculation(null); setCalculationError("");
    if (!create || !draft.start_date || !draft.end_date || draft.end_date < draft.start_date) return;
    const timer = setTimeout(() => {
      api.post<LeaveCalculation>(replacement ? `/requests/${replacement.id}/replacement-calculation` : "/requests/calculate", { start_date: draft.start_date, end_date: draft.end_date })
        .then((value) => { if (active) setCalculation(value); })
        .catch((cause) => { if (active) setCalculationError(errorMessage(cause)); });
    }, 300);
    return () => { active = false; clearTimeout(timer); };
  }, [api, create, draft.start_date, draft.end_date, calculationRevision, replacement]);
  const unread = notifications.data?.filter((item) => !item.read).length;
  const pendingReviews = requests.data?.filter((item) => canReview(me, item, employees.data)).length;
  const nav = [...navigation, { tab: "team" as const, title: "Сотрудники", icon: "people" as const }, ...(me.role === "hr_admin" ? [{ tab: "integrations" as const, title: "Интеграции и очереди", icon: "refresh" as const }, { tab: "audit" as const, title: "Журнал аудита", icon: "shield" as const }] : [])];
  const title = nav.find((item) => item.tab === tab)?.title;
  function navigate(value: Tab) { setTab(value); setMenu(false); setDetailId(null); setEmployeeId(null); setCourseId(null); window.location.hash = value; window.scrollTo({ top: 0, behavior: "instant" }); }
  function openRequest(id: number) { const hash = window.location.hash.slice(1); requestReturn.current = /^(team\/\d+\/calendar|calendar\/mine)$/.test(hash) ? hash : null; setDetailId(id); setEmployeeId(null); window.location.hash = tab === "requests" ? `requests/${id}` : `${tab}/request/${id}`; }
  function closeRequest() { const previous = requestReturn.current; requestReturn.current = null; setDetailId(null); if (previous) window.location.hash = previous; else navigate(tab); }
  function showMyCalendar() { navigate("calendar"); setCalendarMode("mine"); window.location.hash = "calendar/mine"; }
  function newDraft() { if (!uncertain) { setReplacement(null); setDraft(blankDraft); } setCreate(true); }
  function replaceDraft(item: LeaveRequest) { if (uncertain) { setCreate(true); setDetailId(null); return; } setDetailId(null); setReplacement(["submitted", "manager_approved"].includes(item.status) ? item : null); setDraft({ start_date: item.start_date, end_date: item.end_date, comment: item.comment }); setCreateError(""); setCreate(true); }
  function selectEmployee(id: number | null, view: "profile" | "calendar" = "profile") { setEmployeeId(id); setEmployeeView(view); window.location.hash = id ? `team/${id}${view === "calendar" ? "/calendar" : ""}` : "team"; }
  async function openNotification(item: Notification) {
    if (!item.read) { try { await api.patch(`/notifications/${item.id}/read`, {}); notifications.reload(); } catch (cause) { setToast(errorMessage(cause)); } }
    if (item.entity_type === "request" && item.entity_id) openRequest(item.entity_id);
    else if (item.entity_type === "course" && item.entity_id) { navigate("academy"); setCourseId(item.entity_id); window.location.hash = `academy/${item.entity_id}`; }
    else if (item.entity_type === "employee" && item.entity_id) { if (item.entity_id === me.id) navigate("profile"); else { navigate("team"); selectEmployee(item.entity_id); } }
    else navigate("notifications");
  }
  useEffect(() => {
    const route = () => {
      const [value, target, nestedId] = window.location.hash.slice(1).split("/");
      if (value === "profile" && target === "calendar") { window.location.hash = "calendar/mine"; return; }
      const rawId = target === "request" ? nestedId : target;
      const allowed = [...navigation.map(item => item.tab), "team", ...(me.role === "hr_admin" ? ["audit", "integrations"] : [])];
      const next = allowed.includes(value as Tab) ? value as Tab : "home";
      const id = rawId && /^\d+$/.test(rawId) ? Number(rawId) : null;
      setTab(next); setDetailId(target === "request" || next === "requests" ? id : null); setEmployeeId(next === "team" && target !== "request" ? id : null); setCourseId(next === "academy" && target !== "request" ? id : null); setMenu(false);
      setEmployeeView(nestedId === "calendar" ? "calendar" : "profile");
      if (next === "calendar" && target !== "request") setCalendarMode(target === "mine" ? "mine" : "employees");
    };
    route(); window.addEventListener("hashchange", route);
    return () => window.removeEventListener("hashchange", route);
  }, [me.role]);
  function changed() { requests.reload(); notifications.reload(); employees.reload(); profile.reload(); sharedCalendar.reload(); homeCalendar.reload(); }
  useEffect(() => {
    const refresh = () => { setHomeMonth(currentMonth()); profile.reload(); employees.reload(); requests.reload(); notifications.reload(); sharedCalendar.reload(); homeCalendar.reload(); };
    const timer = setInterval(() => { if (document.visibilityState === "visible") { setHomeMonth(currentMonth()); requests.reload(); notifications.reload(); sharedCalendar.reload(); homeCalendar.reload(); } }, 30000);
    window.addEventListener("focus", refresh);
    return () => { window.removeEventListener("focus", refresh); clearInterval(timer); };
  }, [profile.reload, employees.reload, requests.reload, notifications.reload, sharedCalendar.reload, homeCalendar.reload]);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(""), 5500); return () => clearTimeout(timer); }, [toast]);

  async function submitRequest(event: FormEvent) {
    event.preventDefault();
    if (busy.current) return;
    if (!draft.start_date || !draft.end_date || draft.end_date < draft.start_date) { setCreateError("Дата окончания должна быть не раньше даты начала."); return; }
    if (!uncertain && (!currentCalculation || !currentCalculation.sufficient_balance)) { setCreateError("Дождитесь расчёта 1С:ЗУП и проверьте доступный остаток."); return; }
    busy.current = true; setCreating(true); setCreateError("");
    try {
      if (!attempt.current) attempt.current = { key: crypto.randomUUID(), body: { ...draft } };
      const result = await api.post<LeaveRequest>(replacement ? `/requests/${replacement.id}/replace` : "/requests", replacement ? { ...attempt.current.body, version: replacement.version } : attempt.current.body, { "Idempotency-Key": attempt.current.key });
      attempt.current = null; setUncertain(false); setDraft(blankDraft); setCreate(false);
      setReplacement(null); changed(); setToast(`Заявка №${result.id} отправлена на согласование`); openRequest(result.id);
    } catch (cause) {
      const ambiguous = !(cause instanceof ApiError) || cause.status === 0 || cause.status >= 500;
      setUncertain(ambiguous);
      if (!ambiguous) { attempt.current = null; setCalculationRevision((value) => value + 1); }
      setCreateError(errorMessage(cause));
    } finally { busy.current = false; setCreating(false); }
  }

  return <div className="app-shell">
    <a href="#main-content" className="skip-link">Перейти к содержимому</a>
    <div className="workspace-header">
      <div className="utility-bar"><label className="language-switch" title="Переключатель языка (заглушка)"><Icon name="globe" size={16} /><select aria-label="Язык интерфейса" value={language} onChange={event => setLanguage(event.target.value)}><option value="ru">Русский</option><option value="kk">Қазақша</option></select></label><div className="utility-actions"><button className="utility-profile" onClick={() => navigate("profile")} aria-label="Открыть мой профиль"><span className="avatar avatar-small">{initials(me.full_name)}</span><span>{me.full_name}<small>{roleLabel[me.role]}</small></span></button><button className="icon-button notification-button" onClick={() => navigate("notifications")} aria-label={`Уведомления${unread ? `, непрочитанных: ${unread}` : ""}`}><Icon name="bell" />{!!unread && <i />}</button><button className="icon-button" aria-label="Выйти из аккаунта" onClick={onLogout}><Icon name="logout" size={18} /></button></div></div>
      {menu && <button className="navigation-backdrop" onClick={() => setMenu(false)} aria-label="Закрыть меню" />}
      <header className="navigation-bar"><button className="brand-home" onClick={() => navigate("home")} aria-label="JanaМен — главная"><Brand /></button><button className="icon-button menu-button" onClick={() => setMenu(!menu)} aria-label="Открыть меню" aria-expanded={menu} aria-controls="workspace-navigation"><Icon name="menu" /></button>
        <nav id="workspace-navigation" className={`workspace-navigation ${menu ? "navigation-open" : ""}`} aria-label="Основная навигация"><button className="mobile-menu-close icon-button" onClick={() => setMenu(false)} aria-label="Закрыть меню"><Icon name="close" /></button>{[nav.slice(0, 5), nav.slice(5)].map((group, index) => <div key={index} className={index ? "nav-secondary" : "nav-primary"}>{group.map((item) => <button key={item.tab} onClick={() => navigate(item.tab)} className={`nav-item ${item.tab === "notifications" ? "nav-notifications" : ""} ${tab === item.tab ? "active" : ""}`} aria-current={tab === item.tab ? "page" : undefined}><Icon name={item.icon} size={18} /><span>{item.title}</span>{item.tab === "notifications" && !!unread && <span className="nav-count">{unread}</span>}{item.tab === "requests" && !!pendingReviews && <span className="nav-count">{pendingReviews}</span>}</button>)}</div>)}</nav>
      </header>
    </div>
    <div className="main-shell"><div className="context-bar"><div className="breadcrumb"><span>Моё пространство</span><Icon name="chevron" size={12} /><strong>{title}</strong></div></div>
    <main id="main-content" className={`main-content ${tab === "assistant" ? "assistant-page" : ""}`} tabIndex={-1} style={tab !== "assistant" ? { paddingBottom: "calc(112px + env(safe-area-inset-bottom))" } : undefined}>
      {profile.error && <ErrorBox message={`Не удалось обновить остаток: ${profile.error}`} retry={profile.reload} />}
      {tab === "home" && <EmployeeHomeDashboard me={me} requests={requests} courses={courses} notifications={notifications} calendar={currentHomeCalendar} onRequestLeave={newDraft} onMyRequests={() => navigate("requests")} onMyCalendar={showMyCalendar} onMyLearning={() => navigate("academy")} onNotifications={() => navigate("notifications")} onOpenRequest={openRequest} onOpenNotification={openNotification} />}
      {tab === "profile" && <><PageHeading eyebrow="ЛИЧНОЕ" title="Мой профиль" action={<button type="button" className="button button-secondary" onClick={showMyCalendar}><Icon name="calendar" size={17} />Мой календарь</button>} /><ProfileCard me={me} /></>}
      {tab === "requests" && <Requests me={me} employees={employees.data} resource={requests} onCreate={newDraft} onOpen={openRequest} />}
      {tab === "academy" && <Academy api={api} courses={courses} role={me.role} initialCourseId={courseId} onChanged={() => { courses.reload(); notifications.reload(); }} notify={setToast} />}
      {tab === "assistant" && <Assistant api={api} />}
      {tab === "notifications" && <Notifications api={api} resource={notifications} onOpen={openNotification} />}
      {tab === "team" && <CompanyDirectory directory={directory} profiles={employees} requests={requests} me={me} selectedId={employeeId} selectedView={employeeView} onSelect={selectEmployee} onRequest={openRequest} />}
      {tab === "calendar" && <><PageHeading eyebrow="ПЛАНИРОВАНИЕ" title="Календарь сотрудников" description="Отпуска сотрудников и ваши дни отдыха." /><div className="calendar-view-bar"><div className="segmented calendar-mode-buttons" role="group" aria-label="Вид календаря"><button type="button" className={calendarMode === "mine" ? "selected" : ""} aria-pressed={calendarMode === "mine"} onClick={showMyCalendar}>Мой календарь</button><button type="button" className={calendarMode === "employees" ? "selected" : ""} aria-pressed={calendarMode === "employees"} onClick={() => { setCalendarMode("employees"); navigate("calendar"); }}>Общий</button></div><div className="calendar-balance"><Icon name="leaf" size={20} /><span>Остаток отпуска<strong>{me.leave_balance} дн.</strong></span></div></div>{calendarMode === "mine" ? <EmployeeCalendar key={me.id} employee={me} requests={requests} month={calendarMonth} onMonthChange={setCalendarMonth} onOpen={openRequest} /> : <TeamCalendar resource={sharedCalendar} month={calendarMonth} onMonthChange={setCalendarMonth} onOpen={openRequest} onEmployee={id => { if (id === me.id) showMyCalendar(); else { navigate("team"); selectEmployee(id, "calendar"); } }} />}</>}
      {tab === "integrations" && me.role === "hr_admin" && <><PageHeading eyebrow="АДМИНИСТРИРОВАНИЕ" title="Интеграции и очереди" description="Состояние связи, передачи отпусков и документов." /><ZupIntegration api={api} /><DocumentologIntegration api={api} /><IntegrationQueue requests={requests} onOpen={openRequest} /></>}
      {tab === "audit" && me.role === "hr_admin" && <Audit api={api} employees={employees.data || []} onRequest={openRequest} onEmployee={id => { navigate("team"); selectEmployee(id); }} />}
    </main></div>
    {tab !== "assistant" && !menu && <FloatingJana />}
    <div className="toast-region" role="status" aria-live="polite">{toast && <div className="toast"><Icon name="check" /><span>{toast}</span><button className="icon-button" onClick={() => setToast("")} aria-label="Скрыть сообщение"><Icon name="close" size={16} /></button></div>}</div>
    {create && <Modal wide title={replacement ? `Изменение дат · заявка №${replacement.id}` : "Заявка на отпуск"} onClose={() => { if (!creating) setCreate(false); }}><p className="modal-description">{replacement ? `Новая заявка заменит №${replacement.id} и пройдёт согласование заново. Исходная история сохранится.` : `Спланируйте время для себя. ${routeDescription}`}</p><form onSubmit={submitRequest} className="stack-form"><div className="form-row"><label>Дата начала<input type="date" required value={draft.start_date} disabled={creating || uncertain || missingRoute} onChange={(event) => setDraft({ ...draft, start_date: event.target.value })} /></label><label>Дата окончания<input type="date" required min={draft.start_date || undefined} value={draft.end_date} disabled={creating || uncertain || missingRoute} onChange={(event) => setDraft({ ...draft, end_date: event.target.value })} /></label></div>{currentCalculation && <LeaveCalendar calculation={currentCalculation} />}<label>Комментарий <span className="optional">· необязательно</span><textarea rows={4} placeholder="Что нужно знать согласующему?" value={draft.comment} disabled={creating || uncertain || missingRoute} onChange={(event) => setDraft({ ...draft, comment: event.target.value })} /></label><div className="notice"><Icon name="info" /><span>{currentCalculation ? <>По расчёту {sourceTitle}: <strong>{currentCalculation.days_count} дн.</strong> из {currentCalculation.calendar_days} календарных. Доступно <strong>{currentCalculation.available_balance} дн.</strong>{currentCalculation.sufficient_balance ? <> После одобрения останется <strong>{currentCalculation.balance_after} дн.</strong></> : " Недостаточно дней отпуска."}{currentCalculation.excluded_dates.length > 0 && <> Исключены праздники: {currentCalculation.excluded_dates.map((day) => date(day)).join(", ")}.</>}</> : draft.start_date && draft.end_date && !calculationError ? `Получаем расчёт из ${sourceTitle}…` : "Выберите период: календарные дни без праздничных дат. Выходные учитываются."}</span></div>{calculationError && <ErrorBox message={calculationError} retry={() => setCalculationRevision((value) => value + 1)} />}<p className="muted small-text">Дни списываются после финального решения. Ожидающие заявки не резервируют остаток.</p>{missingRoute && <div className="notice warning"><Icon name="people" /><span>В профиле не назначен непосредственный руководитель. Обратитесь в HR для настройки маршрута согласования.</span></div>}{uncertain && <div className="notice warning"><Icon name="shield" /><span>Результат отправки не подтверждён. Повторим ту же заявку с сохранённым ключом: повтор не создаст вторую заявку. До подтверждения данные зафиксированы.</span></div>}{createError && <ErrorBox message={createError} />}<div className="form-actions"><button type="button" className="button button-secondary" disabled={creating} onClick={() => setCreate(false)}>Закрыть</button><button className="button button-primary" disabled={creating || missingRoute || (!uncertain && (!currentCalculation || !currentCalculation.sufficient_balance))}>{creating ? <><span className="spinner" /> Отправляем…</> : <>{uncertain ? "Повторить отправку" : "Отправить заявку"}<Icon name="arrow" size={17} /></>}</button></div></form></Modal>}
    {detailId !== null && <RequestDetail key={detailId} id={detailId} api={api} me={me} employees={employees.data} onClose={closeRequest} onChanged={changed} notify={setToast} onReplace={replaceDraft} />}
  </div>;
}

export function canReview(me: Profile, request: LeaveRequest, employees: Profile[] | null) {
  void me; void employees;
  return request.can_review;
}

export function PageHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description?: string; action?: React.ReactNode }) {
  return <div className="page-heading"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div>;
}

export function ProfileCard({ me }: { me: Profile }) {
  const fields = [["Компания", me.company], ["Должность", me.position], ["Подразделение", me.department], ["Руководитель", me.manager_name || "Не назначен"], ["Рабочая почта", me.email], ["Дата приёма", date(me.hire_date, true)], ["Роль в системе", roleLabel[me.role]]];
  const source = me.data_source === "zup" ? "1С:ЗУП" : "mock 1С:ЗУП";
  return <section className="panel profile-panel"><div className="profile-cover"><span className="eyebrow">JANA · PEOPLE FIRST</span><span aria-hidden="true">↗</span></div><div className="profile-intro"><span className="avatar avatar-large">{initials(me.full_name)}</span><div><h2>{me.full_name}</h2><p>{me.position} · {me.department}</p></div>{me.data_source === "zup" && <span className="tag">Профиль 1С</span>}</div><dl className="profile-fields">{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><div className="profile-balance"><span className="metric-icon mint"><Icon name="leaf" size={24} /></span><div><strong>{me.leave_balance} дней отпуска</strong><p>Остаток из {source} с учётом заявок в передаче</p></div></div><div className="notice"><Icon name="info" /><span>Профиль подключён к {source} по HTTP. Расчёт учитывает календарь источника; кадровые данные доступны для просмотра.</span></div></section>;
}
