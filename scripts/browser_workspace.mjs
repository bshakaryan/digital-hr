/** Live UI regression. Creates demo requests, replaces and cancels one, restoring its days. */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE || "../frontend/node_modules/playwright");
const origin = process.env.WEB_URL || "http://127.0.0.1:3000";
const env = readFileSync(resolve(".env"), "utf8");
const password = process.env.DEMO_PASSWORD || env.match(/^DEMO_PASSWORD=(.+)$/m)?.[1]?.trim();
assert.ok(password);
const output = resolve("frontend/.qa/workspace");
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}) });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const errors = [], failures = [];
page.on("pageerror", error => errors.push(error.message));
page.on("response", response => { if (response.status() >= 500) failures.push(`${response.status()} ${response.url()}`); });
let employeeHeaders;
async function login(actor) {
  await page.getByLabel("Рабочая почта").fill(`${actor}@example.com`);
  await page.getByLabel("Пароль", { exact: true }).fill(password);
  const response = page.waitForResponse(response => response.url().endsWith("/api/auth/login"));
  await page.getByRole("button", { name: "Войти в JanaМен" }).click();
  await page.getByRole("button", { name: "JanaМен — главная", exact: true }).waitFor();
  return { Authorization: `Bearer ${(await (await response).json()).access_token}` };
}
async function logout() { await page.getByRole("button", { name: "Выйти из аккаунта" }).click(); await page.getByRole("heading", { name: "Добро пожаловать" }).waitFor(); }
async function tab(name) {
  if (name === "Уведомления") { await page.getByRole("button", { name: /^Уведомления/ }).first().click(); return; }
  if (await page.getByRole("button", { name: "Открыть меню", exact: true }).isVisible()) await page.getByRole("button", { name: "Открыть меню", exact: true }).click();
  await page.getByRole("navigation").getByRole("button", { name: new RegExp(`^${name}`) }).click();
  await page.waitForFunction(() => document.querySelector(".menu-button")?.getAttribute("aria-expanded") === "false");
}
async function detail(id) { const element = page.getByRole("dialog", { name: `Заявка №${id}`, exact: true }); await element.getByText("История заявки", { exact: true }).waitFor(); return element; }
async function close(id) { await (await detail(id)).getByRole("button", { name: "Закрыть", exact: true }).click(); }
async function review(id, comment) {
  const modal = await detail(id);
  await modal.getByLabel("Комментарий к решению").fill(comment);
  const response = page.waitForResponse(response => response.request().method() !== "GET" && response.url().includes(`/api/requests/${id}/`));
  await modal.getByRole("button", { name: "Подтвердить решение", exact: true }).click();
  const result = await response;
  assert.equal(result.status(), 200, await result.text());
  return result.json();
}
try {
  await page.goto(origin);
  employeeHeaders = await login("employee");
  const before = await (await context.request.get(`${origin}/api/me`, { headers: employeeHeaders })).json();
  const requests = await (await context.request.get(`${origin}/api/requests`, { headers: employeeHeaders })).json();
  const active = requests.filter(item => ["submitted", "manager_approved", "approved", "cancellation_requested"].includes(item.status));
  const free = Array.from({ length: 300 }, (_, index) => new Date(Date.UTC(2027, 1, index + 1)).toISOString().slice(0, 10)).filter(day => !["03-08", "03-21", "03-22", "03-23", "05-01", "05-07", "05-09", "07-06", "08-30", "10-25", "12-16"].includes(day.slice(5)) && !active.some(item => item.start_date <= day && item.end_date >= day));
  assert.ok(free.length >= 2 && before.leave_balance > 0);
  await tab("Главная");
  await page.getByRole("button", { name: "Создать заявку", exact: true }).click();
  const form = page.getByRole("dialog", { name: "Заявка на отпуск", exact: true });
  await form.getByLabel("Дата начала").fill(free[0]); await form.getByLabel("Дата окончания").fill(free[0]);
  await form.getByText(/По расчёту mock 1С:ЗУП/).waitFor();
  const creation = page.waitForResponse(response => response.url().endsWith("/api/requests") && response.request().method() === "POST");
  await form.getByRole("button", { name: "Отправить заявку", exact: true }).click();
  const original = await (await creation).json();
  await (await detail(original.id)).getByRole("button", { name: "Изменить даты", exact: true }).click();
  const replacementForm = page.getByRole("dialog", { name: `Изменение дат · заявка №${original.id}` });
  await replacementForm.getByLabel("Дата начала").fill(free[1]); await replacementForm.getByLabel("Дата окончания").fill(free[1]);
  await replacementForm.getByText(/По расчёту mock 1С:ЗУП/).waitFor();
  const replacing = page.waitForResponse(response => response.url().endsWith(`/api/requests/${original.id}/replace`));
  await replacementForm.getByRole("button", { name: "Отправить заявку", exact: true }).click();
  const replaced = await replacing;
  assert.equal(replaced.status(), 201, await replaced.text());
  const item = await replaced.json();
  assert.equal((await (await context.request.get(`${origin}/api/requests/${original.id}`, { headers: employeeHeaders })).json()).status, "withdrawn");
  await close(item.id);
  await tab("Уведомления");
  await page.getByRole("button", { name: `Открыть заявку №${item.id}`, exact: true }).first().click();
  await detail(item.id); await close(item.id);
  await logout(); await login("manager");
  await tab("Заявки");
  await page.getByRole("button", { name: /^Требуют моего решения/ }).waitFor();
  await page.getByRole("row").filter({ hasText: `№${item.id} ·` }).getByRole("button", { name: "Рассмотреть" }).waitFor();
  await page.screenshot({ path: `${output}/review-queue.png`, fullPage: true, animations: "disabled" });
  await tab("Календарь команды"); await page.getByLabel("Месяц").fill(free[1].slice(0, 7));
  await page.getByRole("button", { name: new RegExp(`заявка №${item.id}$`) }).click();
  await close(item.id); await tab("Заявки");
  await page.getByRole("row").filter({ hasText: `№${item.id} ·` }).getByRole("button", { name: "Рассмотреть" }).click();
  assert.equal((await review(item.id, "Доступность команды проверена")).status, "manager_approved");
  await close(item.id); await logout(); await login("hr"); await tab("Заявки");
  await page.getByRole("row").filter({ hasText: `№${item.id} ·` }).getByRole("button", { name: "Рассмотреть" }).click();
  assert.equal((await review(item.id, "Финальное согласование")).status, "approved");
  await close(item.id); await logout(); employeeHeaders = await login("employee");
  await tab("Уведомления"); await page.getByRole("button", { name: `Открыть заявку №${item.id}`, exact: true }).first().click();
  const approvedDetail = await detail(item.id);
  await approvedDetail.getByRole("button", { name: "Запросить отмену отпуска", exact: true }).click();
  await approvedDetail.getByLabel("Причина", { exact: true }).fill("Планы изменились — браузерная проверка");
  await approvedDetail.getByRole("button", { name: "Подтвердить", exact: true }).click();
  await approvedDetail.getByText("Запрошена отмена", { exact: true }).waitFor();
  await close(item.id); await logout(); await login("hr"); await tab("Заявки");
  await page.getByRole("row").filter({ hasText: `№${item.id} ·` }).getByRole("button", { name: "Рассмотреть" }).click();
  const cancelled = await review(item.id, "Отмена проверена HR");
  assert.equal(cancelled.status, "cancelled"); assert.equal(cancelled.cancellation_sync_status, "synced");
  await (await detail(item.id)).getByText(/Возврат подтверждён:/).waitFor();
  await page.screenshot({ path: `${output}/cancelled-refund.png`, fullPage: true, animations: "disabled" });
  await close(item.id);
  assert.equal((await (await context.request.get(`${origin}/api/me`, { headers: employeeHeaders })).json()).leave_balance, before.leave_balance);
  await tab("Журнал аудита"); await page.getByLabel("Тип события").selectOption("request.cancelled");
  await page.getByText("HR подтвердил отмену", { exact: true }).first().waitFor();
  const download = page.waitForEvent("download"); await page.getByRole("button", { name: "Скачать CSV", exact: true }).click();
  assert.equal((await download).suggestedFilename(), "jana-audit.csv");
  await page.screenshot({ path: `${output}/audit.png`, fullPage: true, animations: "disabled" });
  await tab("Команда"); await page.getByLabel("Поиск", { exact: true }).fill("Айдана");
  await page.getByRole("button", { name: /Айдана Демо Координатор/ }).click();
  await page.getByRole("heading", { name: "Связи в команде", exact: true }).waitFor();
  await page.getByRole("dialog").getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByLabel("Поиск", { exact: true }).fill(""); await page.getByRole("button", { name: "Структура", exact: true }).click();
  await page.screenshot({ path: `${output}/team-structure.png`, fullPage: true, animations: "disabled" });
  await tab("Интеграции и очереди"); await page.getByRole("heading", { name: "Интеграция 1С:ЗУП", exact: true }).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  await tab("Календарь команды"); await page.getByLabel("Месяц").fill(free[1].slice(0, 7));
  assert.equal(await page.getByRole("button", { name: new RegExp(`заявка №${item.id}$`) }).count(), 0);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.screenshot({ path: `${output}/calendar-mobile.png`, fullPage: true, animations: "disabled" });
  await tab("Уведомления"); await page.getByRole("button", { name: "Прочитать все", exact: true }).click();
  await page.getByRole("button", { name: "Непрочитанные", exact: true }).click(); await page.getByRole("heading", { name: "Всё прочитано", exact: true }).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  assert.deepEqual(errors, []); assert.deepEqual(failures, []);
  console.log(JSON.stringify({ ok: true, replaced: original.id, request: item.id, refund: cancelled.cancellation_reference, balance_restored: true, mobile_overflow: false }));
} catch (error) {
  await page.screenshot({ path: `${output}/failure.png`, fullPage: true, animations: "disabled" });
  throw error;
} finally { await browser.close(); }
