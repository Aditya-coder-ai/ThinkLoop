#!/usr/bin/env pwsh
# ThinkLoop — Clerk Integration Setup Script
# Run this ONCE after getting your Clerk API keys from https://dashboard.clerk.com
# Usage:
#   .\setup_clerk.ps1 -PublishableKey "pk_test_..." -SecretKey "sk_test_..." -ClerkDomain "helpful-elk-14.clerk.accounts.dev"
#
# Find ClerkDomain in Dashboard -> API Keys: the domain from the Publishable Key URL

param(
    [Parameter(Mandatory=$true)]
    [string]$PublishableKey,

    [Parameter(Mandatory=$true)]
    [string]$SecretKey,

    [Parameter(Mandatory=$true)]
    [string]$ClerkDomain
)

$ErrorActionPreference = "Stop"

Write-Host "=== ThinkLoop Clerk Integration Setup ===" -ForegroundColor Cyan

# 1. Create frontend/.env.local
$frontendEnv = @"
# ThinkLoop Frontend — Clerk Authentication
# Auto-generated — DO NOT COMMIT TO GIT

NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$PublishableKey
CLERK_SECRET_KEY=$SecretKey

NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/workspace
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/workspace
"@

$frontendEnvPath = "d:\Thinkloop\ThinkLoop\frontend\.env.local"
Set-Content -Path $frontendEnvPath -Value $frontendEnv -Encoding UTF8
Write-Host "[OK] Created frontend/.env.local" -ForegroundColor Green

# 2. Update backend .env with Clerk auth settings
$clerkJwksUrl  = "https://$ClerkDomain/.well-known/jwks.json"
$clerkIssuer   = "https://$ClerkDomain"
# Clerk does not require audience claim by default; empty string disables aud check
$clerkAudience = ""

$backendEnvPath = "d:\Thinkloop\ThinkLoop\.env"
$backendEnv = Get-Content $backendEnvPath -Raw

$backendEnv = $backendEnv -replace "AUTH_JWKS_URL=.*", "AUTH_JWKS_URL=$clerkJwksUrl"
$backendEnv = $backendEnv -replace "AUTH_ISSUER=.*",   "AUTH_ISSUER=$clerkIssuer"
$backendEnv = $backendEnv -replace "AUTH_AUDIENCE=.*", "AUTH_AUDIENCE=$clerkAudience"

Set-Content -Path $backendEnvPath -Value $backendEnv -Encoding UTF8
Write-Host "[OK] Updated .env with Clerk JWKS URL: $clerkJwksUrl" -ForegroundColor Green

Write-Host ""
Write-Host "=== Setup Complete! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Start dev servers:"
Write-Host "  Terminal 1 (backend) : cd d:\Thinkloop\ThinkLoop\backend && uvicorn app.main:app --reload"
Write-Host "  Terminal 2 (frontend): cd d:\Thinkloop\ThinkLoop\frontend && npm run dev"
