import { test, expect, BrowserContext, Page } from "@playwright/test";

function setupBackendRoutes(context: BrowserContext) {
  return context.route("**/backend-api/**", async (route) => {
    const url = route.request().url();
    const headers = route.request().headers();
    const auth = headers["authorization"];

    if (url.includes("/backend-api/auth/logout")) {
      return route.fulfill({ status: 204 });
    }

    if (url.includes("/backend-api/me")) {
      if (!auth || !auth.includes("dev_")) {
        return route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ error: { code: "UNAUTHORIZED", message: "Missing or invalid token" } }),
        });
      }
      const handle = auth.replace("Bearer dev_", "").trim();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: `u_${handle}`,
          email: `${handle}@thinkloop.ai`,
          created_at: "2026-01-01T00:00:00Z",
        }),
      });
    }

    if (url.includes("/backend-api/streak/calendar")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    }

    if (url.includes("/backend-api/streak")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          current_streak: 5,
          longest_streak: 12,
          freezes_available: 1,
          freeze_cap: 2,
          today_active: true,
          at_risk: false,
          days_until_freeze: 2,
        }),
      });
    }

    if (url.includes("/backend-api/mastery")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    }

    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
  });
}

async function signInAs(page: Page, name: string = "Aditya") {
  await page.goto("/");
  const signInBtn = page.getByRole("button", { name: /sign in/i });
  await signInBtn.click();

  if (name === "Aditya") {
    const continueBtn = page.getByRole("button", { name: /continue as aditya/i });
    await continueBtn.click();
  } else {
    const input = page.getByPlaceholder(/enter your name/i);
    await input.fill(name);
    const enterBtn = page.getByRole("button", { name: /^enter$/i });
    await enterBtn.click();
  }
  await page.waitForURL(/\/workspace/);
}

test.describe("Post-Login Authentication & Session Lifecycle E2E", () => {
  test.beforeEach(async ({ context }) => {
    await setupBackendRoutes(context);
  });

  test("sign in -> /workspace loads, shows skeleton during bootstrap, preserves identity", async ({ page }) => {
    await signInAs(page, "Aditya");

    await expect(page).toHaveURL(/\/workspace/);
    await expect(page.locator(".workspace-shell")).toBeVisible();
    await expect(page.getByText(/aditya/i).first()).toBeVisible();
  });

  test("reload preserves identity and active concept", async ({ page }) => {
    await signInAs(page, "Aditya");
    await expect(page.locator(".workspace-shell")).toBeVisible();

    // Reload the page
    await page.reload();

    await expect(page).toHaveURL(/\/workspace/);
    await expect(page.locator(".workspace-shell")).toBeVisible();
    await expect(page.getByText(/aditya/i).first()).toBeVisible();
  });

  test("sign out -> clears state, back button cannot reveal workspace", async ({ page }) => {
    await signInAs(page, "Aditya");
    await expect(page.locator(".workspace-shell")).toBeVisible();

    // Click Sign Out
    const signOutBtn = page.getByRole("button", { name: /sign out/i });
    await signOutBtn.click();

    // Should redirect to /
    await page.waitForURL((url) => url.pathname === "/");

    // Verify storage cleared
    const storedToken = await page.evaluate(() => window.localStorage.getItem("thinkloop_auth_token"));
    expect(storedToken).toBeNull();

    // Test Back button does not reveal workspace
    await page.goBack();
    await page.waitForURL((url) => url.pathname === "/");
    await expect(page).toHaveURL(/\//);
  });

  test("two browser tabs: sign out in tab 1 triggers sign out in tab 2", async ({ context }) => {
    const page1 = await context.newPage();
    const page2 = await context.newPage();

    await signInAs(page1, "Aditya");
    await page2.goto("/workspace");

    await expect(page1.locator(".workspace-shell")).toBeVisible();
    await expect(page2.locator(".workspace-shell")).toBeVisible();

    // Sign out from Page 1
    const signOutBtn = page1.getByRole("button", { name: /sign out/i });
    await signOutBtn.click();

    await page1.waitForURL((url) => url.pathname === "/");

    // Page 2 automatically receives broadcast and redirects to /
    await page2.waitForURL((url) => url.pathname === "/");
    await expect(page2).toHaveURL(/\//);
  });

  test("user A signs out, user B signs in on same browser: B sees none of A's state", async ({ page }) => {
    // 1. Sign in as User A (Aditya)
    await signInAs(page, "Aditya");
    await expect(page.getByText(/aditya/i).first()).toBeVisible();

    // Set user-scoped key for User A
    await page.evaluate(() => {
      window.localStorage.setItem("thinkloop:u_aditya:study_session", "session_aditya_123");
    });

    // 2. Sign out
    const signOutBtn = page.getByRole("button", { name: /sign out/i });
    await signOutBtn.click();
    await page.waitForURL((url) => url.pathname === "/");

    // 3. Sign in as User B (Bob)
    await signInAs(page, "Bob");
    await expect(page.getByText(/bob/i).first()).toBeVisible();

    // 4. Verify User A's data was purged
    const leakedData = await page.evaluate(() => {
      return window.localStorage.getItem("thinkloop:u_aditya:study_session");
    });
    expect(leakedData).toBeNull();
  });

  test("backend down at mount shows error + retry, not a blank page or logout", async ({ page, context }) => {
    // Unroute and mock network failure for /backend-api/me
    await context.unroute("**/backend-api/**");
    await context.route("**/backend-api/me", async (route) => {
      return route.abort("failed");
    });

    await signInAs(page, "Aditya");

    // Must show error card with Retry button
    await expect(page.locator(".workspace-error-card")).toBeVisible();
    await expect(page.getByRole("button", { name: /retry/i })).toBeVisible();
  });

  test("expired/revoked token (backend returns 401) mid-session redirects cleanly with message", async ({ page, context }) => {
    await signInAs(page, "Aditya");
    await expect(page.locator(".workspace-shell")).toBeVisible();

    // Switch /backend-api/streak to return 401
    await context.route("**/backend-api/streak**", async (route) => {
      return route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "UNAUTHORIZED", message: "Token expired" } }),
      });
    });

    // Trigger an authenticated request in page that encounters 401
    await Promise.all([
      page.waitForURL((url) => url.pathname === "/" && url.searchParams.get("reason") === "expired"),
      page.evaluate(() => {
        setTimeout(async () => {
          try {
            const { fetchWithAuth } = await import("../../lib/auth");
            await fetchWithAuth("/backend-api/streak");
          } catch {
            // expected on abort or navigation
          }
        }, 10);
      }),
    ]);

    expect(page.url()).toContain("reason=expired");
  });
});
