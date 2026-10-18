/**
 * Thinkloop Local Clerk Shim
 *
 * Loaded in development when NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is not configured.
 * Replaces the remote call to clerk.example.com to prevent 30-60 second DNS/TCP hangs.
 */
(function () {
  if (typeof window === "undefined") return;

  window.Clerk = window.Clerk || {
    loaded: true,
    version: "5.7.5-local",
    load: function () {
      return Promise.resolve();
    },
    addListener: function () {
      return function () {};
    },
    onComponentsReady: Promise.resolve(),
    mountSignUp: function () {},
    unmountSignUp: function () {},
    mountSignIn: function () {},
    unmountSignIn: function () {},
    mountUserButton: function () {},
    unmountUserButton: function () {},
    client: {
      sessions: [],
      activeSessions: [],
      signUp: {},
      signIn: {},
    },
    session: null,
    user: null,
    telemetry: {
      record: function () {},
    },
  };
})();
