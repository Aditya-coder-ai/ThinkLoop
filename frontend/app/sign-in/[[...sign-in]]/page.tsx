import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="auth-container" style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: "1.5rem" }}>
      <SignIn path="/sign-in" routing="path" signUpUrl="/sign-up" fallbackRedirectUrl="/workspace" />
    </div>
  );
}
