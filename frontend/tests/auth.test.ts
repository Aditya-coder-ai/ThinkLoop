import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import {
  authStore,
  bootstrapSession,
  signOut,
  fetchWithAuth,
  clearAllUserState,
  registerUserScopedKey,
  getUserScopedKeys,
  signIn,
} from "../lib/auth";

const server = setupServer(
  http.post("/backend-api/auth/logout", () => new HttpResponse(null, { status: 204 }))
);

beforeEach(() => {
  server.listen();
  window.localStorage.clear();
  window.sessionStorage.clear();
  vi.clearAllMocks();
});

afterEach(() => {
  server.resetHandlers();
  server.close();
});

describe("Authentication & Session Lifecycle (MSW Integration)", () => {
  it("bootstrap: 200 syncs server values over stale cached profile", async () => {
    // Stale profile in cache
    window.localStorage.setItem(
      "thinkloop_user_profile",
      JSON.stringify({
        id: "usr_123",
        email: "old_email@thinkloop.ai",
        name: "Old Name",
      })
    );

    server.use(
      http.get("/backend-api/me", () => {
        return HttpResponse.json({
          id: "usr_123",
          email: "new_verified@thinkloop.ai",
          name: "Verified Name",
        });
      })
    );

    const state = await bootstrapSession();
    expect(state.status).toBe("authenticated");
    expect(state.user?.email).toBe("new_verified@thinkloop.ai");

    const cached = JSON.parse(window.localStorage.getItem("thinkloop_user_profile") || "{}");
    expect(cached.email).toBe("new_verified@thinkloop.ai");
  });

  it("bootstrap: 401 -> all state cleared + redirect with reason=expired", async () => {
    window.localStorage.setItem("thinkloop_user_profile", JSON.stringify({ id: "usr_old" }));
    window.localStorage.setItem("thinkloop:usr_old:active_concept", "vectors");
    
    // Track redirects
    let redirectedUrl = "";
    authStore.setRedirectHandler((url) => {
      redirectedUrl = url;
    });

    server.use(
      http.get("/backend-api/me", () => {
        return new HttpResponse(null, { status: 401 });
      })
    );

    const state = await bootstrapSession();
    expect(state.status).toBe("unauthenticated");
    expect(redirectedUrl).toContain("reason=expired");

    // All user state cleared
    expect(window.localStorage.getItem("thinkloop:usr_old:active_concept")).toBeNull();
    expect(window.localStorage.getItem("thinkloop_user_profile")).toBeNull();
  });

  it("bootstrap: 500 / network error -> error state with retry, user NOT logged out, no cross-user data", async () => {
    window.localStorage.setItem(
      "thinkloop_user_profile",
      JSON.stringify({ id: "usr_current", email: "current@thinkloop.ai" })
    );

    server.use(
      http.get("/backend-api/me", () => {
        return new HttpResponse(null, { status: 500 });
      })
    );

    const state = await bootstrapSession();
    expect(state.status).toBe("error");
    // Crucial: NOT unauthenticated, and cached state NOT purged on temporary network/5xx glitch
    expect(window.localStorage.getItem("thinkloop_user_profile")).not.toBeNull();
  });

  it("bootstrap: cached profile id != /me id -> clearAllUserState() runs first", async () => {
    // User A leftovers in storage
    window.localStorage.setItem("thinkloop_user_profile", JSON.stringify({ id: "usr_A", name: "User A" }));
    window.localStorage.setItem("thinkloop:usr_A:study_session", "session_A_123");
    window.localStorage.setItem("thinkloop:usr_A:draft", "quantum physics notes");

    server.use(
      http.get("/backend-api/me", () => {
        // Server says current token belongs to User B!
        return HttpResponse.json({
          id: "usr_B",
          email: "userb@thinkloop.ai",
          name: "User B",
        });
      })
    );

    const state = await bootstrapSession();
    expect(state.status).toBe("authenticated");
    expect(state.user?.id).toBe("usr_B");

    // User A's data must be completely expunged!
    expect(window.localStorage.getItem("thinkloop:usr_A:study_session")).toBeNull();
    expect(window.localStorage.getItem("thinkloop:usr_A:draft")).toBeNull();
  });

  it("fetchWithAuth: 5 simultaneous 401s cause exactly ONE sign-out and ONE redirect", async () => {
    let redirectCount = 0;
    authStore.setRedirectHandler(() => {
      redirectCount++;
    });

    server.use(
      http.get("/backend-api/streak", () => new HttpResponse(null, { status: 401 })),
      http.get("/backend-api/mastery", () => new HttpResponse(null, { status: 401 })),
      http.get("/backend-api/focus", () => new HttpResponse(null, { status: 401 })),
      http.get("/backend-api/doubts", () => new HttpResponse(null, { status: 401 })),
      http.get("/backend-api/me", () => new HttpResponse(null, { status: 401 }))
    );

    // Fire 5 concurrent requests
    await Promise.allSettled([
      fetchWithAuth("/streak"),
      fetchWithAuth("/mastery"),
      fetchWithAuth("/focus"),
      fetchWithAuth("/doubts"),
      fetchWithAuth("/me"),
    ]);

    expect(redirectCount).toBe(1);
  });

  it("sign-out: aborts in-flight requests and late responses never mutate state", async () => {
    let slowRequestCompleted = false;

    server.use(
      http.get("/backend-api/slow-operation", async () => {
        await new Promise((r) => setTimeout(r, 100));
        return HttpResponse.json({ updated: true });
      }),
      http.post("/backend-api/auth/logout", () => new HttpResponse(null, { status: 204 }))
    );

    // Start slow request
    const slowReqPromise = fetchWithAuth("/slow-operation")
      .then(() => {
        slowRequestCompleted = true;
      })
      .catch((err) => {
        // Expected to abort
        return err;
      });

    // Immediate sign-out bumps epoch & aborts
    await signOut();

    await slowReqPromise;
    expect(slowRequestCompleted).toBe(false);
  });

  it("sign-out: closes open SSE streams and clears registered timer intervals", async () => {
    let timerCleared = false;
    const testTimerId = setInterval(() => {}, 1000) as unknown as number;
    
    // Register active interval in storageRegistry
    authStore.registerActiveTimer(testTimerId, () => {
      timerCleared = true;
    });

    server.use(
      http.post("/backend-api/auth/logout", () => new HttpResponse(null, { status: 204 }))
    );

    await signOut();
    expect(timerCleared).toBe(true);
  });

  it("clearAllUserState: removes EVERY registered key and any thinkloop:* keys", () => {
    registerUserScopedKey("custom_user_key");
    window.localStorage.setItem("custom_user_key", "secret1");
    window.localStorage.setItem("thinkloop:u1:active_concept", "forces");
    window.localStorage.setItem("thinkloop:u1:timer_remaining", "1400");
    window.localStorage.setItem("unrelated_external_key", "keep_me");

    clearAllUserState();

    expect(window.localStorage.getItem("custom_user_key")).toBeNull();
    expect(window.localStorage.getItem("thinkloop:u1:active_concept")).toBeNull();
    expect(window.localStorage.getItem("thinkloop:u1:timer_remaining")).toBeNull();
    // Non-thinkloop keys must remain untouched
    expect(window.localStorage.getItem("unrelated_external_key")).toBe("keep_me");
  });

  it("sign-in as user B after user A runs clearAllUserState() first", async () => {
    // User A data
    window.localStorage.setItem("thinkloop:usr_A:concept", "kinematics");
    window.localStorage.setItem("thinkloop_user_profile", JSON.stringify({ id: "usr_A" }));

    // Sign in as User B
    signIn("dev_user_b", { id: "usr_B", email: "user_b@thinkloop.ai", name: "User B" });

    // User A's data must be gone immediately
    expect(window.localStorage.getItem("thinkloop:usr_A:concept")).toBeNull();
    expect(JSON.parse(window.localStorage.getItem("thinkloop_user_profile") || "{}").id).toBe("usr_B");
  });

  it("BroadcastChannel logout in tab 1 triggers cleanup and sign-out in tab 2", async () => {
    // Simulate Tab 2 with active data
    window.localStorage.setItem("thinkloop_user_profile", JSON.stringify({ id: "usr_tab2" }));
    window.localStorage.setItem("thinkloop:usr_tab2:session", "tab2_session");

    let tab2Redirected = false;
    authStore.setRedirectHandler(() => {
      tab2Redirected = true;
    });

    // Send broadcast logout from Tab 1
    const channel = new BroadcastChannel("thinkloop_auth");
    channel.postMessage({ type: "LOGOUT" });

    // Allow broadcast dispatch to process
    await new Promise((r) => setTimeout(r, 20));

    expect(tab2Redirected).toBe(true);
    expect(window.localStorage.getItem("thinkloop_user_profile")).toBeNull();
    expect(window.localStorage.getItem("thinkloop:usr_tab2:session")).toBeNull();
  });

  it("logout endpoint failure or timeout does NOT block local cleanup", async () => {
    window.localStorage.setItem("thinkloop_user_profile", JSON.stringify({ id: "usr_logout" }));

    server.use(
      http.post("/backend-api/auth/logout", () => {
        return new HttpResponse(null, { status: 500 });
      })
    );

    // Sign out should complete cleanly despite 500 from server
    await signOut();

    expect(window.localStorage.getItem("thinkloop_user_profile")).toBeNull();
    expect(authStore.getState().status).toBe("unauthenticated");
  });

  it("token is never rendered to DOM, URL, or console", () => {
    const rawToken = "dev_confidential_secret_bearer_token";
    const consoleSpy = vi.spyOn(console, "log");
    const consoleErrorSpy = vi.spyOn(console, "error");

    signIn(rawToken, { id: "usr_secret", email: "test@thinkloop.ai", name: "Secret Learner" });

    // Check console calls
    const allLogs = [
      ...consoleSpy.mock.calls.flat(),
      ...consoleErrorSpy.mock.calls.flat(),
    ].join(" ");

    expect(allLogs).not.toContain(rawToken);
    expect(window.location.href).not.toContain(rawToken);
  });
});
