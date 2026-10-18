import { SignUp } from "@clerk/nextjs";
import { isClerkConfigured } from "@/lib/auth/clerkConfig";
import { AuthFallbackCard } from "@/app/components/AuthFallbackCard";

export default function SignUpPage() {
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
        <SignUp path="/sign-up" routing="path" signInUrl="/sign-in" fallbackRedirectUrl="/workspace" />
      ) : (
        <AuthFallbackCard mode="sign-up" />
      )}
    </div>
  );
}
