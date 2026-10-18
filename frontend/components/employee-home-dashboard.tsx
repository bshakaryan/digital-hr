"use client";

import { date, dateTime, type Course, type LeaveRequest, type Notification, type Profile, type SharedCalendar } from "@/lib/api";
import type { Resource } from "./use-resource";
import { ErrorBox, Icon, Loading } from "./ui";
import styles from "./employee-home-dashboard.module.css";

export interface EmployeeHomeDashboardProps {
  me: Profile;
  requests: Resource<LeaveRequest[]>;
  courses: Resource<Course[]>;
  notifications: Resource<Notification[]>;
  /** Supply the current month's sanitized /calendar response, not /employees. */
  calendar: Resource<SharedCalendar>;
  onRequestLeave: () => void;
  onMyRequests: () => void;
  onMyCalendar: () => void;
  onMyLearning: () => void;
  onNotifications: () => void;
  onOpenRequest: (id: number) => void;
  onOpenNotification: (item: Notification) => void;
  /** Lets isolated fixtures hold the date steady. Defaults to the employee's local date. */
  today?: string;
}

function localToday() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function period(start: string, end: string) {
  return start === end ? date(start) : `${date(start)} — ${date(end)}`;
}

function nextCourse(courses: Course[]) {
  return [...courses].filter((course) => !course.completed).sort((left, right) => {
    if (left.overdue !== right.overdue) return left.overdue ? -1 : 1;
    if (left.deadline && right.deadline && left.deadline !== right.deadline) return left.deadline.localeCompare(right.deadline);
    if (Boolean(left.deadline) !== Boolean(right.deadline)) return left.deadline ? -1 : 1;
    if (Boolean(left.progress) !== Boolean(right.progress)) return left.progress ? -1 : 1;
    return left.id - right.id;
  })[0];
}

