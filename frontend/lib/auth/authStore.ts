/**
 * Single Auth Store owning all client authentication state, session bootstrapping,
 * single-flight 401 handling, proactive expiration, and cross-tab logout.
 */

import { AuthState, AuthUser, RedirectHandler } from "./types";
import {
  clearAllUserState,
  registerActiveTimer,
  unregisterActiveTimer,
  registerUserScopedKey,
  getUserScopedKeys,
} from "./storageRegistry";
import { broadcastAuthEvent, onAuthBroadcast } from "./broadcast";
import { isClerkConfigured } from "./clerkConfig";

const AUTH_STORAGE_KEY = "thinkloop_auth_token";
const USER_STORAGE_KEY = "thinkloop_user_profile";

export type TokenProvider = () => Promise<string | null> | string | null;
let currentTokenProvider: TokenProvider | null = null;

export function setTokenProvider(provider: TokenProvider | null): void {
  currentTokenProvider = provider;
}

export function getTokenProvider(): TokenProvider | null {
  return currentTokenProvider;
}

let currentEpoch = 1;
let epochAbortController = new AbortController();

let proactiveExpiryTimeout: NodeJS.Timeout | null = null;
let singleFlight401Promise: Promise<void> | null = null;

let redirectHandler: RedirectHandler = (url: string) => {
  if (typeof window !== "undefined") {
    window.location.href = url;
  }
};

let state: AuthState = {
  status: "loading",
  user: null,
  error: null,
  epoch: currentEpoch,
};

const listeners = new Set<(s: AuthState) => void>();

function notify(): void {
  listeners.forEach((listener) => {
    try {
      listener(state);
    } catch {
      // ignore
    }
  });
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(AUTH_STORAGE_KEY);
}

export function setStoredToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(AUTH_STORAGE_KEY, token);
  try {
    if (typeof document !== "undefined") {
      const formattedToken = token.startsWith("Bearer ") ? token : `Bearer ${token}`;
      document.cookie = `thinkloop_auth_token=${encodeURIComponent(formattedToken)}; path=/; max-age=604800; SameSite=Lax`;
    }
  } catch {
    // ignore
  }
}

export function getStoredProfile(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function setStoredProfile(profile: AuthUser): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(profile));
}

function bumpEpoch(): number {
  currentEpoch++;
  try {
    epochAbortController.abort();
  } catch {
    // ignore
  }
  epochAbortController = new AbortController();
  return currentEpoch;
}

function scheduleProactiveExpiry(token: string | null | undefined): void {
  if (proactiveExpiryTimeout) {
    clearTimeout(proactiveExpiryTimeout);
    proactiveExpiryTimeout = null;
  }

  if (!token) return;

  // When Clerk is active or a dynamic tokenProvider is configured, token refreshing is handled automatically.
  // Proactively terminating the session based on short-lived Clerk JWT exp (60s) would kick users out prematurely.
  if (isClerkConfigured() || currentTokenProvider) return;

  // Parse payload if JWT
  const parts = token.replace(/^Bearer\s+/i, "").split(".");
  if (parts.length === 3) {
    try {
      const decodedStr = atob(parts[1]);
      const payload = JSON.parse(decodedStr);
      if (payload.exp && typeof payload.exp === "number") {
        const nowMs = Date.now();
        const expMs = payload.exp * 1000;
        const delay = expMs - nowMs - 5000; // 5 seconds before actual exp
        if (delay > 0) {
          proactiveExpiryTimeout = setTimeout(() => {
            handle401("expired");
          }, delay);
        }
      }
    } catch {
      // Not a standard JWT or unparseable
    }
  }
}

export const authStore = {
  getState(): AuthState {
    return state;
  },

  getEpoch(): number {
    return currentEpoch;
  },

  getEpochSignal(): AbortSignal {
    return epochAbortController.signal;
  },

  subscribe(listener: (s: AuthState) => void): () => void {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },

  setRedirectHandler(handler: RedirectHandler): void {
    redirectHandler = handler;
  },

  registerActiveTimer,
  unregisterActiveTimer,
  registerUserScopedKey,
  getUserScopedKeys,
};

