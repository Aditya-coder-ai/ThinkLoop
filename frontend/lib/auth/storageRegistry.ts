/**
 * Central registry for user-scoped storage keys, active timers, and network streams.
 * Ensures complete deterministic cleanup on sign-out or account switch.
 */

const registeredKeys = new Set<string>([
  "thinkloop_auth_token",
  "thinkloop_user_profile",
  "thinkloop-theme",
]);

interface ActiveResource {
  id: string | number;
  cleanup: () => void;
}

const activeTimers = new Map<string | number, () => void>();
const activeStreams = new Set<AbortController>();

/**
 * Register a user-scoped storage key to be expunged during clearAllUserState().
 */
export function registerUserScopedKey(key: string): void {
  registeredKeys.add(key);
}

/**
 * Return all registered user-scoped storage keys.
 */
export function getUserScopedKeys(): string[] {
  return Array.from(registeredKeys);
}

/**
 * Register an active timer or interval (e.g. Pomodoro focus timer or battle timer)
 * to be cancelled on sign-out.
 */
export function registerActiveTimer(id: string | number, cancelFn: () => void): void {
  activeTimers.set(id, cancelFn);
}

/**
 * Unregister a timer once it completes naturally.
 */
export function unregisterActiveTimer(id: string | number): void {
  activeTimers.delete(id);
}

/**
 * Register an active SSE or stream AbortController.
 */
export function registerActiveStream(controller: AbortController): void {
  activeStreams.add(controller);
}

/**
 * Unregister an active stream AbortController.
 */
export function unregisterActiveStream(controller: AbortController): void {
  activeStreams.delete(controller);
}

/**
 * Complete user state purge:
 * 1. Abort all active SSE/stream controllers
 * 2. Clear and invoke all registered timers/intervals
 * 3. Remove all explicitly registered keys from localStorage & sessionStorage
 * 4. Scan localStorage and sessionStorage and remove any key starting with "thinkloop:"
 */
export function clearAllUserState(): void {
  // 1. Abort active streams
  activeStreams.forEach((controller) => {
    try {
      controller.abort();
    } catch {
      // ignore
    }
  });
  activeStreams.clear();

  // 2. Clear all active timers
  activeTimers.forEach((cancelFn, id) => {
    try {
      cancelFn();
      if (typeof id === "number") {
        clearInterval(id);
        clearTimeout(id);
      }
    } catch {
      // ignore
    }
  });
  activeTimers.clear();

  // 3. Clear storage (browser environment guard)
  if (typeof window === "undefined") return;

  // Purge registered keys
  registeredKeys.forEach((key) => {
    try {
      window.localStorage.removeItem(key);
      window.sessionStorage.removeItem(key);
    } catch {
      // ignore
    }
  });

  // Clear auth cookie
  try {
    if (typeof document !== "undefined") {
      document.cookie = "thinkloop_auth_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";
    }
  } catch {
    // ignore
  }

  // Scan localStorage for any thinkloop:* keys
  try {
    const localKeys = Object.keys(window.localStorage);
    for (const key of localKeys) {
      if (key.startsWith("thinkloop:") || key.startsWith("thinkloop_")) {
        window.localStorage.removeItem(key);
      }
    }
  } catch {
    // ignore
  }

  // Scan sessionStorage for any thinkloop:* keys
  try {
    const sessionKeys = Object.keys(window.sessionStorage);
    for (const key of sessionKeys) {
      if (key.startsWith("thinkloop:") || key.startsWith("thinkloop_")) {
        window.sessionStorage.removeItem(key);
      }
    }
  } catch {
    // ignore
  }
}
