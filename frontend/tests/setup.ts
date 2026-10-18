import "@testing-library/jest-dom";

// Mock matchMedia for jsdom
if (typeof window !== "undefined") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });

  // Mock BroadcastChannel in jsdom
  if (!window.BroadcastChannel) {
    class MockBroadcastChannel {
      name: string;
      onmessage: ((event: MessageEvent) => void) | null = null;
      static channels: Map<string, Set<MockBroadcastChannel>> = new Map();

      constructor(name: string) {
        this.name = name;
        if (!MockBroadcastChannel.channels.has(name)) {
          MockBroadcastChannel.channels.set(name, new Set());
        }
        MockBroadcastChannel.channels.get(name)!.add(this);
      }

      postMessage(message: any) {
        const set = MockBroadcastChannel.channels.get(this.name);
        if (set) {
          set.forEach((ch) => {
            if (ch !== this && ch.onmessage) {
              ch.onmessage(new MessageEvent("message", { data: message }));
            }
          });
        }
      }

      close() {
        const set = MockBroadcastChannel.channels.get(this.name);
        if (set) {
          set.delete(this);
        }
      }
    }

    (window as any).BroadcastChannel = MockBroadcastChannel;
  }
}
