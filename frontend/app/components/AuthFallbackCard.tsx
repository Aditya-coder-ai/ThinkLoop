"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { signIn } from "@/lib/auth";
import { ArrowRight, Copy, Check, Terminal, Sparkles, ShieldCheck } from "lucide-react";

interface AuthFallbackCardProps {
  mode: "sign-up" | "sign-in";
}

export function AuthFallbackCard({ mode }: AuthFallbackCardProps) {
  const router = useRouter();
  const [name, setName] = useState("Aditya");
  const [showGuide, setShowGuide] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleSignIn = () => {
    const cleanName = (name || "Aditya").trim();
    const sanitizedHandle = cleanName.toLowerCase().replace(/[^a-z0-9_-]/g, "_").slice(0, 32);
    const authId = `dev_${sanitizedHandle}`;
    const userProfile = {
      id: "u_dev_1",
      authId,
      name: cleanName,
      email: `${sanitizedHandle}@thinkloop.ai`,
      timezone: "UTC",
      dailyGoalMinutes: 30,
      voiceEnabled: true,
    };
    signIn(authId, userProfile);
    router.push("/workspace");
  };

  const copyCommand = () => {
    const cmd = `.\\setup_clerk.ps1 -PublishableKey "pk_test_..." -SecretKey "sk_test_..." -ClerkDomain "your-app.clerk.accounts.dev"`;
    navigator.clipboard.writeText(cmd);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      style={{
        maxWidth: "480px",
        width: "100%",
        background: "var(--white)",
        border: "1px solid var(--line-strong)",
        borderRadius: "16px",
        padding: "32px",
        boxShadow: "0 20px 40px rgba(0, 0, 0, 0.08)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "20px" }}>
        <a href="/" style={{ display: "inline-flex", alignItems: "center", gap: "8px", fontWeight: 700, fontSize: "16px" }}>
          <span style={{ color: "var(--clay)" }}>●</span> thinkloop
        </a>
        <span
          style={{
            fontFamily: "var(--mono)",
            fontSize: "11px",
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            background: "color-mix(in srgb, var(--olive) 15%, transparent)",
            color: "var(--olive-deep)",
            padding: "4px 10px",
            borderRadius: "12px",
            display: "inline-flex",
            alignItems: "center",
            gap: "5px",
          }}
        >
          <ShieldCheck size={12} /> Local Dev Mode
        </span>
      </div>

      <h1
        style={{
          fontFamily: "var(--serif)",
          fontSize: "28px",
          fontWeight: 600,
          lineHeight: "1.2",
          marginBottom: "8px",
        }}
      >
        {mode === "sign-up" ? "Get started with Thinkloop" : "Sign in to Thinkloop"}
      </h1>

      <p style={{ color: "var(--ink-soft)", fontSize: "14px", lineHeight: "1.5", marginBottom: "24px" }}>
        Clerk cloud credentials are not configured in this local environment. You can enter the workspace instantly as a demo learner.
      </p>

      <div style={{ marginBottom: "24px" }}>
        <label
          htmlFor="learner-name"
          style={{
            display: "block",
            fontSize: "12px",
            fontFamily: "var(--mono)",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: "var(--ink-soft)",
            marginBottom: "8px",
          }}
        >
          Learner Name
        </label>
        <div style={{ display: "flex", gap: "10px", marginBottom: "16px" }}>
          <input
            id="learner-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Enter your name"
            required
            style={{
              flex: 1,
              padding: "12px 14px",
              borderRadius: "8px",
              border: "1px solid var(--line-strong)",
              background: "var(--paper)",
              color: "var(--ink)",
              fontSize: "14px",
              fontFamily: "var(--sans)",
              outline: "none",
            }}
          />
        </div>

        <button
          type="button"
          onClick={handleSignIn}
          className="button button-primary"
          style={{
            width: "100%",
            padding: "14px",
            borderRadius: "8px",
            cursor: "pointer",
            fontWeight: 600,
            fontSize: "14px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "8px",
          }}
        >
          <Sparkles size={16} /> Continue as {name || "Demo Learner"} <ArrowRight size={16} />
        </button>
      </div>

      <div style={{ borderTop: "1px solid var(--line)", paddingTop: "18px" }}>
        <button
          type="button"
          onClick={() => setShowGuide(!showGuide)}
          style={{
            background: "none",
            border: "none",
            color: "var(--ink-soft)",
            fontSize: "13px",
            cursor: "pointer",
            padding: 0,
            display: "flex",
            alignItems: "center",
            gap: "6px",
          }}
        >
          <Terminal size={14} />
          <span>{showGuide ? "Hide Clerk configuration setup" : "How to connect real Clerk authentication?"}</span>
        </button>

        {showGuide && (
          <div
            style={{
              marginTop: "14px",
              padding: "14px",
              borderRadius: "8px",
              background: "var(--paper)",
              border: "1px solid var(--line)",
              fontSize: "12px",
              lineHeight: "1.6",
            }}
          >
            <p style={{ margin: "0 0 10px 0", color: "var(--ink)" }}>
              Run the setup script with your keys from{" "}
              <a
                href="https://dashboard.clerk.com"
                target="_blank"
                rel="noreferrer"
                style={{ color: "var(--clay)", textDecoration: "underline" }}
              >
                dashboard.clerk.com
              </a>
              :
            </p>
            <div
              style={{
                position: "relative",
                background: "rgba(0, 0, 0, 0.05)",
                padding: "10px",
                borderRadius: "6px",
                fontFamily: "var(--mono)",
                fontSize: "11px",
                wordBreak: "break-all",
              }}
            >
              <code>{'.\\setup_clerk.ps1 -PublishableKey "pk_test_..." -SecretKey "sk_test_..." -ClerkDomain "..."'}</code>
              <button
                type="button"
                onClick={copyCommand}
                style={{
                  position: "absolute",
                  top: "6px",
                  right: "6px",
                  background: "var(--white)",
                  border: "1px solid var(--line)",
                  borderRadius: "4px",
                  padding: "4px 8px",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                  fontSize: "11px",
                }}
              >
                {copied ? <Check size={12} color="green" /> : <Copy size={12} />}
                <span>{copied ? "Copied" : "Copy"}</span>
              </button>
            </div>
          </div>
        )}
      </div>

      <div style={{ marginTop: "20px", textAlign: "center" }}>
        <a href="/" style={{ color: "var(--ink-soft)", fontSize: "13px", textDecoration: "none" }}>
          ← Back to Home
        </a>
      </div>
    </div>
  );
}
