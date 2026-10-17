/** Read-only browser check for reopening a completed Academy course. */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE || "../frontend/node_modules/playwright");
const config = readFileSync(resolve(".env"), "utf8");
const password = process.env.DEMO_PASSWORD || config.match(/^DEMO_PASSWORD=(.+)$/m)?.[1]?.trim();
const webPort = config.match(/^WEB_PORT=(\d+)$/m)?.[1] || "3000";
assert.ok(password, "DEMO_PASSWORD is required");
const browser = await chromium.launch({headless: true, executablePath: process.env.BROWSER_EXECUTABLE});
try {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(process.env.WEB_URL || `http://127.0.0.1:${webPort}`);
  await page.getByLabel("Рабочая почта").fill("hr@example.com");
  await page.getByLabel("Пароль", {exact: true}).fill(password);
  await page.getByRole("button", {name: "Войти в JanaМен"}).click();
  await page.getByRole("navigation").getByRole("button", {name: /^Jana Academy/}).click();
  for (let attempt = 0; attempt < 2; attempt++) {
    await page.getByRole("button", {name: "Повторить материал"}).click();
    const modal = page.getByRole("dialog", {name: "Jana Academy · Обучение"});
    await modal.getByRole("heading", {name: "Знакомство с JanaМен"}).waitFor();
    await modal.getByText("МАТЕРИАЛ КУРСА").waitFor();
    await modal.getByRole("button", {name: attempt === 0 ? "К списку курсов" : "Закрыть"}).click();
    await modal.waitFor({state: "hidden"});
  }
  assert.deepEqual(errors, []);
  console.log("Completed Academy course opened, closed, and reopened successfully.");
} finally {
  await browser.close();
}