export function EmployeeHomeDashboard({
  me, requests, courses, notifications, calendar, onRequestLeave, onMyRequests, onMyCalendar,
  onMyLearning, onNotifications, onOpenRequest, onOpenNotification, today = localToday(),
}: EmployeeHomeDashboardProps) {
  const firstName = me.full_name.trim().split(/\s+/)[0] || "коллега";
  const ownLeave = requests.data?.filter((item) => item.employee_id === me.id && ["approved", "cancellation_requested"].includes(item.status) && item.end_date >= today)
    .sort((left, right) => left.start_date.localeCompare(right.start_date) || left.id - right.id);
  const colleagues = new Map(calendar.data?.employees
    .filter((person) => person.id !== me.id && person.department === me.department)
    .map((person) => [person.id, person.full_name]));
  const colleagueLeave = calendar.data?.absences
    .filter((item) => item.status === "approved" && colleagues.has(item.employee_id))
    .sort((left, right) => left.start_date.localeCompare(right.start_date) || left.id - right.id);
  const course = courses.data ? nextCourse(courses.data) : undefined;
  const unread = notifications.data?.filter((item) => !item.read)
    .sort((left, right) => right.created_at.localeCompare(left.created_at) || right.id - left.id);
  const calendarMonth = calendar.data?.month;

  return <div className={styles.dashboard}>
    <header className={styles.intro}>
      <div><span className={styles.eyebrow}>МОЁ ПРОСТРАНСТВО · JANA POST</span><h1>Сәлем, {firstName}!</h1><p>{me.position}{me.department ? ` · ${me.department}` : ""}</p></div>
      <span className={styles.today}><Icon name="calendar" size={17} />{date(today, true)}</span>
    </header>

    <nav className={styles.actions} aria-label="Быстрые действия">
      <button type="button" className={styles.primaryAction} onClick={onRequestLeave}><span className={styles.actionIcon}><Icon name="plus" size={22} /></span><span>Запросить отпуск<small>Создать заявку</small></span><Icon name="arrow" size={18} /></button>
      <button type="button" className={styles.action} onClick={onMyRequests}><span className={styles.actionIcon}><Icon name="document" size={22} /></span><span>Мои заявки<small>Статусы и история</small></span><Icon name="arrow" size={18} /></button>
      <button type="button" className={styles.action} onClick={onMyCalendar}><span className={styles.actionIcon}><Icon name="calendar" size={22} /></span><span>Мой календарь<small>Отпускные дни</small></span><Icon name="arrow" size={18} /></button>
      <button type="button" className={styles.action} onClick={onMyLearning}><span className={styles.actionIcon}><Icon name="book" size={22} /></span><span>Моё обучение<small>Jana Academy</small></span><Icon name="arrow" size={18} /></button>
    </nav>

    <div className={styles.grid}>
      <div className={styles.mainColumn}>
        <section className={`${styles.card} ${styles.balance}`} aria-labelledby="home-balance-title">
          <div><span className={styles.kicker}>ЛИЧНОЕ</span><h2 id="home-balance-title">Отпускной баланс</h2><p>Текущий остаток из {me.data_source === "zup" ? "1С:ЗУП" : "демонстрационного 1С:ЗУП"}</p></div>
          <strong>{me.leave_balance}<span>дн.</span></strong>
        </section>

        <section className={styles.card} aria-labelledby="home-leave-title">
          <div className={styles.cardHeader}><div><span className={styles.kicker}>ПЛАНЫ</span><h2 id="home-leave-title">Мой отпуск</h2></div><button type="button" className={styles.link} onClick={onMyCalendar}>Календарь <Icon name="arrow" size={16} /></button></div>
          {requests.error ? <ErrorBox message={requests.error} retry={requests.reload} /> : requests.loading && !requests.data ? <Loading label="Загружаем отпуска…" /> : ownLeave?.length ? <div className={styles.list}>
            {ownLeave.slice(0, 3).map((item) => <button type="button" className={styles.listButton} key={item.id} onClick={() => onOpenRequest(item.id)}><span className={styles.listIcon}><Icon name="calendar" size={19} /></span><span className={styles.listText}><strong>{period(item.start_date, item.end_date)}</strong><small>{item.status === "cancellation_requested" ? "Ожидает решения об отмене" : item.start_date <= today ? "Отпуск идёт сейчас" : "Согласованный отпуск"} · №{item.id}</small></span><Icon name="chevron" size={17} /></button>)}
          </div> : <p className={styles.empty}>Согласованных предстоящих отпусков пока нет.</p>}
        </section>

        <section className={styles.card} aria-labelledby="home-team-title">
          <div className={styles.cardHeader}><div><span className={styles.kicker}>КОМАНДА</span><h2 id="home-team-title">Коллеги в отпуске</h2></div><span className={styles.month}>{calendarMonth ? new Intl.DateTimeFormat("ru-RU", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${calendarMonth}-01T00:00:00Z`)) : ""}</span></div>
          <p className={styles.context}>Только согласованные отпуска в вашем подразделении.</p>
          {calendar.error ? <ErrorBox message={calendar.error} retry={calendar.reload} /> : calendar.loading && !calendar.data ? <Loading label="Загружаем календарь команды…" /> : colleagueLeave?.length ? <ul className={styles.colleagueList}>
            {colleagueLeave.slice(0, 3).map((item) => <li key={item.id}><span className={styles.avatar} aria-hidden="true">{colleagues.get(item.employee_id)?.trim().charAt(0) || "·"}</span><span><strong>{colleagues.get(item.employee_id)}</strong><small>{period(item.start_date, item.end_date)}</small></span></li>)}
          </ul> : <p className={styles.empty}>В этом месяце согласованных отпусков коллег нет.</p>}
        </section>
      </div>

      <div className={styles.sideColumn}>
        <section className={styles.card} aria-labelledby="home-learning-title">
          <div className={styles.cardHeader}><div><span className={styles.kicker}>JANA ACADEMY</span><h2 id="home-learning-title">Следующий курс</h2></div><span className={styles.headerIcon}><Icon name="book" size={19} /></span></div>
          {courses.error ? <ErrorBox message={courses.error} retry={courses.reload} /> : courses.loading && !courses.data ? <Loading label="Загружаем обучение…" /> : course ? <div className={styles.course}>
            <span className={styles.courseTrack}>{course.learning_track === "onboarding" ? "Адаптация" : course.learning_track === "development" ? "Развитие" : "Назначенный курс"}</span>
            <h3>{course.title}</h3>
            <p>{course.deadline ? `${course.overdue ? "Срок прошёл: " : "Срок: "}${date(course.deadline)}` : "Без установленного срока"}</p>
            <div className={styles.progressLabel}><span>Прогресс</span><strong>{course.progress}%</strong></div>
            <progress max={100} value={course.progress} aria-label={`Прогресс курса «${course.title}»`} />
            <button type="button" className={styles.courseButton} onClick={onMyLearning}>{course.progress ? "Продолжить обучение" : "Перейти к курсу"}<Icon name="arrow" size={16} /></button>
          </div> : <p className={styles.empty}>Все назначенные курсы завершены или новых курсов пока нет.</p>}
        </section>

        <section className={styles.card} aria-labelledby="home-notifications-title">
          <div className={styles.cardHeader}><div><span className={styles.kicker}>ОБНОВЛЕНИЯ</span><h2 id="home-notifications-title">Уведомления {unread?.length ? <span className={styles.count}>{unread.length}</span> : null}</h2></div><span className={styles.headerIcon}><Icon name="bell" size={19} /></span></div>
          {notifications.error ? <ErrorBox message={notifications.error} retry={notifications.reload} /> : notifications.loading && !notifications.data ? <Loading label="Загружаем уведомления…" /> : unread?.length ? <><div className={styles.list}>
            {unread.slice(0, 3).map((item) => <button type="button" className={styles.notification} key={item.id} onClick={() => onOpenNotification(item)}><span className={styles.unreadDot} /><span><strong>{item.title}</strong><small>{dateTime(item.created_at)}</small></span><Icon name="chevron" size={16} /></button>)}
          </div><button type="button" className={styles.link} onClick={onNotifications}>Все уведомления <Icon name="arrow" size={16} /></button></> : <p className={styles.empty}>Непрочитанных уведомлений нет.</p>}
        </section>
      </div>
    </div>
  </div>;
}
