# SSO Implementation Guide

## What is SSO and Why Do We Use It?

SSO (Single Sign-On) lets users log into our app using their existing corporate identity (Microsoft, Google, Okta, etc.) instead of a separate password. We outsource identity verification to these providers — we never see or store the user's corporate password.

The protocol we use is **OIDC (OpenID Connect)**, built on **OAuth 2.0**. The specific pattern is called the **Authorization Code Flow** (also known as "three-legged OAuth" because three parties are involved: the user, our app, and the identity provider).

**Supported providers:** Microsoft (Azure AD / Entra ID), Google Workspace, Custom OIDC (Okta, CyberArk, OneLogin, etc.)

---

## Glossary

| Term | What it is | Who creates it | Who consumes it |
|---|---|---|---|
| **IdP (Identity Provider)** | External service that authenticates users (Microsoft, Google, Okta). We trust their answer about who the user is. | — | — |
| **IdP authorization code** | Short-lived, single-use code from the IdP after user authenticates. Not the user's identity — just a ticket to ask the IdP "who logged in?" | IdP | Backend (`/auth/sso/callback`) |
| **IdP tokens** (`id_token`) | A cryptographically signed JWT proving user identity. Contains email, name. Used only to extract email, then discarded. Never stored. | IdP | Backend (reads email, then discards) |
| **App tokens** (`access_token`, `refresh_token`) | Platform JWT tokens for API access. Same as what `POST /auth/login` issues for password login. | Backend | Frontend (NextAuth session) |
| **`state`** | A random value **we** generate to prevent CSRF attacks. We store it in Redis, send it to the IdP in the redirect URL, and the IdP echoes it back untouched. It proves the callback matches a login **we** initiated. It does NOT prove the user authenticated — only the `code` proves that. | Backend (`/auth/sso/authorize`) | Backend (`/auth/sso/callback`) |
| **`sso_code`** | A one-time intermediary code we create after successful authentication. Maps to app tokens in Redis. Passed to the frontend via URL redirect — safer than putting real tokens in the URL. | Backend (`/auth/sso/callback`) | Frontend → Backend (`/auth/sso/exchange`) |
| **OIDC Discovery** | A `.well-known/openid-configuration` URL that every OIDC provider publishes. Returns a JSON document with the IdP's endpoints (authorization, token, JWKS, issuer). We cache this in Redis for 1 hour. | IdP | Backend |
| **JWKS** | JSON Web Key Set — the IdP's public keys used to verify ID token signatures. We fetch these to cryptographically prove the id_token was actually issued by the IdP and not forged. | IdP | Backend |
| **ENVIRONMENT_SECRET** | An env var used to derive a Fernet (AES-128-CBC) encryption key. Used to encrypt/decrypt the SSO client_secret at rest in the database. If this value changes, all stored secrets become unrecoverable. | Ops/DevOps | Backend (`crypto_utils.py`) |

---

## The Complete SSO Login Flow (Step by Step)

This is the core of how SSO works. Every step exists for a specific reason — skip any one and the system is either broken or insecure.

### Step 1: User types their email

**Who:** User
**What:** User enters `john@acme.com` on the login page.
**Why this step exists:** We need to know WHO is trying to log in so we can look up their organization and figure out HOW they should authenticate. Without this, we don't know the org, the provider, or whether this user even uses SSO.

### Step 2: Frontend discovers the auth method

**Who:** Frontend → Backend
**Endpoint:** `POST /auth/discover`
**Request:** `{ "email": "john@acme.com" }`

**What happens internally:**
1. Backend calls `get_user_schema("john@acme.com")` to find which org/DB schema this email belongs to.
2. Reads the org's `auth_config` from the `Configuration` table.
3. Returns the `auth_method` (password, sso, or flexible).

**Response if SSO:** `{ "auth_method": "sso", "sso_provider": "microsoft", "sso_provider_name": "Acme Microsoft SSO" }`
**Response if password:** `{ "auth_method": "password", "sso_provider": null }`

**Why this step exists:** Different orgs have different setups. Acme uses Microsoft, Beta Inc uses Google, Gamma LLC uses passwords. This step tells the frontend which login UI to show (password field vs SSO button). Without it, the frontend would have to guess.

**Security:** Unknown emails return `"password"` — we never reveal whether an org exists or uses SSO.

### Step 3: Browser redirects to the IdP

**Who:** Frontend → Backend → IdP
**Endpoint:** `GET /auth/sso/authorize?provider=microsoft&email=john@acme.com`

