export interface Profile {
  id: number;
  email: string;
  full_name: string;
  role: "employee" | "manager" | "hr_admin";
  company: string;
  position: string;
  department: string;
  manager_id: number | null;
  manager_name: string | null;
  hire_date: string;
  leave_balance: number;
  data_source: "mock_zup" | "zup";
}

export type RequestStatus = "submitted" | "manager_approved" | "approved" | "rejected" | "withdrawn" | "cancellation_requested" | "cancelled";
export interface SharedCalendar {
  month: string;
  employees: { id: number; full_name: string; department: string; can_open_profile: boolean }[];
  absences: { id: number; employee_id: number; start_date: string; end_date: string;
    status: "submitted" | "manager_approved" | "approved" | "cancellation_requested"; can_open_request: boolean }[];
}
export interface LeaveRequest {
  id: number;
  employee_id: number;
  employee_name: string;
  type: "leave";
  start_date: string;
  end_date: string;
  days_count: number;
  calendar_days: number;
  approval_route: "standard" | "manager_to_hr" | "hr_to_manager";
  can_review: boolean;
  cancellation_allowed: boolean;
  cancellation_block_reason: string | null;
  cancellation_sync_status: "pending" | "synced" | "error" | null;
  cancellation_reference: string | null;
  excluded_dates: string[];
  calendar_version: string;
  zup_sync_status: "not_required" | "pending" | "synced" | "error" | "legacy";
  zup_reference: string | null;
  comment: string;
  status: RequestStatus;
  version: number;
  created_at: string;
  history: { status: RequestStatus; actor_name: string; comment: string; created_at: string }[];
}
export interface RequestDraft { start_date: string; end_date: string; comment: string }
export interface LeaveCalculation {
  start_date: string; end_date: string; days_count: number; calendar_days: number;
  excluded_dates: string[]; calendar_version: string; available_balance: number;
  balance_after: number; sufficient_balance: boolean; source: "mock_zup_http" | "zup_http";
}
export interface Notification {
  id: number; kind: string; title: string; body: string; read: boolean; created_at: string;
  entity_type: "request" | "course" | "employee" | null; entity_id: number | null;
  actor_id: number | null; actor_name: string | null;
}
export interface Course {
  id: number; title: string; description: string; content: string; duration_minutes: number;
  progress: number; completed: boolean; question: string; options: string[];
  objectives: string; status: "draft" | "published"; category: CourseCategory; is_demo: boolean;
  deadline: string | null; learning_status: LearningStatus; overdue: boolean;
  learning_track: LearningTrack; self_enrollable: boolean;
}
export type CourseCategory = "general" | "onboarding" | "logistics" | "warehouse_safety" | "customer_service";
export type LearningStatus = "completed" | "in_progress" | "not_started";
export type LearningTrack = "onboarding" | "development" | "legacy";
export interface PublicCourse {
  id: number; title: string; description: string; objectives: string;
  duration_minutes: number; category: CourseCategory; is_demo: boolean; self_enrollable: boolean;
}
export interface AcademyRewards { xp: number; level: number; next_level_xp: number; badges: string[] }
export interface Knowledge {
  document_id: number; title: string; section: string; content: string;
  file_id?: number; source_filename?: string; page_number?: number;
  document_code?: string; version?: string; language?: string;
  classification?: "synthetic_demo" | "external_legal_snapshot" | "external_reference";
  source_note?: string;
}
export interface KnowledgeFile {
  id: number; filename: string; title: string; document_code: string | null;
  version: string; language: string; classification: "synthetic_demo" | "external_legal_snapshot" | "external_reference";
  source_note: string; access_scope: "all" | "employee" | "manager" | "hr_admin";
  sha256: string; size_bytes: number; chunk_count: number; duplicate: boolean;
}
export interface CourseCatalogItem {
  id: number; title: string; description: string; objectives: string; duration_minutes: number;
  status: "draft" | "published"; question: string; options: string[]; correct_index: number;
  category: CourseCategory; is_demo: boolean; self_enrollable: boolean;
}
export interface LearningAssignment {
  employee_id: number; employee_name: string; department: string; course_id: number; course_title: string;
  category: CourseCategory; learning_track: LearningTrack; progress: number; deadline: string | null; status: LearningStatus;
  overdue: boolean; completed_at: string | null; last_activity_at: string | null;
}
export interface EmployeeLearning {
  employee_id: number; employee_name: string; department: string; position: string; manager_name: string | null;
  total_assigned: number; completed: number; in_progress: number; not_started: number; overdue: number;
  completion_rate: number; xp: number; level: number; badges: string[]; assignments: LearningAssignment[];
}
export interface LearningAnalytics {
  as_of: string; total_demo_employees: number; published_courses: number; total_assignments: number;
  completion_rate: number; overdue_assignments: number;
  status_counts: Record<LearningStatus, number>;
  course_completion: { course_id: number; course_title: string; total: number; completed: number; rate: number }[];
  daily_activity: { date: string; count: number }[];
  overdue_by_department: { department: string; count: number }[];
  assignments: LearningAssignment[]; employees: EmployeeLearning[];
}
export interface AssistantAnswer {
  answer: string; sources: Knowledge[]; escalate_to_hr: boolean; mode: "extractive_demo";
}
export interface AuditEntry {
  id: number; actor_id: number; action: string; entity_type: string; entity_id: number; created_at: string;
  actor_name: string; action_label: string; employee_id: number | null; employee_name: string | null;
}
export interface AuditPage { items: AuditEntry[]; total: number; page: number; page_size: number }

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); this.name = "ApiError"; }
}

