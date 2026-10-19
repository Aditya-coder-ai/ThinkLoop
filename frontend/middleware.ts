import { NextResponse } from "next/server";
import type { NextRequest, NextFetchEvent, NextMiddleware } from "next/server";
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isProtectedRoute = createRouteMatcher(["/workspace(.*)"]);

/**
 * Validates that BOTH required Clerk keys are present, non-empty,
 * and contain genuine Clerk API prefixes (not mock/example values).
 *
 * If either key is missing or invalid on Vercel, clerkMiddleware MUST NOT
 * be invoked, as assertKey() throws an unhandled exception that causes
 * Vercel Edge 500 MIDDLEWARE_INVOCATION_FAILED errors.
 */
function hasValidClerkKeys(): boolean {
  const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
  const secretKey = process.env.CLERK_SECRET_KEY;

  if (!publishableKey || !secretKey) {
    return false;
  }

  // Reject dummy or example keys that cause DNS hangs or missing secret errors
  if (
    publishableKey === "pk_test_Y2xlcmsuZXhhbXBsZS5jb20k" ||
    publishableKey.includes("example.com") ||
    secretKey.includes("example")
  ) {
    return false;
  }

  const validPub = publishableKey.startsWith("pk_test_") || publishableKey.startsWith("pk_live_");
  const validSec = secretKey.startsWith("sk_test_") || secretKey.startsWith("sk_live_");

  return validPub && validSec;
}

/**
 * Standard authentication middleware for local dev or when Clerk is unconfigured.
 * Checks for local auth tokens without invoking external Clerk SDK endpoints.
 */
function fallbackMiddleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (pathname.startsWith("/workspace")) {
    const authToken = request.cookies.get("thinkloop_auth_token")?.value;
    if (!authToken) {
      const loginUrl = request.nextUrl.clone();
      loginUrl.pathname = "/";
      loginUrl.searchParams.set("reason", "unauthenticated");
      return NextResponse.redirect(loginUrl);
    }
  }
  return NextResponse.next();
}

// Lazy Clerk middleware instance
let cachedClerkHandler: NextMiddleware | null = null;

function getClerkHandler(): NextMiddleware {
  if (!cachedClerkHandler) {
    cachedClerkHandler = clerkMiddleware(async (auth, req) => {
      if (isProtectedRoute(req)) {
        const devToken = req.cookies.get("thinkloop_auth_token")?.value;
        const authObj = auth();
        if (!authObj.userId && !devToken) {
          return authObj.redirectToSignIn({ returnBackUrl: req.url });
        }
      }
    }) as unknown as NextMiddleware;
  }
  return cachedClerkHandler;
}

/**
 * Resilient Next.js Middleware with graceful error boundary.
 *
 * Guarantees that any internal Clerk initialization or network failure
 * on Vercel Edge Runtime fails open to standard cookie auth rather than
 * crashing with 500 MIDDLEWARE_INVOCATION_FAILED.
 */
export default async function middleware(request: NextRequest, event: NextFetchEvent) {
  if (hasValidClerkKeys()) {
    try {
      const handler = getClerkHandler();
      return await handler(request, event);
    } catch (error) {
      console.error("[Middleware] Clerk invocation failed on Vercel, falling back to local auth:", error);
      return fallbackMiddleware(request);
    }
  }

  return fallbackMiddleware(request);
}

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes
    "/(api|trpc)(.*)",
  ],
};