**This is a full browser navigation (window.location.href), NOT an AJAX/fetch call.**

**What happens internally:**
1. Backend looks up the org's SSO config (client_id, tenant_id, scopes).
2. **Generates a cryptographic state token:** `secrets.token_urlsafe(32)` — reads 32 bytes from `/dev/urandom`, base64url-encodes them. This is 256 bits of entropy (same strength as AES-256). Completely unguessable.
3. **Stores the state in Redis** with a 5-minute TTL: `sso:state:{state}` → `{ provider, email, org_schema }`.
4. Builds the IdP authorization URL with query params: `client_id`, `redirect_uri`, `response_type=code`, `scope`, `state`.
5. Returns **HTTP 302** (redirect) to the IdP URL.

**Example redirect URL:**
```
https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize
  ?client_id=abc123
  &redirect_uri=https://api.yourdomain.com/auth/sso/callback
  &response_type=code
  &scope=openid+email+profile
  &state=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
```

**Why this step exists:** We can't verify the user's corporate identity ourselves — only Microsoft/Google can. So we redirect the browser to them. But we need to do it securely:
- **Why the state token?** It proves this callback came from a login WE started (CSRF protection). Without it, an attacker could craft a fake callback URL and trick a user's browser into hitting it.
- **Why is state unguessable?** It uses a CSPRNG (cryptographically secure pseudo-random number generator). With 256 bits of entropy, brute-forcing would require ~10^77 guesses.
- **Why 5-minute TTL?** If the user abandons the login, the state auto-expires. Limits the attack window.

**Important:** The state does NOT come from Microsoft. WE create it. Microsoft just holds it and passes it back untouched.

### Step 4: User authenticates at the Identity Provider

**Who:** User + IdP (Microsoft/Google/etc.)
**What:** The user's browser is now on the IdP's login page. The user enters their corporate password, completes MFA, etc.

**Why this step exists:** This is the entire point of SSO. Instead of our app managing passwords, MFA, password resets, and brute-force protection, we let the IdP handle all of it. They have dedicated security teams and infrastructure for this. We're outsourcing identity verification.

**Key point:** This happens entirely on the IdP's domain. Our backend NEVER sees the user's corporate password.

### Step 5: IdP redirects back with a code (not the email)

**Who:** IdP → User's Browser → Backend
**Endpoint:** `GET /auth/sso/callback?code=0.AXEA...&state=dBjft...`

After the user authenticates, the IdP redirects the browser back to our callback URL with two params:
- `code` — a short-lived, single-use authorization code
- `state` — the same state value we sent in step 3 (echoed back untouched)

**Why does the IdP return a code instead of just saying "john@acme.com authenticated successfully"?**

Because the redirect happens **through the user's browser, which is untrusted.** If the IdP put the email in the URL like `?email=john@acme.com&status=success`, anyone could type that URL into a browser and our backend would log them in — no IdP involved, no password needed. The URL is user-controlled; you can put anything you want in it.

Instead, the IdP returns an opaque `code` that means nothing by itself. The code can ONLY be redeemed:
1. By calling the IdP's token endpoint **server-to-server** (not through the browser)
2. By presenting the `client_secret` that only our backend knows
3. Once — it's single-use and expires in ~5 minutes

This way, even if someone sees the code in the URL, they can't do anything with it without our server's secret credentials.

### Step 6: Backend processes the callback (handle_callback)

**Who:** Backend ↔ Redis ↔ Database ↔ IdP (server-to-server)

This is the most complex step. It has multiple sub-steps, each with its own purpose:

#### 6a. Validate the state (CSRF check)

**What:** Atomically GET + DELETE the state from Redis.
**Why:** Confirms this callback matches a login we initiated. If the state is missing (expired >5 min, already used, or never existed), the request is rejected.

**Critical misconception to avoid:** The state tells you "we started a login for john@acme.com." It does NOT tell you "john@acme.com actually entered their password." If the user typed the wrong password or cancelled at the IdP, the IdP never redirects back — the state just sits in Redis until it expires. The `code` (from the IdP) is the proof that authentication actually happened. You need BOTH: state proves we asked, code proves they authenticated.

#### 6b. Read the org's SSO config

**What:** Loads client_id, encrypted client_secret, tenant_id from the org's Configuration table.
**Why:** We need these credentials to talk to the IdP's token endpoint in the next step.

#### 6c. Exchange the code for an ID token (server-to-server)

