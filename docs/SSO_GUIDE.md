# SSO Implementation Guide

## Overview

Enterprise SSO where each customer configures their own IdP (Microsoft Azure AD, Google Workspace, or custom OIDC like Okta/CyberArk). The **backend handles the entire OAuth flow** — credentials never leave the backend. The frontend redirects the user to a backend URL and receives app tokens back.

**Supported providers:** Microsoft (Azure AD), Google Workspace, Custom OIDC (Okta, CyberArk, etc.)

---

## Glossary

| Term                                             | What it is                                                                        | Who creates it                  | Who consumes it                           |
| ------------------------------------------------ | --------------------------------------------------------------------------------- | ------------------------------- | ----------------------------------------- |
| **IdP authorization code**                       | Short-lived code from Microsoft/Google after user logs in                         | IdP                             | Backend (`/auth/sso/callback`)            |
| **IdP tokens** (`id_token`)                      | Proves user identity. Used only to extract email. Never stored.                   | IdP                             | Backend (reads email, then discards)      |
| **App tokens** (`access_token`, `refresh_token`) | Platform JWT tokens for API access. Same as `POST /auth/login` issues.            | Backend                         | Frontend (NextAuth session)               |
| **`state`**                                      | CSRF protection UUID. Sent to IdP, echoed back. Maps to Redis entry.              | Backend (`/auth/sso/authorize`) | Backend (`/auth/sso/callback`)            |
| **`sso_code`**                                   | One-time code mapping to app tokens in Redis. Passed to frontend in redirect URL. | Backend (`/auth/sso/callback`)  | Frontend → Backend (`/auth/sso/exchange`) |

---

## Auth Flow

### Flow 1: Email Discovery → SSO

```
Frontend                        Backend                         IdP
   │                               │                              │
   │  1. POST /auth/discover       │                              │
   │      {email}                  │                              │
   │──────────────────────────────>│                              │
   │                               │                              │
   │  {auth_method:"sso",          │                              │
   │   sso_provider:"microsoft"}   │                              │
   │<──────────────────────────────│                              │
   │                               │                              │
   │  2. window.location.href =    │                              │
   │     BACKEND/auth/sso/authorize│                              │
   │     ?provider=microsoft       │                              │
   │     &email=user@acme.com      │                              │
   │──────────────────────────────>│                              │
   │                               │  3. Store state+email        │
   │                               │     in Redis (5min TTL)      │
   │                               │     Build IdP auth URL       │
   │                               │     HTTP 302 ───────────────>│
   │                               │                              │
   │                               │         4. User logs in      │
   │                               │                              │
   │                               │  5. HTTP 302 back            │
   │                               │     ?code=AUTH_CODE          │
   │                               │     &state=...               │
   │                               │<─────────────────────────────│
   │                               │                              │
   │                               │  6. Validate state (Redis)   │
   │                               │     Exchange code → id_token │
   │                               │     Extract email from IdP   │
   │                               │     Verify email match       │
   │                               │     Find user in DB          │
   │                               │     Generate app tokens      │
   │                               │     Store sso_code in Redis  │
   │                               │     (60s TTL)                │
   │                               │                              │
   │  7. HTTP 302 to               │                              │
   │     FRONTEND/sso-complete     │                              │
   │     ?code=sso_code            │                              │
   │<──────────────────────────────│                              │
   │                               │                              │
   │  8. signIn("credentials",     │                              │
   │     {sso_code})               │                              │
   │  → POST /auth/sso/exchange    │                              │
   │    {code: sso_code}           │                              │
   │──────────────────────────────>│                              │
   │                               │  9. Lookup sso_code in Redis │
   │                               │     Return app tokens        │
   │  {access_token,               │     Delete code (single-use) │
   │   refresh_token, user_uuid}   │                              │
   │<──────────────────────────────│                              │
   │                               │                              │
   │  10. Session created,         │                              │
   │      redirect to dashboard    │                              │
```

### Flow 2: Email Discovery → Password (unchanged)

```
Frontend                        Backend
   │                               │
   │  1. POST /auth/discover       │
   │      {email}                  │
   │──────────────────────────────>│
   │                               │
   │  {auth_method:"password"}     │
   │<──────────────────────────────│
   │                               │
   │  2. Show password field       │
   │     User enters password      │
   │                               │
   │  3. POST /auth/login          │
   │     {email, password}         │
   │──────────────────────────────>│
   │                               │
   │  {access_token, refresh_token}│
   │<──────────────────────────────│
   │                               │
   │  4. Session created           │
```

