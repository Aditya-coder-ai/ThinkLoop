import { SignIn } from "@clerk/nextjs";
import { isClerkConfigured } from "@/lib/auth/clerkConfig";
import { AuthFallbackCard } from "@/app/components/AuthFallbackCard";

export default function SignInPage() {
  const clerkReady = isClerkConfigured();

  return (
    <div
      className="auth-container"
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1.5rem",
        background: "var(--paper)",
      }}
    >
      {clerkReady ? (
        <SignIn path="/sign-in" routing="path" signUpUrl="/sign-up" fallbackRedirectUrl="/workspace" />
      ) : (
        <AuthFallbackCard mode="sign-in" />
      )}
    </div>
  );
}
