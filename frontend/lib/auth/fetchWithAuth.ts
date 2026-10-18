/**
 * fetchWithAuth wrapper:
 * - Attaches auth credentials
 * - Links request to current auth epoch AbortController
 * - Discards responses if epoch changed (user signed out in-flight)
 * - Single-flight 401 interception via authStore.handle401()
 * - Respects 429 Retry-After header
 */

import { authStore, getStoredToken, handle401 } from "./authStore";

const BACKEND_BASE = "/backend-api";

export async function fetchWithAuth(
  endpoint: string,
  options: RequestInit = {}
): Promise<Response> {
  const epochAtStart = authStore.getEpoch();
  const token = getStoredToken() || "Bearer dev_learner";

  const headers = new Headers(options.headers || {});
  if (!headers.has("Authorization")) {
    headers.set("Authorization", token);
  }
  if (!headers.has("Content-Type") && options.body && typeof options.body === "string") {
    headers.set("Content-Type", "application/json");
  }

  // Combine caller signal with current epoch signal
  const epochSignal = authStore.getEpochSignal();
  let effectiveSignal = epochSignal;

  if (options.signal) {
    // If caller provided an AbortSignal, abort when either aborts
    const combinedController = new AbortController();
    const abortCombined = () => combinedController.abort();

    epochSignal.addEventListener("abort", abortCombined, { once: true });
    options.signal.addEventListener("abort", abortCombined, { once: true });

    effectiveSignal = combinedController.signal;
  }

  const url = endpoint.startsWith("http") ? endpoint : `${BACKEND_BASE}${endpoint}`;

  let res: Response;
  try {
    res = await fetch(url, {
      ...options,
      headers,
      signal: effectiveSignal,
    });
  } catch (err: any) {
    // If request aborted due to epoch change (sign-out), silently suppress or re-throw AbortError
    if (authStore.getEpoch() !== epochAtStart) {
      throw new DOMException("Request aborted due to authentication epoch change", "AbortError");
    }
    throw err;
  }

  // Check if sign-out occurred while the request was in-flight
  if (authStore.getEpoch() !== epochAtStart) {
    throw new DOMException("Response discarded due to sign-out during flight", "AbortError");
  }

  // Intercept 401 Unauthorized -> single flight sign out
  if (res.status === 401) {
    await handle401("expired");
    return res;
  }

  // 429 Rate Limit warning header
  if (res.status === 429) {
    const retryAfter = res.headers.get("Retry-After");
    if (retryAfter) {
      console.warn(`[thinkloop rate-limit] 429 Too Many Requests. Retry-After: ${retryAfter}s`);
    }
  }

  return res;
}