### Flow 3: Email Discovery → Both (password + SSO)

```
Frontend                        Backend
   │                               │
   │  POST /auth/discover {email}  │
   │──────────────────────────────>│
   │                               │
   │  {auth_method:"flexible",         │
   │   sso_provider:"microsoft",   │
   │   sso_provider_name:"Microsoft"}
   │<──────────────────────────────│
   │                               │
   │  Show password field           │
   │  + "Or sign in with Microsoft" │
```

---

## Backend API Reference

### Unauthenticated Endpoints

#### `POST /auth/discover`

Returns the org's auth method for a given email.

```
Request:  { "email": "user@acme.com" }

Response: {
  "auth_method": "password" | "sso" | "flexible",
  "sso_provider": "microsoft" | "google" | "oidc" | null,
  "sso_provider_name": "Microsoft" | "Google" | "CyberArk" | null
}
```

- Returns `{"auth_method": "password"}` for unknown users (does not reveal org existence).

#### `GET /auth/sso/authorize`

Redirects browser to IdP. **Frontend must set `window.location.href` to this URL** (not fetch/XHR).

```
Query params:
  provider  — "microsoft" | "google" | "oidc"
  email     — user's email (from discovery step)

Response: HTTP 302 redirect to IdP login page
```

#### `GET /auth/sso/callback`

IdP redirects here after user authenticates. **Frontend never calls this directly.** Backend processes and redirects to `{FRONTEND_URL}/sso-complete?code={sso_code}`.

On error, redirects to `{FRONTEND_URL}/sso-complete?error={error_type}`.

Possible error types: `invalid_state`, `sso_not_configured`, `token_exchange_failed`, `no_email`, `email_mismatch`, `user_not_found`, `account_inactive`.

#### `POST /auth/sso/exchange`

Exchanges a one-time `sso_code` for app tokens. Called by NextAuth `authorize()`.

```
Request:  { "code": "one_time_sso_code" }

Response (200): {
  "token_type": "Bearer",
  "user_uuid": "...",
  "access_token": "...",
  "refresh_token": "..."
}

Response (400): { "detail": "Invalid or expired code" }
```

Same response schema as `POST /auth/login`.

### Authenticated Admin Endpoints

#### `GET /auth/settings`

Returns org's SSO configuration. Requires `organizations: edit` permission.

```
Response: {
  "auth_method": "password" | "sso" | "flexible",
  "sso_provider": "microsoft" | "google" | "oidc" | null,
  "sso_provider_name": "Microsoft" | "Google" | "CyberArk" | null,
  "sso_client_id": "abc..." | null,
  "sso_tenant_id": "xyz..." | null,
  "sso_well_known_url": "https://..." | null,
  "sso_scopes": "openid email profile",
  "client_secret_set": true | false,
  "callback_url": "https://api.yourdomain.com/auth/sso/callback"
}
```

- `client_secret_set` indicates if a secret is configured (never exposes actual value).
- `callback_url` is shown so the admin can register it in their IdP's app registration.

#### `PUT /auth/settings`

Updates SSO configuration. Requires `organizations: edit` permission.

```
Request: {
  "auth_method": "sso",
  "sso_provider": "microsoft",
  "sso_provider_name": "Microsoft",
  "sso_client_id": "abc123",
  "sso_client_secret": "secret456",
  "sso_tenant_id": "xyz789",
  "sso_well_known_url": null,
  "sso_scopes": "openid email profile"
}
```

All fields are optional — only provided fields are updated. `sso_client_secret` is encrypted before storage; omitting it keeps the existing secret.

**Required fields by provider:**

| Field                | Microsoft   | Google   | Custom OIDC  |
| -------------------- | ----------- | -------- | ------------ |
| `sso_client_id`      | required    | required | required     |
| `sso_client_secret`  | required    | required | required     |
| `sso_tenant_id`      | required    | —        | —            |
| `sso_well_known_url` | —           | —        | required     |
| `sso_provider_name`  | "Microsoft" | "Google" | User-defined |

---

## IdP Setup Guides

