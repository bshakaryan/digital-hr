/** Read-only Academy track smoke against a built frontend with synthetic API fixtures. */
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PACKAGE || "playwright");
const origin = process.env.WEB_URL || "http://127.0.0.1:3000";
const person = (role) => ({ id: 101, full_name: "Демо Сотрудник", role, email: "demo@example.com", position: "Специалист", department: "Логистика", company: "Демо", manager_id: 1, manager_name: "Демо Руководитель", hire_date: "2024-01-01", leave_balance: 20, data_source: "mock_zup" });
const course = (id, title, learning_track, completed, progress) => ({ id, title, description: "Демонстрационный учебный материал", content: "", duration_minutes: 20, progress, completed, question: "", options: [], objectives: "Знать основы", status: "published", category: "logistics", is_demo: true, deadline: null, learning_status: completed ? "completed" : progress ? "in_progress" : "not_started", overdue: false, learning_track, self_enrollable: false });
const assigned = [course(1, "Адаптация: приёмка", "onboarding", true, 100), course(2, "Адаптация: сортировка", "onboarding", false, 40), course(3, "Развитие: клиентский сервис", "development", true, 100), course(4, "Ранее назначенный курс", "legacy", false, 0)];
const catalog = [{ id: 5, title: "Открытый курс", description: "Демонстрационное обучение", objectives: "Основы", duration_minutes: 30, category: "general", is_demo: true, self_enrollable: true }];
const browser = await chromium.launch({ headless: true });
try {
  for (const width of [1440, 390]) {
    for (const role of ["employee", "hr_admin"]) {
      const context = await browser.newContext({ viewport: { width, height: 900 } });
      await context.addInitScript(() => sessionStorage.setItem("jana-hr.access-token", "synthetic-academy-token"));
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.route("**/api/**", route => {
        const path = new URL(route.request().url()).pathname;
        assert.equal(route.request().method(), "GET", "Browser smoke must not write data");
        const json = path === "/api/me" ? person(role) : path === "/api/courses" ? (role === "employee" ? assigned : [])
          : path === "/api/courses/discover" ? catalog : path === "/api/courses/catalog" ? []
          : path === "/api/courses/rewards" ? { xp: 200, level: 2, next_level_xp: 300, badges: ["Первый курс"] } : [];
        return route.fulfill({ json });
      });
      await page.goto(`${origin}/#academy`);
      if (role === "employee") {
        const onboarding = page.getByLabel("Адаптация", { exact: true });
        await onboarding.getByRole("heading", { name: "Jana Journey" }).waitFor();
        assert.equal(await onboarding.getByText("1 / 2", { exact: true }).count(), 1);
        assert.equal(await onboarding.getByText("50% маршрута").count(), 1);
        assert.equal(await onboarding.getByRole("heading", { name: "Развитие: клиентский сервис" }).count(), 0);
        await page.getByRole("navigation", { name: "Разделы Jana Academy" }).getByRole("button", { name: /Моё развитие/ }).click();
        await page.getByRole("heading", { name: "Развитие: клиентский сервис" }).waitFor();
        await page.getByRole("heading", { name: "Ранее назначенный курс" }).waitFor();
        assert.equal(await page.getByRole("heading", { name: "Адаптация: приёмка" }).count(), 0);
        await page.getByRole("group", { name: "Разделы развития" }).getByRole("button", { name: "Каталог" }).click();
        await page.getByRole("heading", { name: "Открытый курс" }).waitFor();
        assert.equal(await page.getByRole("button", { name: "Записаться" }).count(), 1);
      } else {
        await page.getByRole("button", { name: "Создать курс" }).click();
        await page.getByRole("heading", { name: "Создать черновик" }).waitFor();
        await page.getByText("Открыть самостоятельную запись", { exact: true }).waitFor();
      }
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      assert.deepEqual(errors, []);
      await context.close();
    }
  }
  console.log("Academy onboarding, development, legacy, catalog and HR form desktop/mobile checks passed.");
} finally { await browser.close(); }