/**
 * Handle 401 response in a single-flight mutex pattern.
 * Even if 5 requests fail concurrently, only ONE sign-out and redirect occurs.
 */
export async function handle401(reason = "expired"): Promise<void> {
  if (singleFlight401Promise) {
    return singleFlight401Promise;
  }

  singleFlight401Promise = (async () => {
    try {
      await signOut({ reason, skipServerLogout: false });
    } finally {
      singleFlight401Promise = null;
    }
  })();

  return singleFlight401Promise;
}

/**
 * Cleanly sign out current user.
 */
export async function signOut(options?: {
  reason?: string;
  skipServerLogout?: boolean;
}): Promise<void> {
  const reason = options?.reason;
  const skipServerLogout = options?.skipServerLogout ?? false;

  // 1. Invalidate current auth epoch to abort in-flight requests and drop late responses
  bumpEpoch();

  if (proactiveExpiryTimeout) {
    clearTimeout(proactiveExpiryTimeout);
    proactiveExpiryTimeout = null;
  }

  // 2. Best-effort server-side logout (clears cookies if BFF, 2s timeout)
  if (!skipServerLogout) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2000);
      await fetch("/backend-api/auth/logout", {
        method: "POST",
        signal: controller.signal,
      }).catch(() => {
        // network or server failure must not block local cleanup
      });
      clearTimeout(timeoutId);
    } catch {
      // ignore
    }
  }

  // 3. Clear all user-scoped storage, intervals, and streams
  clearAllUserState();

  // 4. Update store state
  state = {
    status: "unauthenticated",
    user: null,
    error: null,
    epoch: currentEpoch,
  };
  notify();

  // 5. Broadcast to all open tabs
  broadcastAuthEvent({ type: "LOGOUT" });

  // 6. Redirect to / with reason
  const targetUrl = reason ? `/?reason=${encodeURIComponent(reason)}` : "/";
  redirectHandler(targetUrl);
}

/**
 * Sign in as a user.
 */
export function signIn(token: string, user: AuthUser): void {
  // CRITICAL: Always purge prior user state first to prevent inheriting leftovers
  clearAllUserState();

  const epoch = bumpEpoch();
  const formattedToken = token.startsWith("Bearer ") ? token : `Bearer ${token}`;
  setStoredToken(formattedToken);
  setStoredProfile(user);

  try {
    if (typeof document !== "undefined") {
      document.cookie = `thinkloop_auth_token=${encodeURIComponent(formattedToken)}; path=/; SameSite=Lax`;
    }
  } catch {
    // ignore
  }

  scheduleProactiveExpiry(token);

  state = {
    status: "authenticated",
    user,
    error: null,
    epoch,
  };
  notify();

  broadcastAuthEvent({ type: "LOGIN", userId: user.id });
}

/**
 * Directly set authenticated state (e.g. from verified Clerk session or offline fallback).
 */
export function setAuthenticatedUser(user: AuthUser, token?: string): void {
  const cached = getStoredProfile();
  if (cached && cached.id && cached.id !== user.id) {
    clearAllUserState();
  }

  if (token) {
    const formattedToken = token.startsWith("Bearer ") ? token : `Bearer ${token}`;
    setStoredToken(formattedToken);
    try {
      if (typeof document !== "undefined") {
        document.cookie = `thinkloop_auth_token=${encodeURIComponent(formattedToken)}; path=/; SameSite=Lax`;
      }
    } catch {
      // ignore
    }
  }

  setStoredProfile(user);

  state = {
    status: "authenticated",
    user,
    error: null,
    epoch: currentEpoch,
  };
  notify();
}

/**
 * Bootstrap session on workspace mount.
 */
