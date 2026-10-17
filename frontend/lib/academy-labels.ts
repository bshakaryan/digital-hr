import type { CourseCategory, LearningStatus } from "./api";

export const categoryLabel: Record<CourseCategory, string> = {
  general: "Общее обучение",
  onboarding: "Адаптация",
  logistics: "Логистика",
  warehouse_safety: "Безопасность склада",
  customer_service: "Клиентский сервис",
};

export const statusLabel: Record<LearningStatus, string> = {
  completed: "Завершён",
  in_progress: "В процессе",
  not_started: "Не начат",
};

export function shortDate(value: string | null): string {
  if (!value) return "Без срока";
  const [year, month, day] = value.split("-");
  return `${day}.${month}.${year}`;
}
