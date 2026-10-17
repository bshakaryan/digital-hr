/** Run on an isolated seeded demo: this scenario clears that user's notification list. */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

assert.equal(process.env.NOTIFICATIONS_QA_ISOLATED, "1", "Use an isolated seeded demo with NOTIFICATIONS_QA_ISOLATED=1");
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE || "../frontend/node_modules/playwright");
const origin = process.env.WEB_URL || "http://127.0.0.1:13100";
const password = process.env.DEMO_PASSWORD;
assert.ok(password);
const output = resolve("frontend/.qa/notifications");
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}) });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [], failures = [];
page.on("pageerror", error => errors.push(error.message));
page.on("response", response => { if (response.status() >= 500) failures.push(`${response.status()} ${response.url()}`); });

async function login() {
  await page.getByLabel("Рабочая почта").fill("employee@example.com");
  await page.getByLabel("Пароль", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Войти в JanaМен", exact: true }).click();
  await page.getByRole("button", { name: "JanaМен — главная", exact: true }).waitFor();
}
async function tab(name) {
  if (name === "Уведомления") { await page.getByRole("button", { name: /^Уведомления/ }).first().click(); return; }
  if (await page.getByRole("button", { name: "Открыть меню", exact: true }).isVisible()) await page.getByRole("button", { name: "Открыть меню", exact: true }).click();
  await page.getByRole("navigation").getByRole("button", { name: new RegExp(`^${name}`) }).click();
  await page.waitForFunction(() => document.querySelector(".menu-button")?.getAttribute("aria-expanded") === "false");
}
async function count(expected) { await page.waitForFunction(value => document.querySelectorAll(".notification-card").length === value, expected); }
async function readTab() { await page.getByRole("button", { name: "Прочитанные", exact: true }).click(); }
async function unreadTab() { await page.getByRole("button", { name: "Непрочитанные", exact: true }).click(); }
async function mutation(button, path) {
  const response = page.waitForResponse(response => response.url().endsWith(path) && response.request().method() === "PATCH");
  await button.click();
  const result = await response;
  assert.equal(result.status(), 200, await result.text());
  return result.json();
}
try {
  await page.goto(origin); await login(); await tab("Уведомления");
  await page.locator(".notification-card").first().waitFor();
  assert.equal(await page.getByRole("button", { name: "Непрочитанные", exact: true }).getAttribute("aria-pressed"), "true");
  const total = await page.locator(".notification-card").count();
  assert.ok(total >= 3, "Expected a fresh seeded demo");
  const first = page.locator(".notification-card").first();
  const title = await first.getByRole("heading").innerText();
  const id = await mutation(first.getByRole("button", { name: "Прочитано", exact: true }), "/read");
  await count(total - 1);
  await readTab(); await count(1);
  assert.equal(await page.getByRole("heading", { name: title, exact: true }).count(), 1);
  await unreadTab(); await page.getByRole("button", { name: "Открыть курс", exact: true }).click();
  await page.waitForURL("**/#academy/1");
  const course = page.getByRole("dialog", { name: "Jana Academy · Обучение", exact: true });
  await course.getByRole("heading", { name: "Знакомство с JanaМен", exact: true }).waitFor();
  await course.getByRole("button", { name: "Закрыть", exact: true }).click();
  await tab("Уведомления"); await count(total - 2);
  await tab("Главная");
  assert.equal(await page.locator(".update-preview").count(), total - 2);
  await tab("Уведомления"); await readTab(); await count(2);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: `${output}/read-mobile.png`, fullPage: true, animations: "disabled" });

  // A failed request leaves the list intact and can be retried.
  await page.route("**/api/notifications/clear-read", route => route.fulfill({ status: 409, json: { detail: "Проверка: очистка временно недоступна" } }), { times: 1 });
  await page.getByRole("button", { name: "Очистить прочитанные", exact: true }).click();
  await page.getByText("Проверка: очистка временно недоступна", { exact: true }).waitFor(); await count(2);
  assert.equal((await mutation(page.getByRole("button", { name: "Очистить прочитанные", exact: true }), "/clear-read")).updated, 2);
  await page.getByRole("heading", { name: "Нет прочитанных уведомлений", exact: true }).waitFor();
  await unreadTab(); await count(total - 2);
  await page.reload(); await page.getByRole("button", { name: "JanaМен — главная", exact: true }).waitFor();
  await count(total - 2); await readTab(); await count(0);
  await page.getByRole("heading", { name: "Нет прочитанных уведомлений", exact: true }).waitFor();
  await unreadTab();
  assert.equal((await mutation(page.getByRole("button", { name: "Прочитать все", exact: true }), "/read-all")).updated, total - 2);
  await page.getByRole("heading", { name: "Всё прочитано", exact: true }).waitFor();
  await readTab(); await count(total - 2);
  await mutation(page.getByRole("button", { name: "Очистить прочитанные", exact: true }), "/clear-read");
  await page.getByRole("heading", { name: "Нет прочитанных уведомлений", exact: true }).waitFor();
  await page.screenshot({ path: `${output}/cleared-mobile.png`, fullPage: true, animations: "disabled" });
  await tab("Главная"); await page.getByText("Пока всё спокойно.", { exact: false }).waitFor();
  assert.equal(await page.locator(".update-preview").count(), 0);
  await page.setViewportSize({ width: 1440, height: 1000 }); await tab("Уведомления");
  await page.screenshot({ path: `${output}/empty-desktop.png`, fullPage: true, animations: "disabled" });
  assert.deepEqual(errors, []); assert.deepEqual(failures, []);
  console.log(JSON.stringify({ passed: true, notifications: total, first_read_id: id.id, screenshots: output, errors, failures }));
} catch (error) {
  await page.screenshot({ path: `${output}/failure.png`, fullPage: true, animations: "disabled" });
  throw error;
} finally { await browser.close(); }
