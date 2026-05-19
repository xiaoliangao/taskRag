import { expect, test } from "@playwright/test";

const DEMO_EMAIL = process.env.E2E_DEMO_EMAIL || "demo@example.com";
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD || "demo123";

/**
 * Smoke E2E: login → topics list → open first topic → Radar tab loads.
 * Run against a running stack:
 *   E2E_BASE_URL=http://49.233.190.200:5173 npx playwright test
 */
test("user can login, see topics, and open the Radar tab", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: /使用演示账号/ })).toBeVisible();

  await page.getByRole("button", { name: /使用演示账号/ }).click();
  await expect(page.getByRole("textbox", { name: "邮箱" })).toHaveValue(DEMO_EMAIL);
  await page.getByRole("button", { name: /登\s*录/ }).click();

  await page.waitForURL(/\/topics$/);
  // At least one topic card must be visible
  await expect(page.locator(".topic-card-title").first()).toBeVisible();

  // Open the first topic
  await page.locator(".topic-card-title").first().click();
  await page.waitForURL(/\/topics\/\d+/);

  // Navigate to Radar tab directly (more reliable than clicking the Antd tab)
  const detail = page.url();
  await page.goto(detail.replace(/\/topics\/(\d+).*$/, "/topics/$1/radar"));
  await page.waitForURL(/\/topics\/\d+\/radar$/);

  // Either the empty-state generate button OR the existing radar view should appear
  await expect(
    page.locator(
      "[data-testid='trend-radar-view'], button:has-text('生成趋势'), button:has-text('重新生成')",
    ).first(),
  ).toBeVisible({ timeout: 15_000 });
});

test("API health endpoint is reachable", async ({ request }) => {
  const resp = await request.get("/api/v1/auth/me", {
    failOnStatusCode: false,
  });
  // 401 (no token) or 200 (logged in) both prove the API is up & CORS works.
  expect([200, 401]).toContain(resp.status());
});
