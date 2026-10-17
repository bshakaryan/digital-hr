/** Run against a running demo stack. Only logins (and their audit entries) are created. */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE || "../frontend/node_modules/playwright");
const origin = process.env.WEB_URL || "http://127.0.0.1:3100";
const password = process.env.DEMO_PASSWORD || readFileSync(resolve(".env"), "utf8").match(/^DEMO_PASSWORD=(.+)$/m)?.[1]?.trim();
assert.ok(password, "Set DEMO_PASSWORD or generate local .env");
const storageKey = "jana-hr.access-token";
const output = resolve("frontend/.qa/session");
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}) });
const errors = [];
let logins = 0;
let page;

async function login(actor = "employee") {
  await page.getByLabel("Рабочая почта").fill(`${actor}@example.com`);
  await page.getByLabel("Пароль", { exact: true }).fill(password);
  const response = page.waitForResponse(r => r.url().endsWith("/api/auth/login"));
  await page.getByRole("button", { name: "Войти в JanaМен", exact: true }).click();
  const token = (await (await response).json()).access_token;
  await signedIn();
  assert.equal(await storedToken(), token);
  return token;
}
async function signedIn() { await page.getByRole("button", { name: "Выйти из аккаунта", exact: true }).waitFor(); }
async function signedOut() { await page.getByRole("heading", { name: "Добро пожаловать", exact: true }).waitFor(); }
async function storedToken() { return page.evaluate(key => sessionStorage.getItem(key), storageKey); }
async function logout() {
  await page.getByRole("button", { name: "Выйти из аккаунта", exact: true }).click();
  await signedOut();
  assert.equal(await storedToken(), null);
}

try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  page = await context.newPage();
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => { if (request.url().endsWith("/api/auth/login")) logins++; });
  await page.goto(origin);
  await signedOut();
  const token = await login();
  await page.getByRole("navigation").getByRole("button", { name: "Мой профиль", exact: true }).click();

  // Hold /me to verify that neither login nor private UI flashes during restoration.
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route("**/api/me", async route => { await gate; await route.continue(); }, { times: 1 });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("status").filter({ hasText: "Восстанавливаем сессию…" }).waitFor();
  assert.equal(await page.getByRole("heading", { name: "Добро пожаловать", exact: true }).count(), 0);
  assert.equal(await page.getByRole("button", { name: "Выйти из аккаунта", exact: true }).count(), 0);
  release();
  await signedIn();
  await page.getByRole("heading", { name: "Мой профиль", exact: true }).waitFor();
  assert.equal(await storedToken(), token);
  assert.equal(logins, 1, "Reload must not issue a new login or JWT");
  assert.deepEqual(await page.evaluate(() => ({ session: Object.keys(sessionStorage), local: Object.keys(localStorage) })), { session: [storageKey], local: [] });
  await page.screenshot({ path: `${output}/restored-desktop.png`, fullPage: true });
  await page.goto(`${origin}/#requests`);
  await signedIn();
  assert.ok(page.url().endsWith("#requests"));

  // A separate tab without an opener has its own session storage.
  const separate = await context.newPage();
  await separate.goto(origin);
  await separate.getByRole("heading", { name: "Добро пожаловать", exact: true }).waitFor();
  await separate.close();

  // A temporary source/server failure and a network failure retain the token.
  for (const failure of ["503", "network"]) {
    await page.route("**/api/me", route => failure === "503"
      ? route.fulfill({ status: 503, json: { detail: "Источник временно недоступен" } })
      : route.abort("failed"), { times: 1 });
    await page.reload();
    await page.getByRole("heading", { name: "Не удалось загрузить профиль", exact: true }).waitFor();
    assert.equal(await storedToken(), token);
    await page.getByRole("button", { name: "Попробовать снова" }).click();
    await signedIn();
    assert.equal(await storedToken(), token);
    assert.equal(logins, 1);
  }

  // An expired/rejected session is cleared when /me responds 401.
  await page.route("**/api/me", route => route.fulfill({ status: 401, json: { detail: "Войдите в систему" } }), { times: 1 });
  await page.reload();
  await signedOut();
  await page.getByText("Сессия завершена. Войдите снова, чтобы продолжить.", { exact: true }).waitFor();
  assert.equal(await storedToken(), null);
  await page.reload();
  await signedOut();

  // A corrupted token also goes through the real backend validation.
  await page.evaluate(key => sessionStorage.setItem(key, "not.a.jwt"), storageKey);
  await page.reload();
  await signedOut();
  assert.equal(await storedToken(), null);

  // A late 401 from an old account must not clear a new account's token.
  let releaseOld, markStarted, markCompleted;
  const oldGate = new Promise(resolve => { releaseOld = resolve; });
  const started = new Promise(resolve => { markStarted = resolve; });
  const completed = new Promise(resolve => { markCompleted = resolve; });
  await page.route("**/api/requests", async route => {
    markStarted();
    await oldGate;
    await route.fulfill({ status: 401, json: { detail: "Войдите в систему" } });
    markCompleted();
  }, { times: 1 });
  await login();
  await started;
  await logout();
  const hrToken = await login("hr");
  releaseOld();
  await completed;
  await page.waitForLoadState("networkidle");
  await signedIn();
  assert.equal(await storedToken(), hrToken);
  await page.reload();
  await signedIn();
  await page.getByRole("navigation").getByRole("button", { name: "Журнал аудита", exact: true }).waitFor();
  await logout();
  await page.reload();
  await signedOut();

  // Any authenticated API 401 also clears the stored token.
  await login();
  await page.waitForLoadState("networkidle");
  await page.route("**/api/requests", route => route.fulfill({ status: 401, json: { detail: "Войдите в систему" } }), { times: 1 });
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await signedOut();
  assert.equal(await storedToken(), null);

  // The mobile viewport restores the same session and route.
  await page.setViewportSize({ width: 390, height: 844 });
  await login();
  await page.goto(`${origin}/#profile`);
  await signedIn();
  await page.getByRole("heading", { name: "Мой профиль", exact: true }).waitFor();
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: `${output}/restored-mobile.png`, fullPage: true });
  await logout();
  assert.deepEqual(errors, [], "Browser JavaScript errors");
  console.log(`Session browser checks passed: reload/navigation, server verification, 503/network retry, 401/corrupt token, stale response, account switch, logout, separate tab, mobile 390px. Screenshots: ${output}`);
} catch (error) {
  await page?.screenshot({ path: `${output}/failure.png`, fullPage: true }).catch(() => {});
  throw error;
} finally { await browser.close(); }
