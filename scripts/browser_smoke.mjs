/** Run against a running local stack with demo seed; this creates one demo request.
 * Install optional runner: npm install --prefix frontend --no-save --package-lock=false playwright
 * Then: npx --prefix frontend playwright install chromium
 * Run from root: node scripts/browser_smoke.mjs
 * PLAYWRIGHT_PACKAGE may point to an already installed Playwright package.
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE || "../frontend/node_modules/playwright");
const origin = process.env.WEB_URL || "http://127.0.0.1:3000";
const env = readFileSync(resolve(".env"), "utf8");
const password = process.env.DEMO_PASSWORD || env.match(/^DEMO_PASSWORD=(.+)$/m)?.[1]?.trim();
assert.ok(password, "Set DEMO_PASSWORD or generate local .env");
const output = resolve("frontend/.qa/browser-smoke");
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}) });
const errors = [];
const serverErrors = [];
let lastPage;

async function login(page, actor) {
  await page.getByLabel("Рабочая почта").fill(`${actor}@example.com`);
  await page.getByLabel("Пароль", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Войти в JanaМен" }).click();
  await page.getByRole("heading", { name: /Сәлем,/ }).waitFor();
}
async function logout(page) {
  await page.getByRole("button", { name: "Выйти из аккаунта" }).click();
  await page.getByRole("heading", { name: "Добро пожаловать" }).waitFor();
}
async function tab(page, name) {
  await page.getByRole("navigation").getByRole("button", { name: new RegExp("^" + name) }).click();
}
function watch(page) {
  lastPage = page;
  page.on("pageerror", error => errors.push(error.message));
  page.on("response", response => { if (response.status() >= 500) serverErrors.push(`${response.status()} ${response.url()}`); });
}

try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  watch(page);
  await page.goto(origin);
  await page.screenshot({ path: `${output}/login-desktop.png`, fullPage: true });
  await login(page, "employee");
  await page.getByRole("button", { name: "Создать заявку", exact: true }).waitFor();
  await page.getByRole("heading", { name: "Знакомство с JanaМен", exact: true }).waitFor();
  await page.screenshot({ path: `${output}/dashboard-desktop.png`, fullPage: true });
  await tab(page, "Мой профиль");
  await page.getByText("Арман Демо", { exact: true }).waitFor();
  await tab(page, "Главная");
  await page.getByRole("button", { name: "Создать заявку", exact: true }).click();
  const form = page.getByRole("dialog", { name: "Заявка на отпуск", exact: true });
  await form.getByLabel("Дата начала").fill("2027-03-01");
  await form.getByLabel("Дата окончания").fill("2027-03-05");
  await form.getByLabel(/Комментарий/).fill("Браузерная проверка сквозного сценария");
  const creation = page.waitForResponse(r => r.url().endsWith("/api/requests") && r.request().method() === "POST");
  await form.getByRole("button", { name: "Отправить заявку" }).click();
  const response = await creation;
  assert.equal(response.status(), 201);
  const request = await response.json();
  const detail = page.getByRole("dialog", { name: `Заявка №${request.id}`, exact: true });
  await detail.getByText("История заявки", { exact: true }).waitFor();
  assert.equal(await detail.getByText("Подтвердить решение", { exact: true }).count(), 0);
  await detail.getByRole("button", { name: "Закрыть", exact: true }).click();

  await tab(page, "Jana Academy");
  await page.getByRole("button", { name: /^(Начать обучение|Продолжить|Повторить материал)$/ }).click();
  const course = page.getByRole("dialog", { name: "Jana Academy · Обучение" });
  await course.getByRole("heading", { name: "Знакомство с JanaМен" }).waitFor();
  if (!(await course.getByRole("heading", { name: "Курс завершён" }).count())) {
    const read = course.getByRole("button", { name: "Материал изучен — перейти к тесту" });
    if (await read.count()) await read.click();
    await course.getByLabel("Только позвонить курьеру").check();
    await course.getByRole("button", { name: "Отправить ответ" }).click();
    await course.getByRole("alert").filter({ hasText: "Ответ неверный" }).waitFor();
    await course.getByLabel("В карточке заявки и уведомлениях").check();
    await course.getByRole("button", { name: "Отправить ответ" }).click();
    await course.getByRole("heading", { name: "Курс завершён" }).waitFor();
  }
  await course.getByRole("button", { name: "Закрыть", exact: true }).click();
  await tab(page, "HR-помощник");
  await page.getByRole("button", { name: "Как подать заявку на отпуск?", exact: true }).click();
  await page.getByRole("button", { name: /Как подать заявку на отпуск Заявки/ }).click();
  const source = page.getByRole("dialog", { name: "Источник ответа" });
  await source.getByRole("heading", { name: "Как подать заявку на отпуск" }).waitFor();
  await source.getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByLabel("Ваш вопрос").fill("Какая погода на Марсе?");
  await page.getByRole("button", { name: "Отправить вопрос" }).click();
  await page.getByText(/В демонстрационной базе нет надёжного ответа/).waitFor();

  await logout(page);
  await login(page, "manager");
  await tab(page, "Заявки");
  await page.getByRole("button", { name: "Заявки команды", exact: true }).click();
  await page.getByRole("row").filter({ hasText: `№${request.id} ·` }).getByRole("button", { name: "Рассмотреть" }).click();
  const review = page.getByRole("dialog", { name: `Заявка №${request.id}`, exact: true });
  await review.getByLabel("Комментарий к решению").fill("Проверено руководителем в браузере");
  const decision = page.waitForResponse(r => r.url().endsWith(`/api/requests/${request.id}/status`) && r.request().method() === "PATCH");
  await review.getByRole("button", { name: "Подтвердить решение" }).click();
  assert.equal((await decision).status(), 200);
  await review.getByText("Заявка согласована", { exact: true }).waitFor();
  await page.screenshot({ path: `${output}/request-approved.png`, fullPage: true });
  await review.getByRole("button", { name: "Закрыть", exact: true }).click();

  await logout(page);
  await login(page, "employee");
  await tab(page, "Уведомления");
  const notification = page.getByRole("article").filter({ hasText: `Заявка №${request.id}:` });
  await notification.getByRole("heading", { name: "Заявка одобрена" }).waitFor();
  const read = page.waitForResponse(r => r.url().endsWith("/read") && r.request().method() === "PATCH");
  await notification.getByRole("button", { name: "Прочитано" }).click();
  assert.equal((await read).status(), 200);
  await logout(page);
  await login(page, "hr");
  await tab(page, "Журнал аудита");
  await page.getByText("request.approved", { exact: true }).first().waitFor();
  await logout(page);
  await login(page, "outsider");
  assert.equal(await page.getByRole("navigation").getByRole("button", { name: "Команда", exact: true }).count(), 0);
  await tab(page, "Заявки");
  assert.equal(await page.getByRole("row").filter({ hasText: `№${request.id} ·` }).count(), 0);
  await tab(page, "Главная");
  await page.reload();
  await page.getByRole("heading", { name: "Добро пожаловать" }).waitFor();

  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const small = await mobile.newPage();
  watch(small);
  await small.goto(origin);
  await small.screenshot({ path: `${output}/login-mobile.png`, fullPage: true });
  await login(small, "employee");
  await small.getByRole("button", { name: "Создать заявку", exact: true }).waitFor();
  await small.getByRole("heading", { name: "Знакомство с JanaМен", exact: true }).waitFor();
  await small.screenshot({ path: `${output}/dashboard-mobile.png`, fullPage: true });
  assert.ok(await small.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "Mobile page overflows horizontally");
  await small.getByRole("button", { name: "Открыть меню" }).click();
  await tab(small, "Мой профиль");
  await small.getByRole("heading", { name: "Мой профиль", exact: true }).waitFor();
  await small.getByText("Арман Демо", { exact: true }).waitFor();
  assert.deepEqual(errors, [], "Browser JavaScript errors");
  assert.deepEqual(serverErrors, [], "HTTP server errors");
  console.log(`Browser smoke passed: request ${request.id}, employee → manager → employee, Academy, sources/refusal, session reset, mobile 390px. Screenshots: ${output}`);
} catch (error) {
  await lastPage?.screenshot({ path: `${output}/failure.png`, fullPage: true }).catch(() => {});
  throw error;
} finally {
  await browser.close();
}
