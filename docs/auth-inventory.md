# Thinkloop Authentication & User State Inventory

This document provides a comprehensive inventory of all client-side storage, network calls, streams, and timers that touch authentication or user-scoped state across the Thinkloop frontend and backend proxy.

---

## 1. Storage & State Inventory

| File | Storage Mechanism | Key / Identifier | Owner / Component | User-Scoped? | How It Is Cleared / Managed |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `frontend/app/workspace/api.ts` | `localStorage` | `thinkloop_auth_token` | Legacy Auth Helper | **YES** | Cleared via `clearAllUserState()` / `clearStoredAuth()`. Migrated to memory + cookie BFF / registered key. |
| `frontend/app/workspace/api.ts` | `localStorage` | `thinkloop_user_profile` | Legacy User Cache | **YES** | Cleared via `clearAllUserState()`. Reconciled strictly from `/me`. |
| `frontend/app/page.tsx` | `localStorage` | `thinkloop_auth_token` | Landing Page Sign-In | **YES** | Set on sign-in after `clearAllUserState()` flushes prior user data. |
| `frontend/app/page.tsx` | `localStorage` | `thinkloop_user_profile` | Landing Page Sign-In | **YES** | Set on sign-in after `clearAllUserState()` flushes prior user data. |
| `frontend/app/workspace/page.tsx` | `localStorage` | `thinkloop-theme` | Theme Manager | **NO** (Global device preference) | Preserved across logouts. Values: `"light"` \| `"dark"`. |
| `frontend/app/page.tsx` | `localStorage` | `thinkloop-theme` | Theme Manager | **NO** (Global device preference) | Preserved across logouts. Values: `"light"` \| `"dark"`. |
| `frontend/lib/auth/storageRegistry.ts` | Registry | `thinkloop:<userId>:*` | Auth & User State Store | **YES** | Namespaced by user ID. Central `clearAllUserState()` scans and purges all registered keys. |
| `frontend/app/workspace/page.tsx` | React State | `doubts`, `streak`, `masteryList` | Workspace Root | **YES** | Re-initialized or reset upon auth transition to `unauthenticated`. |

---

## 2. In-Flight Requests, Timers & Active Streams

| File | Mechanism | Purpose | Owner / Context | Cancellation / Teardown on Sign-Out |
| :--- | :--- | :--- | :--- | :--- |
| `frontend/app/workspace/api.ts` | `fetch()` | `fetchWithAuth` (`/me`, `/streak`, etc.) | Central API Client | Bound to auth `epoch` via `AbortController`. Incremented on sign-out to abort all in-flight requests and discard late responses. |
| `frontend/app/workspace/components/FocusTimerView.tsx` | `setInterval` | Pomodoro 1-second countdown | Focus Timer View | Cleared in `useEffect` unmount and registered in auth teardown listeners. |
| `frontend/app/workspace/components/BattleArenaView.tsx` | `setInterval` | 15-second round countdown timer | Battle Arena View | Cleared in `useEffect` unmount and registered in auth teardown listeners. |
| `frontend/app/workspace/components/SocraticChatView.tsx` | `setTimeout` | Simulated Socratic dialogue turn | Socratic Chat View | Bound to active component lifecycle and discarded if auth epoch increments. |
| `frontend/components/ui/smooth-cursor.tsx` | `setTimeout` | Pointer click scale animation | UI Cursor Component | Component-internal transient timer (non-user data). |

---

## 3. Cross-Tab Synchronization

| File | Mechanism | Channel / Event | Purpose | Action on Event |
| :--- | :--- | :--- | :--- | :--- |
| `frontend/lib/auth/broadcast.ts` | `BroadcastChannel` | `thinkloop_auth_channel` | Cross-tab auth synchronization | When `"logout"` is received, tab clears in-flight work and redirects to `/`. |
| `frontend/lib/auth/broadcast.ts` | `window.addEventListener("storage")` | Storage event fallback | Fallback for browsers without `BroadcastChannel` | Detects auth token removal and triggers synchronized sign-out. |

---

## 4. Backend Endpoints Invoked by Post-Login Flow

| Endpoint | Method | Auth Required | Purpose | Response Handling |
| :--- | :--- | :--- | :--- | :--- |
| `/backend-api/me` | `GET` | Bearer Token / Cookie | Bootstrap session verification | `200`: stores user ID/email, transitions state to `authenticated`. `401`: triggers `clearAllUserState()` + redirect `/?reason=expired`. `5xx`/network error: sets state to `error` with backoff retry. |
| `/backend-api/auth/logout` | `POST` | Optional (idempotent) | Invalidate server session & clear cookie | 2s timeout best-effort. Returns `204 No Content`. Local client cleanup proceeds regardless of failure. |
| `/backend-api/streak` | `GET` | Bearer Token / Cookie | Fetch learner streaks | Guarded by `fetchWithAuth`. 401 triggers single-flight sign-out. |
| `/backend-api/streak/calendar` | `GET` | Bearer Token / Cookie | Fetch monthly activity heatmap | Guarded by `fetchWithAuth`. |
| `/backend-api/mastery/mechanics` | `GET` | Bearer Token / Cookie | Fetch BKT knowledge graph nodes | Guarded by `fetchWithAuth`. |
| `/backend-api/sessions` | `POST` | Bearer Token / Cookie | Create/resume Socratic session | Guarded by `fetchWithAuth`. |
