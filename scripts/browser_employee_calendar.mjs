/** Personal calendar UI regression with synthetic GET fixtures; no database writes. */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE || "../frontend/node_modules/playwright");
const origin = process.env.WEB_URL || "http://127.0.0.1:3000";
const output = resolve("frontend/.qa/employee-calendar");
mkdirSync(output, { recursive: true });
const people = [100, 101, 102].map(id => ({ id, full_name: `Демо Сотрудник ${id}`, email: `calendar-${id}@example.com`,
  role: id === 100 ? "hr_admin" : "employee", position: id === 100 ? "HR" : "Специалист", company: "Демо-компания", department: "Команда",
  manager_id: id === 100 ? null : 100, manager_name: id === 100 ? null : "Демо Сотрудник 100", hire_date: "2024-01-01", leave_balance: 24, data_source: "mock_zup" }));
function leave(id, employee_id, status, start_date, end_date = start_date) {
  return { id, employee_id, employee_name: people.find(person => person.id === employee_id).full_name,
    type: "leave", status, start_date, end_date, days_count: 3, calendar_days: 3, excluded_dates: [], calendar_version: "test-fixture",
    approval_route: "standard", can_review: false, cancellation_allowed: false, cancellation_block_reason: "Демонстрационная проверка", cancellation_sync_status: null,
    cancellation_reference: null, zup_sync_status: status === "approved" ? "legacy" : "not_required", zup_reference: null,
    comment: "Вымышленная заявка для проверки интерфейса", version: 1, created_at: "2026-10-17T00:00:00Z", history: [] };
}
const requests = [leave(1001, 100, "approved", "2026-12-30", "2027-01-02"),
  leave(1011, 101, "approved", "2027-01-11", "2027-01-15"), leave(1012, 101, "submitted", "2027-01-14", "2027-01-16"),
  leave(1013, 101, "rejected", "2027-01-20"), leave(1014, 101, "cancelled", "2027-01-22"), leave(1015, 101, "withdrawn", "2027-01-23"),
  leave(1016, 101, "manager_approved", "2027-01-18"), leave(1017, 101, "cancellation_requested", "2027-01-25"),
  leave(1021, 102, "approved", "2027-01-11", "2027-01-13")];
const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}) });