### Microsoft (Azure AD)

#### 1. Create App Registration

1. Go to [Azure Portal](https://portal.azure.com) → **Azure Active Directory** → **App registrations** → **New registration**
2. Fill in:
   - **Name:** Your app name (e.g., `AssistCX SSO`)
   - **Supported account types:**
     - *Single tenant* — only users from your Azure AD tenant
     - *Multitenant* — users from any Azure AD tenant
   - **Redirect URI:**
     - Platform: **Web**
     - URI: `https://your-backend-domain.com/auth/sso/callback`
3. Click **Register**

#### 2. Copy Values

From the **Overview** page:
- **Application (client) ID** → `sso_client_id`
- **Directory (tenant) ID** → `sso_tenant_id`

#### 3. Create Client Secret

1. **Certificates & secrets** → **Client secrets** → **New client secret**
2. Add description, pick expiry, click **Add**
3. **Copy the Value immediately** (shown only once) → `sso_client_secret`

#### 4. API Permissions

1. **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated permissions**
2. Add:
   - `openid`
   - `email`
   - `profile`
   - `User.Read`
3. Click **"Grant admin consent for [your tenant]"**

#### 5. Configure in Platform

```json
PUT /auth/settings
{
  "auth_method": "sso",
  "sso_provider": "microsoft",
  "sso_provider_name": "Microsoft",
  "sso_client_id": "<Application (client) ID>",
  "sso_client_secret": "<Client secret Value>",
  "sso_tenant_id": "<Directory (tenant) ID>"
}
```

#### Common Azure AD Errors

| Error | Cause | Fix |
|---|---|---|
| `AADSTS700016` | Wrong client_id | Verify Application (client) ID |
| `AADSTS7000215` | Wrong client_secret | Regenerate secret, copy Value (not Secret ID) |
| `AADSTS50011` | Redirect URI mismatch | Add `https://your-backend/auth/sso/callback` in Authentication |
| `AADSTS65001` | Missing admin consent | Grant admin consent in API permissions |
| `AADSTS90002` | Wrong tenant_id | Verify Directory (tenant) ID |

---

### Google Workspace

#### 1. Create OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com) → **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. Fill in:
   - **Application type:** Web application
   - **Name:** Your app name
   - **Authorized redirect URIs:** `https://your-backend-domain.com/auth/sso/callback`
4. Click **Create**

#### 2. Copy Values

From the created credential:
- **Client ID** → `sso_client_id`
- **Client secret** → `sso_client_secret`

#### 3. Enable APIs

1. Go to **APIs & Services** → **Library**
2. Search and enable **Google People API** (for profile/email access)

#### 4. Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **Internal** (for Google Workspace org-only) or **External**
3. Add scopes: `openid`, `email`, `profile`
4. Add your domain to authorized domains if needed
5. Publish the app (move out of testing mode for production)

#### 5. Configure in Platform

```json
PUT /auth/settings
{
  "auth_method": "sso",
  "sso_provider": "google",
  "sso_provider_name": "Google",
  "sso_client_id": "<Client ID>",
  "sso_client_secret": "<Client secret>"
}
```

#### Common Google Errors

| Error | Cause | Fix |
|---|---|---|
| `redirect_uri_mismatch` | Redirect URI not registered | Add exact URI in Credentials → Authorized redirect URIs |
| `access_denied` | User not in allowed domain | Check OAuth consent screen → User type (Internal vs External) |
| `invalid_client` | Wrong client_id or secret | Verify credentials in Cloud Console |
| `consent_required` | App in testing mode | Add user as test user, or publish the app |

---

### Custom OIDC (Okta, CyberArk, OneLogin, etc.)

#### 1. Create Application in Your IdP

The exact steps vary by provider, but generally:

1. Create a new **Web Application** or **OIDC App Integration**
2. Set **Sign-in redirect URI:** `https://your-backend-domain.com/auth/sso/callback`
3. Set **Grant type:** Authorization Code
4. Note down:
   - **Client ID** → `sso_client_id`
   - **Client secret** → `sso_client_secret`

#### 2. Find the Well-Known URL

Every OIDC provider has a discovery endpoint. Common patterns:

| Provider | Well-Known URL Format |
|---|---|
| **Okta** | `https://your-domain.okta.com/.well-known/openid-configuration` |
| **CyberArk** | `https://your-tenant.id.cyberark.cloud/.well-known/openid-configuration` |
| **OneLogin** | `https://your-domain.onelogin.com/oidc/2/.well-known/openid-configuration` |
| **Auth0** | `https://your-domain.auth0.com/.well-known/openid-configuration` |
| **Keycloak** | `https://your-host/realms/your-realm/.well-known/openid-configuration` |

Verify it by opening the URL in a browser — it should return a JSON with `authorization_endpoint`, `token_endpoint`, `jwks_uri`, etc.

#### 3. Required Scopes

Ensure your IdP app grants these scopes:
- `openid` (required — enables OIDC)
- `email` (required — we need the user's email)
- `profile` (optional — provides display name)

#### 4. Configure in Platform

```json
PUT /auth/settings
{
  "auth_method": "sso",
  "sso_provider": "oidc",
  "sso_provider_name": "CyberArk",
  "sso_client_id": "<Client ID>",
  "sso_client_secret": "<Client secret>",
  "sso_well_known_url": "https://your-tenant.id.cyberark.cloud/.well-known/openid-configuration"
}
```

#### Common OIDC Errors

| Error | Cause | Fix |
|---|---|---|
| Discovery URL unreachable | Wrong well_known_url or network issue | Verify URL returns JSON in browser |
| `invalid_client` | Wrong client_id or secret | Verify in IdP admin console |
| `redirect_uri_mismatch` | Redirect URI not registered in IdP | Add `/auth/sso/callback` in IdP app config |
| No email in token | `email` scope not granted | Add `email` scope in IdP app settings |
| Issuer mismatch | Token issuer doesn't match discovery doc | Verify well_known_url matches IdP's actual issuer |

---

## Frontend Implementation Guide

### 1. Login Form — Email-First Discovery

Replace the current login form with an email-first state machine:

```
State: "email" → "discovering" → "password" | "sso_redirect" | "both" | "error"
```

| State          | UI                                                       |
| -------------- | -------------------------------------------------------- |
| `email`        | Email field + "Continue" button. No SSO buttons.         |
| `discovering`  | Loading spinner on Continue button                       |
| `password`     | Email (with back option) + password field + Login button |
| `sso_redirect` | "Redirecting to {provider_name}..." then navigate away   |
| `both`         | Password field + "Or sign in with {provider_name}" link  |
| `error`        | Toast "Account not found" → back to `email` state        |

**Discovery call:**

```ts
const res = await fetch(`${backendUrl}/auth/discover`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email }),
});
const data = await res.json();
// data.auth_method → "password" | "sso" | "flexible"
```

**SSO redirect (when auth_method is "sso", or user clicks SSO link in "both" mode):**

```ts
// This is a full page navigation, NOT a fetch call
window.location.href = `${backendUrl}/auth/sso/authorize?provider=${data.sso_provider}&email=${encodeURIComponent(email)}`;
```

### 2. SSO Complete Page

Create: `app/(authentication)/sso-complete/page.tsx`

This page handles the redirect back from the backend after IdP authentication.

```tsx
'use client';

import { useSearchParams, useRouter } from 'next/navigation';
import { signIn } from 'next-auth/react';
import { useEffect } from 'react';

export default function SSOCompletePage() {
  const params = useSearchParams();
  const router = useRouter();
  const code = params.get('code');
  const error = params.get('error');

  useEffect(() => {
    if (error) {
      router.push(`/login?error=${error}`);
      return;
    }
    if (code) {
      signIn('credentials', { sso_code: code, redirect: false }).then(
        (result) => {
          if (result?.ok) {
            router.push('/'); // or decode token for first available route
          } else {
            router.push('/login?error=sso_exchange_failed');
          }
        },
      );
    }
  }, [code, error]);

  return <div>Signing in...</div>; // loading spinner
}
```

### 3. NextAuth — Add SSO Code Support

In `pages/api/auth/[...nextauth].ts`, update the CredentialsProvider:

```ts
credentials: {
  email: { label: "Email", type: "email" },
  password: { label: "Password", type: "password" },
  sso_code: { label: "SSO Code", type: "text" },  // NEW
},
authorize: async (credentials) => {
  // SSO code exchange
  if (credentials?.sso_code) {
    const res = await fetch(`${process.env.NEXTAUTH_BACKEND}/auth/sso/exchange`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: credentials.sso_code }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    return {
      id: data.user_uuid,
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
    };
  }

  // Existing password auth (unchanged)
  // ...
}
```

### 4. Admin Settings Page

Create: `app/(dashboard)/settings/authentication/page.tsx`

Form with:

- **Auth method** radio: Password only / SSO only / Both
- **Provider** select (visible when SSO/Both): Microsoft / Google / Custom OIDC
- **Provider fields** (change based on selection):
  - Microsoft: Client ID, Client Secret, Tenant ID
  - Google: Client ID, Client Secret
  - Custom OIDC: Provider Name, Well-Known URL, Client ID, Client Secret
- **Callback URL** (read-only, copyable): shown from `GET /auth/settings` response
- **Save** button → `PUT /auth/settings`

### 5. Proxy/Middleware

Allow unauthenticated access to `/sso-complete` (the redirect lands here before the user has a session).

### 6. Settings Navigation

Add "Authentication" tab to the settings menu, linking to `/settings/authentication`.

---

## Microsoft Teams Integration (Silent Auth)

When AssistCX runs inside a Microsoft Teams iframe, users are already authenticated with Microsoft. Instead of forcing a second login via the org's configured SSO provider, we use the Teams context to silently authenticate.

This is enabled by default for all orgs — no admin configuration needed.

### Azure App Registration Setup for Teams SSO

Teams silent auth requires additional configuration on the same Azure AD app registration used by the platform.

#### 1. Expose an API

1. Go to **Azure Portal** → **App registrations** → select your app
2. Click **Expose an API** in the left sidebar
3. Click **Set** next to "Application ID URI" and set it to:
   ```
   api://your-frontend-host/YOUR_CLIENT_ID
   ```
   For local development: `api://localhost:3001/YOUR_CLIENT_ID`
   For production: `api://teams.yourdomain.com/YOUR_CLIENT_ID`

   (No `http://`, no trailing slash)

4. Click **Add a scope**:
   - **Scope name:** `access_as_user`
   - **Who can consent:** Admins and users
   - **Admin consent display name:** Access AssistCX as user
   - **Admin consent description:** Allow Teams to access AssistCX on behalf of the signed-in user
   - **State:** Enabled
   - Click **Add scope**

5. Click **Add a client application** — add these Teams client IDs one at a time, checking the `access_as_user` scope for each:
   - `1fec8e78-bce4-4aaf-ab1b-5451cc387264` (Teams desktop/mobile)
   - `5e3ce6c0-2b1f-4285-8d4b-75ee78787346` (Teams web)

#### 2. Authentication

1. Click **Authentication** in the left sidebar
2. Under **Single-page application** (click "Add a platform" if not present):
   - **Redirect URI:** `https://localhost:3001` (or your production frontend URL)
3. Under **Implicit grant and hybrid flows**, check:
   - **Access tokens**
   - **ID tokens**

#### 3. Summary of Required Values

| Value | Where to find it | Used for |
|---|---|---|
| **Application (client) ID** | App registration → Overview | `CLIENT_ID` in `.env` |
| **Application ID URI** | Expose an API | Audience (`aud`) in Teams token |
| **Teams client IDs** | Pre-authorized (step 1.5 above) | Allow Teams apps to request tokens |

### Flow

```
Teams iframe loads AssistCX
  → Teams JS SDK: getAuthToken() → Microsoft token
  → Frontend calls: POST /auth/teams { teams_token: "..." }
  → Backend:
      1. Validate Microsoft token (verify signature via Microsoft JWKS, check aud/exp)
      2. Extract email from token claims (preferred_username / upn / email)
      3. Look up user by email → find org schema → verify user is active
      4. create_user_session() → generate app tokens
      5. Return tokens (same response as /auth/login)
  → Frontend stores tokens in session, app loads
```

### Backend Endpoint

#### `POST /auth/teams` (unauthenticated)

```
Request:  { "teams_token": "eyJ..." }

Response (200): {
  "token_type": "Bearer",
  "user_uuid": "...",
  "access_token": "...",
  "refresh_token": "..."
}

Response (401): { "detail": "Invalid Teams token" }
Response (404): { "detail": "User not found" }
```

### Frontend (Teams Tab)

```ts
import * as microsoftTeams from '@microsoft/teams-js';

// Initialize Teams SDK
await microsoftTeams.app.initialize();

// Get Teams SSO token
const teamsToken = await microsoftTeams.authentication.getAuthToken();

// Exchange for app tokens
const res = await fetch(`${backendUrl}/auth/teams`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ teams_token: teamsToken }),
});
const data = await res.json();
// data.access_token, data.refresh_token → store in session
```

### Common Teams SSO Errors

| Error | Cause | Fix |
|---|---|---|
| `Audience doesn't match` | Application ID URI format mismatch | Token aud is `api://host/client_id` — backend accepts any aud containing the client_id |
| `resourceDisabled` | `access_as_user` scope not configured | Add scope in Expose an API |
| `invalid_grant` | Teams client IDs not pre-authorized | Add both Teams client IDs in Expose an API |
| `getAuthToken()` fails | App not registered as Teams tab | Verify Teams app manifest has `webApplicationInfo` with correct `id` and `resource` |
| `User not found` | User's email not in platform | User must be created in platform before Teams auth works |

### Why this is safe

- The Teams token is cryptographically signed by Microsoft and verified against Microsoft's JWKS
- The user must exist in the platform (no auto-provisioning)
- This is the standard pattern used by Salesforce, ServiceNow, Jira, and other enterprise apps inside Teams
- The org's SSO provider (CyberArk, Okta, etc.) is not bypassed for web login — Teams auth is a separate trusted entry point

---

## User Provisioning

### Current Behavior

SSO handles **authentication** (proving identity), not **provisioning** (creating accounts). Users must be manually created in the platform by an admin before they can log in via SSO. If a user authenticates with the IdP but doesn't exist in the platform, they receive a `user_not_found` error.

This is a deliberate design choice — the admin controls who has access, and SSO only controls how they prove their identity.

### What Customers May Ask

| Question | Answer |
|---|---|
| "When I add a user in Azure AD, do they automatically get an account?" | No. An admin must create the user in the platform first. |
| "When I disable a user in Azure AD, do they lose access?" | They can't SSO login anymore (IdP rejects them), but their platform account remains until an admin deactivates it. |
| "Do you support SCIM?" | Not currently. User management is done through the platform's admin UI or API. |

### Provisioning Levels (Industry Context)

| Level | What it does | Our status |
|---|---|---|
| **Manual** | Admin creates users in the platform UI/API | Current |
| **JIT (Just-In-Time)** | Auto-create user on first SSO login using IdP claims (email, name) with a default role | Planned |
| **SCIM** | IdP pushes user create/update/disable events to a SCIM API (`/scim/v2/Users`) for full lifecycle management | Roadmap |

### Why Customer-Owned Credentials

Each customer creates their own app registration (Microsoft, Google, or OIDC provider) and provides the credentials to the platform. This is the enterprise standard used by Slack, Salesforce, ServiceNow, and other B2B SaaS products.

**Why not a single platform-owned app registration shared by all customers?**

- Customer's IdP policies (Conditional Access, MFA, device compliance) only apply when users sign into the **customer's own** app registration
- Customer can independently revoke access without involving the platform vendor
- Customer's security team can audit their own app registration
- No single point of failure across customers
- Required for custom OIDC providers (Okta, CyberArk) which are always customer-owned
- Stronger security posture — the platform never holds customer IdP credentials on a shared basis

---

## Security Notes

| Concern              | How it's handled                                                                  |
| -------------------- | --------------------------------------------------------------------------------- |
| Client secrets       | Encrypted at rest (Fernet). Never sent to frontend.                               |
| Tokens in URL        | Only `sso_code` appears in URL — single-use, 60s TTL. Actual tokens never in URL. |
| CSRF                 | `state` parameter stored in Redis, validated on callback, single-use.             |
| Email validation     | Email from discovery stored in state, verified against IdP's `id_token`.          |
| Open redirect        | Frontend URL is a backend env var, not passed dynamically.                        |
| SSO enforcement      | `POST /auth/login` returns 403 when org is SSO-only.                              |
| Unknown users        | `/auth/discover` returns `"password"` for unknown emails (no org leak).           |
| No auto-provisioning | Users must exist in platform before SSO login works.                              |
