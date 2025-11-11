import { expect, test } from "@playwright/test";

test.describe("Admin Panel", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/auth/login");
  });

  test("should redirect non-admin users to dashboard", async ({ page }) => {
    await page.fill('input[type="email"]', "user@example.com");
    await page.fill('input[type="password"]', "password123");
    await page.click('button[type="submit"]');

    await page.goto("/admin");

    await expect(page).toHaveURL("/");
  });

  test("should allow admin access to admin panel", async ({ page, context }) => {
    await context.addCookies([
      {
        name: "auth_token",
        value: "mock-admin-token",
        domain: "localhost",
        path: "/",
      },
    ]);

    await page.evaluate(() => {
      localStorage.setItem(
        "auth",
        JSON.stringify({
          user: { id: 1, email: "admin@example.com", role: "admin" },
          accessToken: "mock-token",
        }),
      );
    });

    await page.goto("/admin");

    await expect(page.locator("h2:text('Admin Panel')")).toBeVisible();
  });

  test("should display analytics dashboard", async ({ page, context }) => {
    await context.addCookies([
      {
        name: "auth_token",
        value: "mock-admin-token",
        domain: "localhost",
        path: "/",
      },
    ]);

    await page.evaluate(() => {
      localStorage.setItem(
        "auth",
        JSON.stringify({
          user: { id: 1, email: "admin@example.com", role: "admin" },
          accessToken: "mock-token",
        }),
      );
    });

    await page.route("**/api/v1/admin/analytics", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total_users: 150,
          active_users: 120,
          total_subscriptions: 80,
          active_subscriptions: 65,
          total_generations: 2500,
          generations_today: 100,
          generations_this_week: 500,
          generations_this_month: 1800,
          failed_generations: 25,
          revenue_total: "50000.00",
          revenue_this_month: "5000.00",
        }),
      });
    });

    await page.goto("/admin");

    await expect(page.locator("h1:text('Admin Dashboard')")).toBeVisible();
    await expect(page.locator("text=Total Users")).toBeVisible();
    await expect(page.locator("text=150")).toBeVisible();
  });

  test("should navigate to users management", async ({ page, context }) => {
    await context.addCookies([
      {
        name: "auth_token",
        value: "mock-admin-token",
        domain: "localhost",
        path: "/",
      },
    ]);

    await page.evaluate(() => {
      localStorage.setItem(
        "auth",
        JSON.stringify({
          user: { id: 1, email: "admin@example.com", role: "admin" },
          accessToken: "mock-token",
        }),
      );
    });

    await page.goto("/admin");

    await page.click('a[href*="/admin/users"]');

    await expect(page).toHaveURL(/\/admin\/users/);
    await expect(page.locator("h1:text('User Management')")).toBeVisible();
  });

  test("should list users with pagination", async ({ page, context }) => {
    await context.addCookies([
      {
        name: "auth_token",
        value: "mock-admin-token",
        domain: "localhost",
        path: "/",
      },
    ]);

    await page.evaluate(() => {
      localStorage.setItem(
        "auth",
        JSON.stringify({
          user: { id: 1, email: "admin@example.com", role: "admin" },
          accessToken: "mock-token",
        }),
      );
    });

    await page.route("**/api/v1/admin/users*", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              id: 1,
              email: "user1@example.com",
              role: "user",
              balance: "100.00",
              is_active: true,
              created_at: "2024-01-01T00:00:00Z",
            },
            {
              id: 2,
              email: "user2@example.com",
              role: "admin",
              balance: "200.00",
              is_active: true,
              created_at: "2024-01-02T00:00:00Z",
            },
          ],
          total: 2,
          page: 1,
          page_size: 20,
          total_pages: 1,
        }),
      });
    });

    await page.goto("/admin/users");

    await expect(page.locator("table")).toBeVisible();
    await expect(page.locator("text=user1@example.com")).toBeVisible();
    await expect(page.locator("text=user2@example.com")).toBeVisible();
  });

  test("should filter users by role", async ({ page, context }) => {
    await context.addCookies([
      {
        name: "auth_token",
        value: "mock-admin-token",
        domain: "localhost",
        path: "/",
      },
    ]);

    await page.evaluate(() => {
      localStorage.setItem(
        "auth",
        JSON.stringify({
          user: { id: 1, email: "admin@example.com", role: "admin" },
          accessToken: "mock-token",
        }),
      );
    });

    let requestedRole = "";

    await page.route("**/api/v1/admin/users*", (route) => {
      const url = new URL(route.request().url());
      requestedRole = url.searchParams.get("role") || "";

      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [],
          total: 0,
          page: 1,
          page_size: 20,
          total_pages: 0,
        }),
      });
    });

    await page.goto("/admin/users");

    await page.selectOption('select[class*="filter-select"]', "admin");

    await page.waitForTimeout(500);

    expect(requestedRole).toBe("admin");
  });

  test("should moderate generations", async ({ page, context }) => {
    await context.addCookies([
      {
        name: "auth_token",
        value: "mock-admin-token",
        domain: "localhost",
        path: "/",
      },
    ]);

    await page.evaluate(() => {
      localStorage.setItem(
        "auth",
        JSON.stringify({
          user: { id: 1, email: "admin@example.com", role: "admin" },
          accessToken: "mock-token",
        }),
      );
    });

    await page.route("**/api/v1/admin/generations*", (route) => {
      if (route.request().method() === "GET") {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            items: [
              {
                id: 1,
                user_id: 10,
                prompt_id: 5,
                status: "completed",
                source: "api",
                parameters: {},
                result_parameters: {},
                result_asset_url: "https://example.com/result.png",
                created_at: "2024-01-01T00:00:00Z",
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
            total_pages: 1,
          }),
        });
      } else {
        route.fulfill({ status: 200, body: "{}" });
      }
    });

    await page.goto("/admin/generations");

    await expect(page.locator("h1:text('Generation Management')")).toBeVisible();
    await expect(page.locator("table")).toBeVisible();
  });
});
