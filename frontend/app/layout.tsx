import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";
import { SmoothCursor } from "@/components/ui/smooth-cursor";

import { getClerkPublishableKey, isClerkConfigured } from "@/lib/auth/clerkConfig";

export const metadata: Metadata = {
  title: "Thinkloop — Learn the way your mind works",
  description:
    "An AI-powered cognitive mentor that helps students build durable understanding through better questions.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const publishableKey = getClerkPublishableKey();
  const clerkReady = isClerkConfigured();

  return (
    <ClerkProvider
      publishableKey={publishableKey}
      {...(!clerkReady ? { clerkJSUrl: "/clerk-noop.js" } : {})}
    >
      <html lang="en" data-theme="light" suppressHydrationWarning>
        <body>
          <SmoothCursor />
          {children}
        </body>
      </html>
    </ClerkProvider>
  );
}
