/** Browser smoke for merged AI Jana history and the employee home; synthetic API only. */
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE || "playwright");
const origin = process.env.WEB_URL || "http://127.0.0.1:3000";
const now = new Date().toISOString();
const currentMonth = new Intl.DateTimeFormat("sv-SE", { year: "numeric", month: "2-digit", timeZone: "Asia/Almaty" }).format(new Date());
const nextMonth = new Date(Date.UTC(Number(currentMonth.slice(0, 4)), Number(currentMonth.slice(5)), 1)).toISOString().slice(0, 7);
const futureDay = (offset) => new Date(Date.now() + offset * 86400000).toISOString().slice(0, 10);
const me = (role) => ({ id: 101, full_name: "Айдана Демо", role, email: "aidana@example.com", position: "Специалист", department: "Логистика", company: "Демо", manager_id: 1, manager_name: "Демо Руководитель", hire_date: "2024-01-01", leave_balance: 20, data_source: "mock_zup" });
const leave = { id: 501, employee_id: 101, employee_name: "Айдана Демо", type: "leave", status: "approved", start_date: futureDay(30), end_date: futureDay(32), days_count: 3, calendar_days: 3, excluded_dates: [], calendar_version: "test-fixture", approval_route: "manager_to_hr", can_review: false, cancellation_allowed: false, cancellation_block_reason: "Демо", cancellation_sync_status: null, cancellation_reference: null, zup_sync_status: "legacy", zup_reference: null, comment: "Демо", version: 1, created_at: now, history: [] };
const course = { id: 7, title: "Учебный курс", description: "Демо материал", content: "", duration_minutes: 20, progress: 40, completed: false, question: "Вопрос?", options: ["Да", "Нет"], objectives: "Знать основы", status: "published", category: "general", is_demo: true, deadline: null, learning_status: "in_progress", overdue: false, learning_track: "development", self_enrollable: false };
const source = { document_id: 9, title: "Демо источник", section: "02", content: "Демонстрационный источник ответа", source_filename: "HR-01.pdf", classification: "synthetic_demo" };
const conversations = [
  { id: 1, course_id: null, title: "Вопрос об отпуске", created_at: now, updated_at: now },
  { id: 2, course_id: 7, title: "Вопрос по курсу", created_at: now, updated_at: now },
];
const stored = new Map([
  [1, [{ id: 11, role: "user", text: "Вопрос об отпуске", sources: [], escalate_to_hr: null, mode: null, client_turn_id: "one", created_at: now }, { id: 11, role: "assistant", text: "Ответ по общему документу", sources: [source], escalate_to_hr: false, mode: "extractive_demo", client_turn_id: "one", created_at: now }]],
  [2, [{ id: 21, role: "user", text: "Вопрос по курсу", sources: [], escalate_to_hr: null, mode: null, client_turn_id: "two", created_at: now }, { id: 21, role: "assistant", text: "Ответ только по материалу курса", sources: [source], escalate_to_hr: false, mode: "extractive_demo", client_turn_id: "two", created_at: now }]],
]);
const browser = await chromium.launch({ headless: true });
try {
  for (const width of [1440, 390]) {
    console.log(`Checking viewport ${width}`);
    const context = await browser.newContext({ viewport: { width, height: 900 }, timezoneId: "Asia/Almaty" });
    await context.addInitScript(() => sessionStorage.setItem("jana-hr.access-token", "synthetic-employee-token"));
    const page = await context.newPage();
    const errors = [], calls = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/api/**", async route => {
      const url = new URL(route.request().url());
      const path = url.pathname;
      calls.push(url.pathname + url.search);
      if (path === "/api/auth/login") return route.fulfill({ json: { access_token: "synthetic-employee-token", token_type: "bearer" } });
      if (path === "/api/notifications/1/read") return route.fulfill({ json: { ok: true } });
      if (route.request().method() !== "GET") throw new Error(`Unexpected write: ${path}`);
      const month = url.searchParams.get("month");
      const json = path === "/api/me" ? me("employee") : path === "/api/requests" ? [leave] : path === "/api/requests/501" ? leave
        : path === "/api/courses" ? [course] : path === "/api/courses/7" ? course : path === "/api/courses/7/materials" ? []
        : path === "/api/courses/discover" || path === "/api/employees" || path === "/api/directory" ? []
        : path === "/api/courses/rewards" ? { xp: 0, level: 1, next_level_xp: 100, badges: [] }
        : path === "/api/notifications" ? [{ id: 1, kind: "course", title: "Новый курс", body: "Демо", read: false, created_at: now, entity_type: null, entity_id: null, actor_id: null, actor_name: null }]
        : path === "/api/calendar" ? { month, employees: [{ id: 101, full_name: "Айдана Демо", department: "Логистика", can_open_profile: true }, { id: 102, full_name: "Бекжан Демо", department: "Логистика", can_open_profile: false }], absences: month === currentMonth ? [{ id: 777, employee_id: 102, start_date: `${month}-10`, end_date: `${month}-12`, status: "approved", can_open_request: false }] : [] }
        : path === "/api/assistant/conversations" ? { items: conversations, total: conversations.length, page: 1, page_size: 20 }
        : /^\/api\/assistant\/conversations\/\d+$/.test(path) ? (() => { const id = Number(path.split("/").at(-1)); return { id, course_id: id === 1 ? null : 7, created_at: now, updated_at: now, messages: stored.get(id), total_turns: 1, page: 1, page_size: 30 }; })() : [];
      return route.fulfill({ json });
    });
    await page.goto(origin);
    await page.getByRole("heading", { name: /Сәлем, Айдана!/ }).waitFor();
    await page.getByRole("heading", { name: "Коллеги в отпуске" }).waitFor();
    await page.getByText("Бекжан Демо").waitFor();
    assert.ok(calls.some((path) => path.startsWith("/api/calendar?month=")));
    await page.getByRole("region", { name: "Мой отпуск" }).locator("button").last().click();
    await page.getByRole("dialog", { name: "Заявка №501" }).waitFor();
    await page.getByRole("dialog", { name: "Заявка №501" }).getByRole("button", { name: "Закрыть" }).click();
    await page.getByRole("navigation", { name: "Быстрые действия" }).getByRole("button", { name: /Запросить отпуск/ }).click();
    await page.getByRole("dialog", { name: "Заявка на отпуск" }).waitFor();
    await page.getByRole("dialog", { name: "Заявка на отпуск" }).getByRole("button", { name: "Закрыть" }).first().click();
    await page.getByRole("navigation", { name: "Быстрые действия" }).getByRole("button", { name: /Мой календарь/ }).click();
    assert.ok(page.url().endsWith("#calendar/mine"));
    await page.getByLabel("Месяц личного календаря", { exact: true }).fill(nextMonth);
    await page.goto(`${origin}/#home`);
    await page.getByRole("heading", { name: "Коллеги в отпуске" }).waitFor();
    await page.getByText("Бекжан Демо").waitFor();
    await page.getByRole("navigation", { name: "Быстрые действия" }).getByRole("button", { name: /Мои заявки/ }).click();
    assert.ok(page.url().endsWith("#requests"));
    await page.goto(`${origin}/#home`);
    await page.getByRole("navigation", { name: "Быстрые действия" }).getByRole("button", { name: /Моё обучение/ }).click();
    assert.ok(page.url().endsWith("#academy"));
    await page.goto(`${origin}/#home`);
    await page.getByRole("region", { name: /Уведомления/ }).getByRole("button", { name: /Новый курс/ }).click();
    await page.waitForURL(/#notifications$/);
    assert.ok(page.url().endsWith("#notifications"));
    assert.ok(calls.includes("/api/notifications/1/read"));
    await page.goto(`${origin}/#assistant`);
    const history = page.getByRole("complementary", { name: "История диалогов AI Jana" });
    if (width === 390) await page.getByRole("button", { name: "История диалогов", exact: true }).click();
    await history.getByRole("button", { name: /Вопрос об отпуске/ }).waitFor();
    assert.equal(await history.getByRole("button", { name: /Вопрос по курсу/ }).count(), 0);
    await history.getByRole("button", { name: /Вопрос об отпуске/ }).click();
    await page.getByText("Ответ по общему документу").waitFor();
    await page.reload();
    if (width === 390) await page.getByRole("button", { name: "История диалогов", exact: true }).click();
    await history.getByRole("button", { name: /Вопрос об отпуске/ }).click();
    await page.getByText("Ответ по общему документу").waitFor();
    await page.goto(`${origin}/#academy/7`);
    const reader = page.getByRole("dialog", { name: "Jana Academy · Обучение" });
    await reader.waitFor();
    await reader.getByRole("button", { name: /Спросить AI Jana/ }).click();
    const courseHistory = reader.getByRole("complementary", { name: "История диалогов AI Jana" });
    if (width === 390) await reader.getByRole("button", { name: "История диалогов", exact: true }).click();
    await courseHistory.getByRole("button", { name: /Вопрос по курсу/ }).waitFor();
    assert.equal(await courseHistory.getByRole("button", { name: /Вопрос об отпуске/ }).count(), 0);
    await courseHistory.getByRole("button", { name: /Вопрос по курсу/ }).click();
    await reader.getByText("Ответ только по материалу курса").waitFor();
    await page.goto(`${origin}/#assistant`);
    await page.getByRole("button", { name: "Выйти из аккаунта" }).click();
    await page.getByRole("heading", { name: "Добро пожаловать" }).waitFor();
    await page.getByLabel("Рабочая почта").fill("aidana@example.com");
    await page.getByLabel("Пароль", { exact: true }).fill("synthetic-password");
    await page.getByRole("button", { name: /Войти в JanaМен/ }).click();
    await page.goto(`${origin}/#assistant`);
    if (width === 390) await page.getByRole("button", { name: "История диалогов", exact: true }).click();
    await page.getByRole("complementary", { name: "История диалогов AI Jana" }).getByRole("button", { name: /Вопрос об отпуске/ }).click();
    await page.getByText("Ответ по общему документу").waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.deepEqual(errors, []);
    await context.close();
  }
  for (const role of ["hr_admin", "manager"]) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await context.addInitScript(() => sessionStorage.setItem("jana-hr.access-token", "synthetic-reviewer-token"));
    const page = await context.newPage();
    await page.route("**/api/**", route => {
      const path = new URL(route.request().url()).pathname;
      const json = path === "/api/me" ? me(role) : path === "/api/courses/rewards" ? { xp: 0, level: 1, next_level_xp: 100, badges: [] } : [];
      return route.fulfill({ json });
    });
    await page.goto(origin);
    await page.getByRole("heading", { name: /Возможности/ }).waitFor();
    assert.equal(await page.getByRole("heading", { name: "Коллеги в отпуске" }).count(), 0);
    await context.close();
  }
  console.log("AI Jana history and employee home desktop/mobile browser checks passed.");
} finally { await browser.close(); }
