/** Org chart UI regression with synthetic read-only API fixtures; no database writes. */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE || "../frontend/node_modules/playwright");
const origin = process.env.WEB_URL || "http://127.0.0.1:3000";
const output = resolve("frontend/.qa/structure");
mkdirSync(output, { recursive: true });
const person = (id, full_name, manager_id, role = "employee", department = "Операции") => ({
  id, full_name, manager_id, role, department, email: `structure-${id}@example.com`,
  position: role === "employee" ? "Специалист" : "Руководитель подразделения", company: "Демо-компания",
  manager_name: null, hire_date: "2024-01-01", leave_balance: 24, data_source: "mock_zup",
});
const people = [
  person(100, "Демо Директор", null, "hr_admin", "Управление"),
  person(101, "Демо Руководитель А", 100, "manager"),
  person(102, "Демо Руководитель Б", 100, "manager", "Развитие"),
  person(103, "Демо Специалист А", 101),
  person(104, "Демо Специалист Б", 102, "employee", "Развитие"),
  person(105, "Демо Независимый", null),
  person(106, "Демо Неполная связь", 999),
  person(107, "Демо Цикл А", 108, "manager"),
  person(108, "Демо Цикл Б", 107, "manager"),
  person(109, "Демо Своя связь", 109),
];
const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}) });
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.addInitScript(() => sessionStorage.setItem("jana-hr.access-token", "synthetic-structure-ui-token"));
  const page = await context.newPage();
  const errors = [], calls = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/**", async route => {
    const request = route.request();
    assert.equal(request.method(), "GET", "The structure must not mutate personnel data");
    const path = new URL(request.url()).pathname;
    calls.push(path);
    const json = path === "/api/me" ? people[0] : path === "/api/employees" ? people
      : path === "/api/courses/rewards" ? { xp: 0, level: 1, next_level_xp: 100, badges: [] } : [];
    await route.fulfill({ json });
  });
  await page.goto(`${origin}/#team`);
  await page.getByRole("button", { name: "Структура", exact: true }).click();
  const cards = page.locator(".org-chart-card");
  await cards.first().waitFor();
  assert.equal(await cards.count(), 5, "Only independent roots are initially visible");
  const director = () => page.getByRole("button", { name: /^(Показать|Скрыть) подчинённых: Демо Директор$/ });
  await director().focus();
  await page.keyboard.press("Enter");
  assert.equal(await director().getAttribute("aria-expanded"), "true");
  assert.equal(await cards.count(), 7, "One click reveals direct reports only");
  await page.getByRole("button", { name: "Показать подчинённых: Демо Руководитель А", exact: true }).click();
  assert.equal(await cards.count(), 8);
  assert.equal(await page.locator(".org-chart-identity strong").getByText("Демо Специалист Б", { exact: true }).count(), 0);
  await director().focus();
  await page.keyboard.press("Space");
  assert.equal(await cards.count(), 5, "Collapsing a manager hides the entire branch");
  await page.getByRole("button", { name: "Развернуть всё", exact: true }).click();
  assert.equal(await cards.count(), people.length, "Cycles and missing managers must not lose or duplicate profiles");
  assert.equal(new Set(await page.locator(".org-chart-identity strong").allTextContents()).size, people.length);
  await page.screenshot({ path: `${output}/desktop.png`, fullPage: true });
  await page.locator(".org-chart-profile").filter({ hasText: "Профиль" }).first().click();
  await page.getByRole("dialog", { name: "Профиль сотрудника", exact: true }).waitFor();
  await page.getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByLabel("Поиск", { exact: true }).fill("Демо Специалист А");
  assert.equal(await cards.count(), 3, "Searching reveals the match and its authorized ancestors");
  assert.equal(await director().getAttribute("aria-expanded"), "true");
  await page.getByRole("button", { name: "Свернуть всё", exact: true }).click();
  assert.equal(await cards.count(), 1, "Search paths can also be collapsed");
  await page.getByRole("button", { name: "Развернуть всё", exact: true }).click();
  assert.equal(await cards.count(), 3);
  await page.getByLabel("Поиск", { exact: true }).fill("Нет такого сотрудника");
  await page.getByRole("heading", { name: "Сотрудники не найдены", exact: true }).waitFor();
  await page.getByLabel("Поиск", { exact: true }).fill("");
  await page.getByLabel("Подразделение").selectOption("Развитие");
  assert.equal(await cards.count(), 3);
  await page.getByLabel("Подразделение").selectOption("");
  await page.getByLabel("Роль").selectOption("manager");
  assert.equal(await cards.count(), 5, "Role filters retain the authorized HR ancestor of managers");
  assert.ok(await page.locator(".org-chart-card.is-context").count() > 0);
  await page.getByLabel("Роль").selectOption("");
  await page.getByRole("button", { name: "Развернуть всё", exact: true }).click();
  for (let step = 0; step < 2; step++) await page.getByRole("button", { name: "Уменьшить масштаб", exact: true }).click();
  assert.equal(await page.getByRole("button", { name: "Уменьшить масштаб", exact: true }).isDisabled(), true);
  await page.getByRole("button", { name: "Сбросить масштаб", exact: true }).click();
  assert.equal(await page.getByRole("button", { name: "Сбросить масштаб", exact: true }).textContent(), "100%");
  for (let step = 0; step < 2; step++) await page.getByRole("button", { name: "Увеличить масштаб", exact: true }).click();
  assert.equal(await page.getByRole("button", { name: "Увеличить масштаб", exact: true }).isDisabled(), true);
  await page.getByRole("button", { name: "Сбросить масштаб", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.locator(".org-chart-viewport").evaluate(element => { element.scrollLeft = element.scrollWidth; });
  assert.ok(await page.locator(".org-chart-viewport").evaluate(element => element.scrollLeft > 0));
  await page.getByRole("button", { name: "Свернуть всё", exact: true }).click();
  assert.equal(await cards.count(), 5);
  await page.locator(".org-chart-viewport").evaluate(element => { element.scrollLeft = 0; });
  await page.screenshot({ path: `${output}/mobile.png`, fullPage: true });
  await page.getByRole("button", { name: "Карточки", exact: true }).click();
  assert.equal(await page.locator(".team-grid .person-card").count(), people.length);
  await page.getByRole("button", { name: "Структура", exact: true }).click();
  assert.equal(await cards.count(), 5);
  assert.ok(!calls.some(path => /employees\/.+/.test(path)), "Expanding branches must use only the authorized directory response");
  assert.deepEqual(errors, []);
  console.log("Structure UI passed: progressive branches, keyboard, profiles, search/department/role ancestors, cycles, missing managers, zoom limits/reset, cards toggle, desktop and 390px scrolling; synthetic GET fixtures only.");
} finally { await browser.close(); }