**What:** Backend sends the code + client_id + client_secret to the IdP's token endpoint.
**This call goes directly from our server to the IdP's server — it never touches the browser.**

For Microsoft, this uses the MSAL library. For Google/OIDC, it's a standard POST:

```
POST https://token-endpoint.idp.com/token
  grant_type=authorization_code
  code=0.AXEA...
  client_id=abc123
  client_secret=my-super-secret
  redirect_uri=https://api.yourdomain.com/auth/sso/callback
```

**The IdP validates:** Is client_id registered? Does client_secret match? Is the code valid, not expired, not already used? Was it issued for this redirect_uri?

**The IdP responds with an `id_token`** — a cryptographically signed JWT containing the user's claims (email, name, etc.).

**Why this step exists:** This is where the IdP tells us WHO authenticated. Everything before was setup. This is the payoff. The server-to-server call ensures the identity data never passes through the untrusted browser.

**Client secret decryption:** The client_secret is stored encrypted in the database using Fernet (AES-128-CBC). The encryption key is derived from the `ENVIRONMENT_SECRET` env var — the value is padded/truncated to 32 bytes and base64url-encoded to produce the Fernet key. The same key is used for both encryption (when admin saves settings) and decryption (when backend needs the secret for IdP communication).

#### 6d. Validate the ID token (Google/OIDC only)

**What:** Fetches the IdP's JWKS (public keys), finds the key matching the token's `kid` header, verifies the JWT's RS256 signature, checks audience = our client_id, checks issuer matches the discovery document, checks the token hasn't expired.
**Why:** Ensures the id_token was actually issued by the IdP and wasn't forged or tampered with.
**Note:** For Microsoft, MSAL handles this internally.

#### 6e. Extract email from the ID token

**What:** Reads email from the verified token claims. Checks fields in order: `preferred_username`, `mail`, `upn`, `email` (different providers use different fields).
**Why:** We need the actual email to match it against our user database.

#### 6f. Verify email matches

**What:** Compares the email from the IdP with the email stored in the state (from step 2).
**Why:** If john@acme.com started the SSO flow but then logged into Microsoft as jane@acme.com, this catches it. Prevents login with the wrong account at the IdP.

**Note:** We never send the user's email TO Microsoft during the code exchange. The user logs in with whatever Microsoft account they choose, then Microsoft tells US the email. This check is OUR security validation, not Microsoft's.

#### 6g. Look up user in the database

**What:** Queries the org's schema for this email. Checks user exists and `account_status == "active"`.
**Why:** Just because someone works at Acme and has a Microsoft account doesn't mean they have access to our platform. They might not have been invited, or their account might have been disabled by an admin.

#### 6h. Create the platform session

**What:** Generates JWT access_token + refresh_token for our platform, stores them in the authentication table.
**Why:** Microsoft's tokens are useless to us going forward. We need our own JWTs that contain the user's UUID, org schema, and role — these are what every API endpoint checks for authorization. After this step, Microsoft's tokens are discarded.

#### 6i. Generate the one-time sso_code

**What:** Creates a random code (`secrets.token_urlsafe(48)`, 384 bits), stores `{ access_token, refresh_token, user_uuid }` in Redis with 60-second TTL.
**Why:** We need to pass the tokens from the backend to the frontend through the browser. But putting the access_token directly in the URL is dangerous because:
- URLs appear in browser history (anyone with computer access could see it)
- URLs show up in server/CDN access logs
- URLs leak via the Referer header when the page loads external resources

A one-time, 60-second code limits the exposure. Even if it leaks, it's already consumed or expired.

### Step 7: Backend redirects to the frontend

**Who:** Backend → Browser
**What:** HTTP 302 redirect to `https://app.yourdomain.com/sso-complete?code={sso_code}`
**Why:** The callback endpoint is a backend API route — there's no UI. We redirect to the frontend's `/sso-complete` page so it can finish the process.

### Step 8: Frontend exchanges sso_code for tokens

**Who:** Frontend → Backend → Redis
**Endpoint:** `POST /auth/sso/exchange`
**Request:** `{ "code": "the_sso_code" }`

**What happens:**
1. Backend atomically reads and deletes the code from Redis (single-use).
2. Returns `{ user_uuid, access_token, refresh_token }`.
3. Frontend stores the tokens in the NextAuth session.

**Why this step exists:** To securely deliver the tokens to the frontend. The sso_code in the URL was just a safe intermediary — this step trades it for the actual tokens via a POST body (not a URL).

### Step 9: User is logged in

