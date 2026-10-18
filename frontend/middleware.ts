import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isProtectedRoute = createRouteMatcher(["/workspace(.*)"]);

const hasClerkKeys = Boolean(
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY || process.env.CLERK_SECRET_KEY
);

export default hasClerkKeys
  ? clerkMiddleware((auth, req) => {
      if (isProtectedRoute(req)) {
        const devToken = req.cookies.get("thinkloop_auth_token")?.value;
        if (!auth().userId && !devToken) {
          return auth().redirectToSignIn({ returnBackUrl: req.url });
        }
      }
    })
  : function middleware(request: NextRequest) {
      const { pathname } = request.nextUrl;
      if (pathname.startsWith("/workspace")) {
        const authToken = request.cookies.get("thinkloop_auth_token")?.value;
        if (!authToken) {
          const loginUrl = new URL("/", request.url);
          loginUrl.searchParams.set("reason", "unauthenticated");
          return NextResponse.redirect(loginUrl);
        }
      }
      return NextResponse.next();
    };

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
