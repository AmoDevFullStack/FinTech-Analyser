import { expect, test } from "@playwright/test";

/** Import through scenario result, per docs/architecture.md §6 and PLAN.md's quality
 * gate. Requires the full stack with a seeded demo user:
 *
 *   make up && make migrate && make seed && make e2e
 *
 * CI runs it in the `e2e` job of .github/workflows/ci.yml. The defaults match what
 * `flask seed demo` creates (backend/app/cli.py); override them to run against another
 * environment.
 */

const DEMO_EMAIL = process.env.E2E_EMAIL ?? "demo@financialdigitaltwin.local";
const DEMO_PASSWORD = process.env.E2E_PASSWORD ?? "demo-password-change-me";

test("import a CSV, run the vehicle purchase scenario, and see the result", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(DEMO_EMAIL);
  await page.getByLabel("Password").fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();

  await expect(page.getByRole("heading", { name: "Financial Digital Twin" })).toBeVisible();

  // Destinations live behind the menu control now, not in a row of tabs.
  await page.getByRole("button", { name: "Menu" }).click();
  await page.getByRole("link", { name: "Scenarios" }).click();
  await page.getByRole("button", { name: "Create scenario" }).click();

  await expect(page.getByRole("heading", { name: "New vehicle" })).toBeVisible();
  await page.getByRole("button", { name: "Run scenario" }).click();

  await expect(page.getByText("Monthly cash-flow impact")).toBeVisible();
  await expect(page.getByText("Net worth: scenario vs. baseline")).toBeVisible();
});
