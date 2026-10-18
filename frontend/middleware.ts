import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Protect /workspace routes
  if (pathname.startsWith("/workspace")) {
    const authToken = request.cookies.get("thinkloop_auth_token")?.value;

    // Fast-fail cookie presence check
    if (!authToken) {
      const loginUrl = new URL("/", request.url);
      loginUrl.searchParams.set("reason", "unauthenticated");
      return NextResponse.redirect(loginUrl);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/workspace/:path*", "/workspace"],
};
