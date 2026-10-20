import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";
import { SmoothCursor } from "@/components/ui/smooth-cursor";
import SplashCursor from "@/components/ui/SplashCursor";
import ClickSpark from "@/components/ui/ClickSpark";

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
          <SplashCursor
            size={1}
            force={1}
            swirl={3}
            trail={1.1}
            clickSplash
            colorSpeed={0.8}
          />
          <ClickSpark
            sparkCount={9}
            sparkSize={13}
            sparkRadius={28}
            duration={450}
            ring
          >
            <SmoothCursor />
            {children}
          </ClickSpark>
        </body>
      </html>
    </ClerkProvider>
  );
}
