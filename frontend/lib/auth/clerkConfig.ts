/**
 * Clerk Configuration Utilities
 *
 * Checks whether valid Clerk API credentials have been provided.
 * When running in local development without Clerk keys, Clerk falls back to a dummy key
 * which points to "clerk.example.com", causing 30-60s network hangs if not handled gracefully.
 */

export function isClerkConfigured(): boolean {
  const key = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
  if (!key) return false;
  if (key === "pk_test_Y2xlcmsuZXhhbXBsZS5jb20k") return false;
  if (key.includes("example.com")) return false;
  return key.startsWith("pk_test_") || key.startsWith("pk_live_");
}