From this point, every API call includes `Authorization: Bearer {access_token}`. This is identical to password login. The rest of the app has no idea the user logged in via SSO.

---

## Security Deep Dive

### Why can't attackers use the state token?

Three protections:
1. **Unpredictable:** 256 bits from a CSPRNG (`/dev/urandom`). Brute force = ~10^77 guesses.
2. **Single-use:** Read + delete happens atomically in a Redis pipeline. First consumer wins.
3. **Short-lived:** Auto-expires after 5 minutes.

### What about Man-in-the-Middle attacks?

If an attacker intercepts the redirect URL (which contains the state and later the code):

| What attacker captures | What stops them |
|---|---|
| State only (from step 3 URL) | They can visit the IdP URL, but the IdP asks THEM to log in. They authenticate as themselves, and our email mismatch check (step 6f) rejects it. |
| State + code (from step 5 URL) | HTTPS prevents this in practice. All redirects use TLS. |
| State + code (hypothetical) | The code exchange (step 6c) requires the `client_secret`, which only lives on our server. The attacker can't exchange the code without it. |
| State + code + somehow exchanges | The email mismatch check catches it — the IdP email won't match the original login email. |

**Layered defense:** State prevents CSRF. HTTPS prevents interception. client_secret prevents unauthorized code exchange. Email match prevents identity substitution. Each layer handles a different threat.

### Why does the IdP return a code instead of the email directly?

Because the redirect goes through the browser, which is untrusted. A URL like `?email=john@acme.com&status=success` could be faked by anyone. The code can only be redeemed server-to-server with the client_secret, keeping the real identity data off the browser.

### Why doesn't matching the state in Redis prove the user authenticated?

The state is created BEFORE the user goes to the IdP. It means "we started a login for this email." If the user fails authentication (wrong password, cancels, closes the tab), the state still exists in Redis. Only the code proves Microsoft actually authenticated someone. Analogy: the state is an appointment slip (proves you have an appointment), the code is the doctor's signed report (proves the examination happened).

### Client secret encryption

Stored encrypted using Fernet (AES-128-CBC). The key is derived from the `ENVIRONMENT_SECRET` env var: `base64url(ENVIRONMENT_SECRET.encode().ljust(32)[:32])`. **If ENVIRONMENT_SECRET changes, all stored client secrets become unrecoverable.**

### What is this pattern called?

**OIDC Authorization Code Flow** (also called "OAuth 2.0 Authorization Code Grant" or informally "three-legged OAuth"). This is the industry standard used by virtually all enterprise SSO implementations.

---

## Where Each Piece of Data Lives

| Data | Created at | Stored in | Used at | Destroyed at |
|---|---|---|---|---|
| state (CSRF token) | Step 3 | Redis, 5 min TTL | Step 6a | Atomically deleted after read |
| IdP auth code | Step 4 (by IdP) | URL params only | Step 6c | Consumed by IdP token endpoint (single-use) |
| IdP id_token (JWT) | Step 6c (from IdP) | Backend memory only | Step 6d-6e | Discarded after email extraction |
| access_token | Step 6h | Redis sso:code + DB auth table | Step 8 onward (every API call) | Logout or expiry |
| refresh_token | Step 6h | Redis sso:code + DB auth table | When access_token expires | Logout |
| sso_code | Step 6i | Redis, 60s TTL | Step 8 | Atomically deleted after read |

---

## Auth Flow Diagrams

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
   │                               │            at IdP            │
   │                               │                              │
   │                               │  5. HTTP 302 back            │
   │                               │     ?code=AUTH_CODE          │
   │                               │     &state=...               │
   │                               │<─────────────────────────────│
   │                               │                              │
   │                               │  6. Validate state (Redis)   │
   │                               │     Exchange code → id_token │
   │                               │     (server-to-server call)  │
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
   │  {auth_method:"flexible",     │
   │   sso_provider:"microsoft",   │
   │   sso_provider_name:"Microsoft"}
   │<──────────────────────────────│
   │                               │
   │  Show password field           │
   │  + "Or sign in with Microsoft" │
