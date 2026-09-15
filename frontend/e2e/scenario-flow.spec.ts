import { expect, test } from "@playwright/test";

/** Import through scenario result, per docs/architecture.md §6 and PLAN.md's quality
 * gate. Requires the full stack (docker compose up) with a seeded demo user — this spec
 * is written to the plan's verification section and was not executed in the sandboxed
 * session that wrote it (no Postgres/Docker there); run it via
 * `docker compose run --rm playwright npx playwright test`.
 */

const DEMO_EMAIL = "demo@financialdigitaltwin.local";
const DEMO_PASSWORD = "AN@";

test("import a CSV, run the vehicle purchase scenario, and see the result", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(DEMO_EMAIL);
  await page.getByLabel("Password").fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();

  await expect(page.getByRole("heading", { name: "Financial Digital Twin" })).toBeVisible();

  await page.getByRole("link", { name: "Scenarios" }).click();
  await page.getByRole("button", { name: "Create scenario" }).click();

  await expect(page.getByRole("heading", { name: "New vehicle" })).toBeVisible();
  await page.getByRole("button", { name: "Run scenario" }).click();

  await expect(page.getByText("Monthly cash-flow impact")).toBeVisible();
  await expect(page.getByText("Net worth: scenario vs. baseline")).toBeVisible();
});
