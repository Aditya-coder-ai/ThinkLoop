/**
 * Cross-tab synchronization via BroadcastChannel with storage event fallback.
 */

type AuthMessage = { type: "LOGOUT" } | { type: "LOGIN"; userId: string };

type MessageListener = (message: AuthMessage) => void;

const CHANNEL_NAME = "thinkloop_auth";
const STORAGE_SYNC_KEY = "thinkloop_sync_event";

let channel: BroadcastChannel | null = null;
const listeners = new Set<MessageListener>();

function initChannel(): void {
  if (typeof window === "undefined") return;

  if (typeof window.BroadcastChannel !== "undefined") {
    try {
      if (!channel) {
        channel = new BroadcastChannel(CHANNEL_NAME);
        channel.onmessage = (event: MessageEvent<AuthMessage>) => {
          if (event.data && typeof event.data === "object") {
            notifyListeners(event.data);
          }
        };
      }
    } catch {
      // BroadcastChannel unavailable
    }
  }

  // Fallback to storage events
  window.addEventListener("storage", (event: StorageEvent) => {
    if (event.key === STORAGE_SYNC_KEY && event.newValue) {
      try {
        const parsed = JSON.parse(event.newValue) as AuthMessage;
        notifyListeners(parsed);
      } catch {
        // ignore
      }
    }
  });
}

function notifyListeners(msg: AuthMessage): void {
  listeners.forEach((listener) => {
    try {
      listener(msg);
    } catch {
      // ignore
    }
  });
}

/**
 * Broadcast an authentication event to all other open tabs.
 */
export function broadcastAuthEvent(msg: AuthMessage): void {
  initChannel();
  if (channel) {
    try {
      channel.postMessage(msg);
    } catch {
      // ignore
    }
  }

  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(
        STORAGE_SYNC_KEY,
        JSON.stringify({ ...msg, _t: Date.now() })
      );
    } catch {
      // ignore
    }
  }
}

/**
 * Subscribe to cross-tab auth events.
 */
export function onAuthBroadcast(callback: MessageListener): () => void {
  initChannel();
  listeners.add(callback);
  return () => {
    listeners.delete(callback);
  };
}
