"use client";

import type { AcademyRewards, Course } from "@/lib/api";
import styles from "./jana-journey.module.css";

const milestones = ["Приёмка", "Склад", "Сортировка", "Транспортировка", "Доставка"] as const;
type JourneyCourse = Pick<Course, "completed" | "progress" | "title">;

/** The five stops are reached at 0%, 25%, 50%, 75%, and 100% of completed assignments. */
export function getJourneyState(courses: JourneyCourse[]) {
  const total = courses.length;
  const completed = courses.filter((course) => course.completed).length;
  const percent = total ? Math.floor((completed / total) * 100) : 0;
  const currentIndex = total ? Math.min(milestones.length - 1, Math.floor((completed * (milestones.length - 1)) / total)) : -1;
  const activeCourse = courses.reduce<JourneyCourse | null>((best, course) =>
    !course.completed && course.progress > 0 && (!best || course.progress > best.progress) ? course : best, null);
  return { total, completed, percent, currentIndex, activeCourse, delivered: total > 0 && completed === total };
}

function ParcelIcon() {
  return <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m3 7 9-4 9 4v10l-9 4-9-4V7Z" /><path d="m3 7 9 4 9-4M12 11v10M7.5 5l9 4" /></svg>;
}

function TruckIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2 6h12v11H2V6ZM14 10h4l4 4v3h-8v-7Z" /><circle cx="6" cy="18" r="2" /><circle cx="18" cy="18" r="2" /></svg>;
}

export function JanaJourney({ courses, rewards }: { courses: Course[]; rewards: AcademyRewards | null }) {
  const journey = getJourneyState(courses);
  const currentName = journey.currentIndex >= 0 ? milestones[journey.currentIndex] : null;

  return <section className={styles.journey} aria-labelledby="jana-journey-title">
    <div className={styles.heading}>
      <div><span className={styles.kicker}>JANA ACADEMY / МАРШРУТ ОБУЧЕНИЯ</span><h2 id="jana-journey-title">Jana Journey</h2><p>От приёмки до доставки — каждый завершённый курс продвигает вашу посылку.</p></div>
      <div className={styles.summary} aria-live="polite"><strong>{journey.total ? `${journey.completed} / ${journey.total}` : "—"}</strong><span>{journey.total ? "курсов завершено" : "нет назначений"}</span></div>
    </div>

    <ol className={styles.route} aria-label="Пять этапов учебного маршрута">
      {milestones.map((name, index) => {
        const isCurrent = index === journey.currentIndex;
        const isComplete = journey.total > 0 && (index < journey.currentIndex || journey.delivered);
        const state = isCurrent ? journey.delivered ? "доставлено" : "текущий этап" : isComplete ? "пройдено" : "впереди";
        return <li key={name} className={`${styles.stop} ${isCurrent ? styles.current : ""} ${isComplete ? styles.complete : ""}`} aria-current={isCurrent ? "step" : undefined} aria-label={`${name}: ${state}`}>
          <span className={styles.marker} aria-hidden="true">{isCurrent ? <ParcelIcon /> : isComplete ? <span className={styles.check}>✓</span> : String(index + 1).padStart(2, "0")}</span>
          <span className={styles.stopName}>{name}</span>
          <span className={styles.stopState}>{state}</span>
        </li>;
      })}
    </ol>

    <div className={styles.footer}>
      <div className={styles.explanation}><TruckIcon /><span>{journey.total === 0 ? "Маршрут начнётся, когда HR назначит вам курс." : journey.delivered ? "Доставка завершена: все назначенные курсы пройдены." : `Сейчас: ${currentName}. Следующий этап откроется после завершения назначенных курсов.`}</span></div>
      {journey.total > 0 && <span className={styles.rate}>{journey.percent}% маршрута</span>}
    </div>
    {journey.activeCourse && <p className={styles.activeCourse}>В изучении: <strong>{journey.activeCourse.title}</strong> · прогресс курса {journey.activeCourse.progress}%</p>}
    {rewards && <div className={styles.rewards} aria-label="Награды из Jana Academy"><span>{rewards.xp} XP</span><span>Уровень {rewards.level}</span><span>Значков: {rewards.badges.length}</span></div>}
    <p className={styles.rule}>Этапы соответствуют 0%, 25%, 50%, 75% и 100% завершённых назначений. Отметка изучения материала сама по себе не продвигает посылку.</p>
  </section>;
}
