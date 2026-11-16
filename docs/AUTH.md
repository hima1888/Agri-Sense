# Authentication & authorization

## Flow

```
Browser ──(email + password)──▶ Supabase Auth ──▶ access token (JWT, ES256, ~1 h, auto-refreshed)
Browser ──(Authorization: Bearer <token>)──▶ FastAPI
FastAPI ── verifies signature with Supabase's public keys (JWKS, cached) ──▶ user id
FastAPI ── loads/creates the `users` profile, checks farm ownership ──▶ data
```

- The browser uses Supabase **only** to sign up, sign in and refresh tokens. Farm data never goes
  directly from the browser to the database; it always passes through the API.
- The API never sees passwords.

## Token verification (backend `app/core/security.py`)

| Check | Rule |
|---|---|
| Algorithm | ES256/RS256 against `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`; HS256 **only** if `SUPABASE_JWT_SECRET` is set. `none` and algorithm confusion are rejected. |
| Key | Looked up by `kid`; JWKS cached 10 min; unknown `kid` triggers at most one refetch per 30 s (key rotation). |
| Claims | `exp` (30 s leeway), `aud = authenticated`, `iss = <SUPABASE_URL>/auth/v1`, `sub` is a UUID |
| Who | `role = authenticated` only. Anon/service-role keys and anonymous sign-ins are rejected. |

## Authorization

- **Profile:** the first request from a new Supabase account creates its `users` row (`id` = Supabase user id).
  An email change made in Supabase is synced on the next request.
- **Roles** (`farmer`, `agronomist`, `admin`) live only in our `users` table. They are **never** read from
  token metadata, which users can edit themselves. Change roles with:
  `python -m app.cli.users set-role someone@example.com admin`
- **Farm scope:** users see and change only farms they own. Admins see all farms. Records belonging to
  someone else return **404**, so their existence is never confirmed.
- **Crop catalogue:** readable by every signed-in user; only admins may change it.
- **Audit:** every change records the acting user (`audit_logs.user_id`).
- **Public endpoints:** `GET /health` and `GET /system/info` only.

## Frontend

- `AuthProvider` holds the session; `RequireAuth` guards private routes and returns to them after sign-in.
  After sign-in, only paths on this site are allowed as the return address (no open redirects).
- Every API call attaches the current access token (`setAccessTokenProvider`).
- The password policy (8+ characters, upper- and lowercase letters, a number) is checked in the form and
  enforced by Supabase.
- Cached user data is cleared on sign-in and sign-out, so the next person on a shared device never sees it.

## Local development

```bash
npm install            # repo root: installs the Supabase CLI
npm run auth:start     # local Supabase Auth on http://127.0.0.1:54321 (Docker)
npx supabase status    # prints the local publishable key for frontend/.env.local
```

- Local tokens are signed with an ES256 key in `supabase/signing_keys.json`. That file is git-ignored and
  local only; generate it with `npx supabase gen signing-key --algorithm ES256`.
- Email confirmation is **off locally** (`supabase/config.toml`). Confirmation emails would appear in
  Mailpit at http://127.0.0.1:54324.

## Hosted Supabase (deployment, Phase 20)

| Where | Setting |
|---|---|
| Backend | `SUPABASE_URL=https://<ref>.supabase.co` (JWKS + issuer checks) |
| Frontend | `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` |
| Supabase dashboard | Turn email confirmation on; set the Site URL and redirect URLs to the Vercel domain |