export async function bootstrapSession(explicitToken?: string): Promise<AuthState> {
  const epochAtStart = currentEpoch;
  state = {
    ...state,
    status: "loading",
    error: null,
  };
  notify();

  let token: string | null | undefined = explicitToken;
  if (!token && currentTokenProvider) {
    try {
      const dynamic = await currentTokenProvider();
      if (dynamic) {
        token = dynamic.startsWith("Bearer ") ? dynamic : `Bearer ${dynamic}`;
        setStoredToken(token);
      }
    } catch {
      // ignore
    }
  }

  if (!token) {
    token = getStoredToken();
  }

  // If in pure local dev mode without Clerk and without token, fallback to dev_learner
  if (!token && !isClerkConfigured()) {
    token = "Bearer dev_learner";
    setStoredToken(token);
  }

  const cachedProfile = getStoredProfile();

  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = token.startsWith("Bearer ") ? token : `Bearer ${token}`;
  }

  try {
    let res = await fetch("/backend-api/me", {
      headers,
      credentials: "include",
      signal: epochAbortController.signal,
    });

    // Check if epoch changed while fetching (e.g. signed out in-flight)
    if (currentEpoch !== epochAtStart) {
      return state;
    }

    // If 401, try one refresh if dynamic token provider is configured (e.g. Clerk token expired)
    if (res.status === 401 && (isClerkConfigured() || currentTokenProvider)) {
      if (currentTokenProvider) {
        try {
          const fresh = await currentTokenProvider();
          if (fresh) {
            token = fresh.startsWith("Bearer ") ? fresh : `Bearer ${fresh}`;
            setStoredToken(token);
            headers["Authorization"] = token;
            res = await fetch("/backend-api/me", {
              headers,
              credentials: "include",
              signal: epochAbortController.signal,
            });
            if (currentEpoch !== epochAtStart) {
              return state;
            }
          }
        } catch {
          // ignore
        }
      }
    }

    if (res.status === 401) {
      await handle401("expired");
      return state;
    }

    if (!res.ok) {
      // 5xx or server glitch: do NOT log out, do NOT show other users' data
      state = {
        status: "error",
        user: cachedProfile,
        error: `Server responded with error status ${res.status}.`,
        epoch: currentEpoch,
      };
      notify();
      return state;
    }

    const data = await res.json();

    // Verify user ID match with cached profile
    if (cachedProfile && cachedProfile.id && cachedProfile.id !== data.id) {
      // Different user! Purge old user data before rendering
      clearAllUserState();
    }

    const verifiedUser: AuthUser = {
      id: data.id,
      email: data.email,
      name: cachedProfile?.name || (data.email ? data.email.split("@")[0] : "Learner"),
      timezone: cachedProfile?.timezone || "UTC",
      dailyGoalMinutes: cachedProfile?.dailyGoalMinutes || 30,
      voiceEnabled: cachedProfile?.voiceEnabled ?? true,
    };

    setStoredProfile(verifiedUser);
    if (token) {
      setStoredToken(token);
      scheduleProactiveExpiry(token);
    }

    state = {
      status: "authenticated",
      user: verifiedUser,
      error: null,
      epoch: currentEpoch,
    };
    notify();
    return state;
  } catch (err: any) {
    if (err?.name === "AbortError" && currentEpoch !== epochAtStart) {
      return state;
    }
    // Network error: keep user, enter error state with retry
    state = {
      status: "error",
      user: cachedProfile,
      error: "Unable to connect to Thinkloop server. Please check your network and retry.",
      epoch: currentEpoch,
    };
    notify();
    return state;
  }
}

// Listen for cross-tab broadcasts
if (typeof window !== "undefined") {
  onAuthBroadcast((msg) => {
    if (msg.type === "LOGOUT") {
      // Tab 2 cleans up and redirects
      clearAllUserState();
      state = {
        status: "unauthenticated",
        user: null,
        error: null,
        epoch: bumpEpoch(),
      };
      notify();
      redirectHandler("/");
    }
  });
}