```

---

## Callback Error Cases

Every sub-step in `handle_callback` can fail. Each failure redirects the user to the frontend with a specific error code.

| Step | Failure Condition | Error Code | What Went Wrong |
|---|---|---|---|
| 6a | State not in Redis or expired | `invalid_state` | Token expired (>5 min), already used, or CSRF attack |
| 6b | No auth_config for org | `sso_not_configured` | Admin hasn't set up SSO for this organization |
| 6c | IdP rejects the code | `token_exchange_failed` | Code expired, wrong client_secret, redirect_uri mismatch, or IdP error |
| 6e | No email in IdP response | `no_email` | IdP didn't include an email claim (missing scope config) |
| 6f | IdP email differs from login email | `email_mismatch` | User started login as john@ but authenticated as jane@ at the IdP |
| 6g | User not in DB | `user_not_found` | Email not registered in the platform (no auto-provisioning) |
| 6g | Account status not active | `account_inactive` | User has been disabled by an admin |

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

**What happens on save:** The backend merges your update with the existing config, encrypts the client_secret, validates all required fields are present, then **tests the credentials against the actual IdP** before saving. For Microsoft, it attempts a client_credentials token acquisition via MSAL. For Google/OIDC, it fetches the discovery document and tests the token endpoint. If verification fails, the save is rejected.

**Required fields by provider:**

| Field | Microsoft | Google | Custom OIDC |
|---|---|---|---|
| `sso_client_id` | required | required | required |
| `sso_client_secret` | required | required | required |
| `sso_tenant_id` | required | — | — |
| `sso_well_known_url` | — | — | required |
| `sso_provider_name` | "Microsoft" | "Google" | User-defined |

**Auth method options:**

| auth_method | Behavior |
|---|---|
| `password` | All users log in with email + password. All SSO fields are cleared on save. |
| `sso` | All users must use SSO. Password login returns HTTP 403. |
| `flexible` | Users can use either SSO or password (org's choice to offer both). |

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
2. Add: `openid`, `email`, `profile`, `User.Read`
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

## Microsoft Teams Integration (Silent Auth)

When AssistCX runs inside a Microsoft Teams iframe, users are already authenticated with Microsoft. Instead of forcing a second login via the org's configured SSO provider, we use the Teams context to silently authenticate.

This is enabled by default for all orgs — no admin configuration needed.

### How Teams Auth Differs from Browser SSO

| Aspect | Browser SSO | Teams Silent Auth |
|---|---|---|
| User interaction | Full redirect to IdP login page | Zero — completely invisible |
| Token source | Backend exchanges code for token | Teams SDK gives the token directly |
| State management | Redis state for CSRF protection | Not needed — no browser redirect |
| Code exchange | Two-step: IdP code, then sso_code | Single step: Teams JWT → app tokens |
| Provider support | Microsoft, Google, custom OIDC | Microsoft only |
| Audience validation | Standard client_id | `api://{host}/{client_id}` URI |

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

4. Click **Add a scope**:
   - **Scope name:** `access_as_user`
   - **Who can consent:** Admins and users
   - **Admin consent display name:** Access AssistCX as user
   - **Admin consent description:** Allow Teams to access AssistCX on behalf of the signed-in user
   - **State:** Enabled

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

## Frontend Implementation Guide

### 1. Login Form — Email-First Discovery

Replace the current login form with an email-first state machine:

```
State: "email" → "discovering" → "password" | "sso_redirect" | "both" | "error"
```

| State | UI |
|---|---|
| `email` | Email field + "Continue" button. No SSO buttons. |
| `discovering` | Loading spinner on Continue button |
| `password` | Email (with back option) + password field + Login button |
| `sso_redirect` | "Redirecting to {provider_name}..." then navigate away |
| `both` | Password field + "Or sign in with {provider_name}" link |
| `error` | Toast "Account not found" → back to `email` state |

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

## Security Summary

| Concern | How it's handled |
|---|---|
| Client secrets | Encrypted at rest (Fernet/AES-128-CBC via ENVIRONMENT_SECRET). Never sent to frontend. |
| Tokens in URL | Only `sso_code` appears in URL — single-use, 60s TTL. Actual tokens never in URL. |
| CSRF | `state` parameter stored in Redis, validated on callback, single-use, 5 min TTL. |
| MITM | All redirects over HTTPS. Code exchange requires client_secret (server-side only). |
| Email validation | Email from discovery stored in state, verified against IdP's id_token. |
| Open redirect | Frontend URL is a backend env var, not passed dynamically. |
| SSO enforcement | `POST /auth/login` returns 403 when org is SSO-only. |
| Unknown users | `/auth/discover` returns `"password"` for unknown emails (no org leak). |
| No auto-provisioning | Users must exist in platform before SSO login works. |
| Replay attacks | State and sso_code are both atomically read+deleted (single-use via Redis pipeline). |
