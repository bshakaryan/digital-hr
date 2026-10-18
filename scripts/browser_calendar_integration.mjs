/** Read-only calendar and leave UI smoke using synthetic API fixtures. */
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE || "playwright");
const origin = process.env.WEB_URL || "http://127.0.0.1:3000";
const me = { id: 101, full_name: "Демо Сотрудник", role: "employee", email: "demo@example.com", position: "Специалист", department: "Логистика", company: "Демо", manager_id: 1, manager_name: "Демо Руководитель", hire_date: "2024-01-01", leave_balance: 20, data_source: "mock_zup" };
const request = { id: 501, employee_id: 101, employee_name: me.full_name, type: "leave", status: "approved", start_date: "2027-01-11", end_date: "2027-01-13", days_count: 3, calendar_days: 3, excluded_dates: [], calendar_version: "test-fixture", approval_route: "manager_to_hr", can_review: false, cancellation_allowed: false, cancellation_block_reason: "Демонстрационная проверка", cancellation_sync_status: null, cancellation_reference: null, zup_sync_status: "legacy", zup_reference: null, comment: "Демонстрационная заявка", version: 1, created_at: "2026-10-17T00:00:00Z", history: [] };
const browser = await chromium.launch({ headless: true });
try {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, timezoneId: "Asia/Almaty" });
    await context.addInitScript(() => sessionStorage.setItem("jana-hr.access-token", "synthetic-calendar-token"));
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/api/**", route => {
      assert.equal(route.request().method(), "GET", "Smoke test must not mutate data");
      const url = new URL(route.request().url());
      const path = url.pathname;
      const month = url.searchParams.get("month");
      const json = path === "/api/me" ? me : path === "/api/requests" ? [request]
        : path === "/api/requests/501" ? request
        : path === "/api/calendar" ? { month, employees: [{ id: me.id, full_name: me.full_name, department: me.department, can_open_profile: true }], absences: month === "2027-01" ? [{ id: request.id, employee_id: me.id, start_date: request.start_date, end_date: request.end_date, status: request.status, can_open_request: true }] : [] }
        : path === "/api/employees" ? [me] : path === "/api/directory" ? []
        : path === "/api/courses/rewards" ? { xp: 0, level: 1, next_level_xp: 100, badges: [] } : [];
      return route.fulfill({ json });
    });
    await page.goto(`${origin}/#calendar`);
    await page.getByRole("heading", { name: "Календарь сотрудников", exact: true }).waitFor();
    await page.getByRole("button", { name: "Мой календарь", exact: true }).click();
    const mine = page.getByRole("region", { name: `Календарь сотрудника: ${me.full_name}` });
    await mine.waitFor();
    await mine.getByLabel("Месяц личного календаря", { exact: true }).fill("2027-01");
    assert.equal(await mine.getByRole("button", { name: "Открыть заявку №501" }).count(), 1);
    await mine.getByRole("button", { name: "Открыть заявку №501" }).click();
    const detail = page.getByRole("dialog", { name: "Заявка №501" });
    await detail.getByText("История заявки", { exact: true }).waitFor();
    await detail.getByRole("button", { name: "Закрыть" }).click();
    await page.getByRole("button", { name: "Общий", exact: true }).click();
    await page.locator(".team-calendar").waitFor();
    await page.goto(`${origin}/#requests`);
    await page.getByText("№501", { exact: false }).first().waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.deepEqual(errors, []);
    await context.close();
  }
  console.log("Calendar and leave UI desktop/mobile browser checks passed.");
} finally { await browser.close(); }
