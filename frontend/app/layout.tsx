import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Thinkloop — Learn the way your mind works",
  description:
    "An AI-powered cognitive mentor that helps students build durable understanding through better questions.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