async function setup(me = people[0], failRequests = false) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, timezoneId: "Asia/Almaty" });
  await context.addInitScript(() => sessionStorage.setItem("jana-hr.access-token", "synthetic-personal-calendar-token"));
  const page = await context.newPage();
  const errors = [], calls = [];
  let failCalendar = false;
  const directory = me.role === "employee" ? [me] : people.map(person => person.id === me.id ? me : person);
  const visible = me.role === "employee" ? requests.filter(item => item.employee_id === me.id) : requests;
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/**", async route => {
    assert.equal(route.request().method(), "GET", "Calendar browsing must not mutate data");
    const url = new URL(route.request().url());
    const path = url.pathname;
    calls.push(path);
    if (path === "/api/requests" && failRequests) return route.fulfill({ status: 503, json: { detail: "Тестовый временный сбой" } });
    if (path === "/api/calendar" && failCalendar) return route.fulfill({ status: 503, json: { detail: "Тестовый сбой общего календаря" } });
    const month = url.searchParams.get("month");
    const end = month ? `${month}-${new Date(Date.UTC(Number(month.slice(0, 4)), Number(month.slice(5)), 0)).getUTCDate()}` : "";
    const shared = { month, employees: people.map(person => ({ id: person.id, full_name: person.full_name, department: person.department,
      can_open_profile: directory.some(allowed => allowed.id === person.id) })),
      absences: requests.filter(item => ["submitted", "manager_approved", "approved", "cancellation_requested"].includes(item.status)
        && item.start_date <= end && item.end_date >= `${month}-01`).map(item => ({ id: item.id, employee_id: item.employee_id,
        start_date: item.start_date, end_date: item.end_date, status: item.status, can_open_request: visible.some(allowed => allowed.id === item.id) })) };
    let json = path === "/api/calendar" ? shared : path === "/api/me" ? me : path === "/api/employees" ? directory : path === "/api/requests" ? visible
      : path === "/api/courses/rewards" ? { xp: 0, level: 1, next_level_xp: 100, badges: [] } : [];
    if (/^\/api\/requests\/\d+$/.test(path)) {
      json = visible.find(item => item.id === Number(path.split("/").at(-1)));
      if (!json) return route.fulfill({ status: 404, json: { detail: "Заявка не найдена" } });
    } else if (path.endsWith("/documentolog")) json = { mode: "disabled", status: "not_created" };
    await route.fulfill({ json });
  });
  return { context, page, errors, calls, recover: () => { failRequests = false; failCalendar = false; }, failCalendar: () => { failCalendar = true; } };
}

try {
  const { page, context, errors, calls } = await setup();
  await page.goto(`${origin}/#team`);
  await page.getByRole("button", { name: "Открыть календарь: Демо Сотрудник 101", exact: true }).click();
  const calendar = () => page.getByRole("region", { name: "Календарь сотрудника: Демо Сотрудник 101", exact: true });
  await calendar().waitFor();
  assert.ok(page.url().endsWith("#team/101/calendar"));
  await calendar().getByLabel("Месяц личного календаря", { exact: true }).fill("2027-01");
  const requestIds = async () => calendar().locator(".employee-calendar-request").evaluateAll(nodes => nodes.map(node => node.getAttribute("aria-label")));
  assert.deepEqual(await requestIds(), [1011, 1012, 1016, 1017].map(id => `Открыть заявку №${id}`));
  assert.equal(await calendar().locator('time[datetime="2027-01-01"]').locator("..").evaluate(node => node.cellIndex), 4);
  assert.equal(await calendar().locator('time[datetime="2027-01-14"]').locator("..").locator(".employee-calendar-event").count(), 2);
  assert.equal(await calendar().locator('time[datetime="2027-01-16"]').locator("..").getAttribute("class"), "is-weekend");
  await calendar().getByLabel("Показывать отклонённые, отозванные и отменённые").check();
  assert.equal((await requestIds()).length, 7);
  await calendar().getByLabel("Показывать отклонённые, отозванные и отменённые").uncheck();
  await page.screenshot({ path: `${output}/desktop.png`, fullPage: true });
  await calendar().locator('.employee-calendar-event[title^="№1011 "]').first().click();
  const detail = page.getByRole("dialog", { name: "Заявка №1011", exact: true });
  await detail.getByText("История заявки", { exact: true }).waitFor();
  await detail.getByRole("button", { name: "Закрыть", exact: true }).click();
  await calendar().waitFor();
  assert.equal(await calendar().getByLabel("Месяц личного календаря", { exact: true }).inputValue(), "2027-01");
  await calendar().getByLabel("Месяц личного календаря", { exact: true }).fill("2026-12");
  await calendar().getByRole("button", { name: "Следующий месяц", exact: true }).click();
  assert.equal(await calendar().getByLabel("Месяц личного календаря", { exact: true }).inputValue(), "2027-01");
  await calendar().getByLabel("Месяц личного календаря", { exact: true }).fill("2028-02");
  assert.equal(await calendar().locator("time").count(), 29);
  await calendar().getByText("В этом месяце действующих заявок на отпуск нет.", { exact: true }).waitFor();
  await page.reload();
  await calendar().waitFor();
  await page.getByRole("dialog", { name: "Профиль сотрудника", exact: true }).getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByRole("button", { name: "Структура", exact: true }).click();
  await page.getByRole("button", { name: "Показать подчинённых: Демо Сотрудник 100", exact: true }).click();
  await page.getByRole("button", { name: "Открыть календарь: Демо Сотрудник 102", exact: true }).click();
  const other = page.getByRole("region", { name: "Календарь сотрудника: Демо Сотрудник 102", exact: true });
  await other.getByLabel("Месяц личного календаря", { exact: true }).fill("2027-01");
  assert.equal(await other.locator(".employee-calendar-request").count(), 1);
  assert.equal(await other.getByRole("button", { name: "Открыть заявку №1021", exact: true }).count(), 1);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert.ok(await page.getByRole("dialog", { name: "Профиль сотрудника", exact: true }).evaluate(node => node.scrollWidth <= node.clientWidth));
  await page.screenshot({ path: `${output}/mobile.png`, fullPage: true });
  await page.getByRole("dialog", { name: "Профиль сотрудника", exact: true }).getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`${origin}/#calendar`);
  await page.getByRole("button", { name: "Открыть календарь: Демо Сотрудник 101", exact: true }).click();
  await calendar().waitFor();
  await page.getByRole("dialog", { name: "Профиль сотрудника", exact: true }).getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.goto(`${origin}/#profile/calendar`);
  const mine = page.getByRole("region", { name: "Календарь сотрудника: Демо Сотрудник 100", exact: true });
  await mine.getByLabel("Месяц личного календаря", { exact: true }).fill("2027-01");
  assert.equal(await mine.locator(".employee-calendar-request").count(), 1);
  assert.equal(await mine.locator(".employee-calendar-event").count(), 2, "A leave crossing years is clipped to the selected month");
  await mine.getByRole("button", { name: "Предыдущий месяц", exact: true }).click();
  assert.equal(await mine.locator(".employee-calendar-event").count(), 2);
  await mine.getByRole("button", { name: "Открыть заявку №1001", exact: true }).click();
  const ownDetail = page.getByRole("dialog", { name: "Заявка №1001", exact: true });
  await ownDetail.getByText("История заявки", { exact: true }).waitFor();
  await ownDetail.getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByRole("heading", { name: "Календарь сотрудников", exact: true }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Мой календарь", exact: true }).getAttribute("aria-pressed"), "true");
  assert.equal(await mine.getByLabel("Месяц личного календаря", { exact: true }).inputValue(), "2026-12");
  assert.deepEqual(errors, []);
  assert.ok(!calls.some(path => /employees\/.+/.test(path)), "Person calendars must reuse the authorized data");
  await context.close();

  const own = await setup(people[1]);
  await own.page.goto(`${origin}/#profile`);
  await own.page.getByRole("button", { name: "Мой календарь", exact: true }).click();
  await own.page.getByRole("heading", { name: "Календарь сотрудников", exact: true }).waitFor();
  assert.equal(await own.page.getByRole("button", { name: "Мой календарь", exact: true }).getAttribute("aria-pressed"), "true");
  await own.page.getByLabel("Месяц личного календаря", { exact: true }).fill("2027-01");
  assert.equal(await own.page.locator(".employee-calendar-request").count(), 4);
  assert.equal(await own.page.locator('.employee-calendar-event[title^="№1021 "]').count(), 0);
  await own.page.getByRole("button", { name: "Общий", exact: true }).click();
  await own.page.locator(".team-calendar").waitFor();
  assert.equal(await own.page.locator(".team-calendar tbody tr").count(), 3);
  assert.equal(await own.page.locator('.absence[role="img"]').count(), 5, "Colleagues' leave dates are shared without opening private requests");
  assert.equal(await own.page.getByRole("button", { name: "Открыть календарь: Демо Сотрудник 102", exact: true }).count(), 0);
  assert.equal(await own.page.getByRole("button", { name: /заявка №1021$/ }).count(), 0);
  assert.equal(await own.page.getByRole("switch").count(), 0);
  assert.equal(await own.page.getByLabel("Месяц", { exact: true }).inputValue(), "2027-01");
  await own.page.getByRole("button", { name: "Открыть календарь: Демо Сотрудник 101", exact: true }).click();
  assert.equal(await own.page.getByRole("button", { name: "Мой календарь", exact: true }).getAttribute("aria-pressed"), "true");
  await own.page.goto(`${origin}/#team/102/calendar`);
  await own.page.getByRole("heading", { name: /Сәлем/ }).waitFor();
  assert.equal(await own.page.locator(".employee-calendar").count(), 0);
  assert.deepEqual(own.errors, []);
  await own.context.close();

  for (const me of [{ ...people[0], role: "manager" }, people[0]]) {
    const unified = await setup(me);
    await unified.page.goto(origin);
    await unified.page.getByRole("navigation").getByRole("button", { name: "Календарь сотрудников", exact: true }).click();
    await unified.page.locator(".team-calendar").waitFor();
    assert.equal(await unified.page.locator(".team-calendar tbody tr").count(), 3);
    const mineButton = unified.page.getByRole("button", { name: "Мой календарь", exact: true });
    const commonButton = unified.page.getByRole("button", { name: "Общий", exact: true });
    assert.equal(await mineButton.getAttribute("aria-pressed"), "false");
    await unified.page.getByLabel("Месяц", { exact: true }).fill("2027-01");
    await unified.page.locator('.team-calendar caption').filter({ hasText: "2027-01" }).waitFor({ state: "attached" });
    if (me.role === "hr_admin") await unified.page.screenshot({ path: `${output}/unified-employees.png`, fullPage: true });
    await mineButton.focus();
    await unified.page.keyboard.press("Space");
    assert.equal(await mineButton.getAttribute("aria-pressed"), "true");
    assert.ok(unified.page.url().endsWith("#calendar/mine"));
    assert.equal(await unified.page.getByLabel("Месяц личного календаря", { exact: true }).inputValue(), "2027-01");
    assert.equal(await unified.page.locator(".employee-calendar-request").count(), 1);
    assert.equal(await unified.page.locator(".employee-calendar-event").count(), 2);
    assert.equal(await unified.page.getByRole("button", { name: "Открыть заявку №1001", exact: true }).count(), 1);
    assert.equal(await unified.page.locator(".calendar-balance strong").textContent(), "24 дн.");
    await unified.page.getByRole("button", { name: "Следующий месяц", exact: true }).click();
    await commonButton.click();
    assert.equal(await unified.page.getByLabel("Месяц", { exact: true }).inputValue(), "2027-02");
    await mineButton.click();
    assert.equal(await unified.page.getByLabel("Месяц личного календаря", { exact: true }).inputValue(), "2027-02");
    await unified.page.reload();
    await unified.page.locator(".employee-calendar-month").waitFor();
    assert.equal(await mineButton.getAttribute("aria-pressed"), "true");
    await unified.page.getByLabel("Месяц личного календаря", { exact: true }).fill("2027-01");
    if (me.role === "hr_admin") {
      await unified.page.screenshot({ path: `${output}/unified-mine.png`, fullPage: true });
      await unified.page.setViewportSize({ width: 390, height: 844 });
      await unified.page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      assert.ok(await unified.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await unified.page.screenshot({ path: `${output}/unified-mobile.png`, fullPage: true });
      await commonButton.click();
      assert.ok(await unified.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    }
    assert.deepEqual(unified.errors, []);
    await unified.context.close();
  }

  const commonFailure = await setup(people[1]);
  await commonFailure.page.goto(`${origin}/#calendar`);
  await commonFailure.page.getByLabel("Месяц", { exact: true }).fill("2027-01");
  await commonFailure.page.locator('.team-calendar caption').filter({ hasText: "2027-01" }).waitFor({ state: "attached" });
  commonFailure.failCalendar();
  await commonFailure.page.getByLabel("Месяц", { exact: true }).fill("2027-02");
  await commonFailure.page.getByRole("alert").getByText(/Не удалось обновить общий календарь/).waitFor();
  assert.equal(await commonFailure.page.locator(".team-calendar").count(), 0);
  assert.equal(await commonFailure.page.getByText("В выбранном месяце заявок нет.", { exact: true }).count(), 0);
  commonFailure.recover();
  await commonFailure.page.getByRole("button", { name: /Попробовать снова/ }).click();
  await commonFailure.page.locator('.team-calendar caption').filter({ hasText: "2027-02" }).waitFor({ state: "attached" });
  assert.equal(await commonFailure.page.locator(".absence").count(), 0);
  assert.deepEqual(commonFailure.errors, []);
  await commonFailure.context.close();

  const failure = await setup(people[0], true);
  await failure.page.goto(`${origin}/#team/101/calendar`);
  await failure.page.getByRole("alert").getByText(/Не удалось обновить календарь/).waitFor();
  assert.equal(await failure.page.locator(".employee-calendar-month").count(), 0);
  assert.equal(await failure.page.getByText(/В этом месяце .*заявок на отпуск нет/).count(), 0);
  failure.recover();
  await failure.page.getByRole("button", { name: /Попробовать снова/ }).click();
  await failure.page.locator(".employee-calendar-month").waitFor();
  assert.deepEqual(failure.errors, []);
  await failure.context.close();
  console.log("Employee calendars passed: all-role navigation, shared colleague dates, two mode buttons and shared month, own-only days/balance, cards/structure/profile, statuses/history, request return, deep links, leap/cross-year dates, error/retry and 390px layout; synthetic GET fixtures only.");
} finally { await browser.close(); }
