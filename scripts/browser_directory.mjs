/** Safe Jana People UI regression using synthetic, read-only API responses. */
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE || "playwright");
const origin = process.env.WEB_URL || "http://127.0.0.1:3000";
const profile = (id, full_name, manager_id, position, department, role = "employee") => ({
  id, full_name, manager_id, position, department, role, email: `test-${id}@example.com`,
  company: "Synthetic test company", manager_name: null, hire_date: "2024-01-01",
  leave_balance: 20, data_source: "mock_zup",
});
const full = [
  profile(1, "Айдана Тест", 2, "Координатор", "Логистика"),
  profile(2, "Арман Тест", 3, "Руководитель логистики", "Логистика", "manager"),
  profile(3, "Алия Тест", null, "Генеральный директор", "Руководство", "hr_admin"),
  profile(4, "Данияр Тест", 2, "Логист", "Логистика"),
];
const people = full.map(({ id, full_name, position, department, manager_id }) => ({
  id, full_name, position, department, manager_id, can_open_profile: id === 1, is_demo: true,
}));
const browser = await chromium.launch({ headless: true });
try {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    await context.addInitScript(() => sessionStorage.setItem("jana-hr.access-token", "browser-test-token"));
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/api/**", route => {
      const path = new URL(route.request().url()).pathname;
      assert.equal(route.request().method(), "GET");
      const json = path === "/api/me" ? full[0] : path === "/api/directory" ? people
        : path === "/api/employees" ? [full[0]]
        : path === "/api/courses/rewards" ? { xp: 0, level: 1, next_level_xp: 100, badges: [] } : [];
      return route.fulfill({ json });
    });
    await page.goto(`${origin}/#team`);
    await page.getByRole("heading", { name: "Сотрудники", exact: true }).waitFor();
    await page.getByText("4 из 4 сотрудников").waitFor();
    await page.getByRole("button", { name: /Алия Тест/ }).first().click();
    const dialog = page.getByRole("dialog", { name: "Карточка сотрудника" });
    await dialog.waitFor();
    assert.equal(await dialog.getByText("Почта недоступна").count(), 1);
    assert.equal(await dialog.getByText(/Остаток отпуска/).count(), 0);
    await dialog.getByRole("button", { name: "Закрыть" }).click();
    await page.getByRole("button", { name: "Список", exact: true }).click();
    await page.getByLabel("Поиск", { exact: true }).fill("Логист");
    await page.getByText("2 из 4 сотрудников").waitFor();
    await page.getByRole("button", { name: "Структура", exact: true }).click();
    await page.getByRole("button", { name: "Подразделения", exact: true }).click();
    await page.getByRole("heading", { name: "Подразделения", exact: true }).waitFor();
    await page.getByLabel("Поиск", { exact: true }).fill("");
    await page.getByRole("button", { name: "Подчинение", exact: true }).click();
    await page.getByRole("button", { name: "Развернуть всё", exact: true }).click();
    assert.equal(await page.locator(".org-chart-card").count(), 4);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.deepEqual(errors, []);
    await context.close();
  }
  console.log("Jana People desktop and 390px mobile browser checks passed.");
} finally { await browser.close(); }