function detailMessage(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => {
    if (item && typeof item === "object" && "msg" in item) {
      const value = item as { loc?: unknown[]; msg: string };
      return `${value.loc?.filter((part) => part !== "body").join(" · ") || "Поле"}: ${value.msg}`;
    }
    return "Проверьте введённые данные";
  }).join(". ");
}

export class ApiClient {
  constructor(private token: string | null = null, private expired?: () => void) {}

  async call<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
    if (this.token) headers.set("Authorization", `Bearer ${this.token}`);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20_000);
    try {
      const base = (process.env.NEXT_PUBLIC_API_URL || "/api").replace(/\/$/, "");
      const response = await fetch(`${base}${path}`, {
        ...options, headers, signal: controller.signal, cache: "no-store", credentials: "omit",
      });
      if (response.status === 401) {
        this.expired?.();
        throw new ApiError(this.token ? "Сессия завершена. Войдите снова." : "Не удалось войти. Проверьте почту и пароль.", 401);
      }
      const body: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
        throw new ApiError(detailMessage(detail) || (response.status === 409
          ? "Данные уже изменились. Обновите их перед повторной попыткой."
          : `Сервер вернул ошибку ${response.status}. Попробуйте ещё раз.`), response.status);
      }
      if (body === null) throw new ApiError("Сервер вернул пустой ответ. Обновите данные.", 0);
      return body as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(controller.signal.aborted
        ? "Сервер не ответил вовремя. Проверьте соединение и повторите запрос."
        : "Не удалось связаться с сервером. Проверьте соединение и повторите запрос.", 0);
    } finally { clearTimeout(timer); }
  }

  post<T>(path: string, body: unknown, headers?: HeadersInit): Promise<T> {
    return this.call(path, { method: "POST", body: JSON.stringify(body), headers });
  }
  upload<T>(path: string, body: FormData): Promise<T> {
    return this.call(path, { method: "POST", body });
  }
  patch<T>(path: string, body: unknown): Promise<T> {
    return this.call(path, { method: "PATCH", body: JSON.stringify(body) });
  }
  put<T>(path: string, body: unknown): Promise<T> {
    return this.call(path, { method: "PUT", body: JSON.stringify(body) });
  }

  async download(path: string, filename: string, previewPdf = false) {
    const viewer = previewPdf && filename.toLowerCase().endsWith(".pdf") ? window.open("about:blank", "_blank") : null;
    try {
      const response = await fetch(`${(process.env.NEXT_PUBLIC_API_URL || "/api").replace(/\/$/, "")}${path}`, { headers: this.token ? { Authorization: `Bearer ${this.token}` } : {}, cache: "no-store", credentials: "omit" });
      if (response.status === 401) { this.expired?.(); throw new ApiError("Сессия завершена. Войдите снова.", 401); }
      if (!response.ok) { const body = await response.json().catch(() => null); throw new ApiError(detailMessage(body?.detail) || "Не удалось открыть документ", response.status); }
      const url = URL.createObjectURL(await response.blob());
      if (viewer) { viewer.opener = null; viewer.location.href = url; setTimeout(() => URL.revokeObjectURL(url), 60_000); }
      else { const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
    } catch (error) { viewer?.close(); throw error; }
  }
}

export const errorMessage = (error: unknown) => error instanceof Error ? error.message : "Произошла ошибка. Попробуйте ещё раз.";
export const roleLabel: Record<Profile["role"], string> = { employee: "Сотрудник", manager: "Руководитель", hr_admin: "HR-администратор" };
export const statusLabel: Record<RequestStatus, string> = { submitted: "У руководителя", manager_approved: "На проверке HR", approved: "Согласовано", rejected: "Отклонено", withdrawn: "Отозвано", cancellation_requested: "Запрошена отмена", cancelled: "Отменено" };
export const date = (value: string, full = false) => new Intl.DateTimeFormat("ru-RU", {
  day: "numeric", month: full ? "long" : "short", year: "numeric", timeZone: "UTC",
}).format(new Date(value.length === 10 ? `${value}T00:00:00Z` : value));
export const dateTime = (value: string) => new Intl.DateTimeFormat("ru-RU", {
  day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
}).format(new Date(value));
export const initials = (name: string) => name.trim().split(/\s+/).slice(0, 2).map((word) => word[0]).join("").toUpperCase();
