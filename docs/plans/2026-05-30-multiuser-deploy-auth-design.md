# brain2 — Multi-user deploy + real auth (cloud tier)

**Date:** 2026-05-30
**Status:** Design approved (brainstorm); implementation starting.
**Scope:** Deploy the cloud tier behind a real domain and replace the single
shared service identity with **per-Apple-user** auth and isolation — the spine the
iOS companion needs to serve more than one person.

## Goal

Turn the cloud tier from "one hosted account behind a pre-shared key" into a real
multi-tenant service: any user signs in with Apple on the iPhone, gets their **own**
isolated data, and reads it from anywhere. This pulls the iOS-companion design's
"v1.5 / v2" Apple-OAuth work forward and makes it the foundation.

## Decision summary

| Decision | Choice | Rationale |
|---|---|---|
| Tenancy scope | **Real multi-user** (each Apple ID = own org + data) | The actual product, not just "my phone reaches my laptop" |
| Apple → Supabase bridge | **Thin backend exchange** (`POST /v1/auth/apple` → Supabase `sign_in_with_id_token`) | App stays SDK-free; Supabase owns Apple verification + user provisioning + refresh |
| Backend identity | **Per-request GoTrue JWT drives tenancy** (kill `_login()` on the request path) | Today every cloud call collapses to one shared service user |
| API key | **Retire `BRAIN2_API_KEY` as a user identity**; service-only | The phone sends a real per-user JWT; the static key identifies the deployment, not a user |
| Refresh | **Backend proxy `POST /v1/auth/refresh`** | Anon key never ships in the app binary |
| Hosting | **Fly.io** | Always-on; sets up cleanly for APNs push in v2 (vs Vercel's serverless re-platform risk) |
| RLS posture | **Make RLS authoritative on the phone-read path** | Policies are correct but bypassed today (service client + `kb_id`-only KG reads) |

## What grounding the design changed

Two findings (verified against the live shared Delapan Supabase schema and the
backend source) reshaped the work:

1. **Org provisioning already works.** A live, enabled trigger
   `on_auth_user_created AFTER INSERT ON auth.users` runs `public.handle_new_user()`,
   which inserts one `orgs` row + one `org_members` (role `owner`) for every new
   GoTrue signup — Apple OAuth included. So a first-time Apple user gets an org for
   free; `_org_for(sub)` finds it. The hardest part of multi-tenancy is already done.

2. **The real blocker is a shared identity, not missing auth — and there's a
   security hole.** The entire cloud path resolves to **one** account:
   `resolve_tenant` (cloud branch), `SupabaseStore.resolve_project`,
   `SupabaseStore.list_projects`, and `knowledge_graph/activity.resolve_activity_target`
   each call `_login()` with the hardcoded `DVG_MCP_USER_EMAIL/PASSWORD`. A signed-in
   phone would see the **server's** repos. Worse, brain2 reads through the
   `service_client` (which **bypasses RLS**) and the activity-KG read surface
   (`get_kg_subgraph`, `list_kg_nodes`, `kg_stats`, `match_kg_nodes`) filters by
   `kb_id` only, **never `org_id`** — so the correct, org-scoped RLS policies do
   nothing on the hot path. Multi-user is cosmetic until both are fixed.

### Verified facts (anchors)

- Trigger: `CREATE TRIGGER on_auth_user_created AFTER INSERT ON auth.users ...
  EXECUTE FUNCTION handle_new_user()` — enabled. `handle_new_user()` creates
  `orgs` + `org_members(role='owner')`.
- RLS **enabled** on `findings`, `kbs`, `projects`, `kg_nodes`, `kg_edges`,
  `orgs`, `org_members` (and more); every data policy =
  `org_id IN (SELECT org_id FROM org_members WHERE user_id = auth.uid())`.
  RLS is **not FORCED**, and brain2's cloud path uses the service-role key → RLS
  is bypassed; only hand-written `.eq("org_id", …)` filters protect rows.
- KG reads use `service_client` + `.eq('kb_id', …)` only — `org_id` guard absent
  (`store/supabase.py:398-481`). KG writes trust caller-supplied `org_id`
  (`nd.get('org_id')`, lines 315/369) → null/wrong org silently persisted.
- `_login()` (`interfaces/mcp/tenancy.py:33-44`) signs in the single configured
  user; called by `resolve_tenant` (cloud, :112), `resolve_project`
  (`store/supabase.py:222`), `list_projects` (:252).
- Bridge is buildable with current deps: `supabase-py` exposes
  `auth.sign_in_with_id_token({provider:'apple', token, nonce})`; `pyjwt[crypto]`
  already a dep; `Settings.supabase_jwt_secret` already declared (currently unused).
- **Native-Apple `aud` trap:** a native iOS app's `identityToken` carries
  `aud = the app bundle id`, **not** a Services ID. Supabase's Apple provider
  "Client IDs" must contain the bundle id (native-only → skip Services ID / .p8 /
  Key ID / Team ID). Wrong value = "unexpected aud claim value".

## Architecture

```
iOS (Sign in with Apple)
  rawNonce → sha256 → ASAuthorization → identityToken (JWT, aud = bundle id)
    → POST /v1/auth/apple { identity_token, nonce: rawNonce }
Backend (no Apple crypto of its own)
    → supabase.auth.sign_in_with_id_token(provider='apple', token, nonce)
       (Supabase verifies Apple token, find-or-creates GoTrue user, mints session)
    ← { access_token (GoTrue JWT), refresh_token, expires_in, user_id }
iOS  → store session in Keychain; send access_token as Bearer on every /v1/*
Backend /v1/*  → require_principal: HS256-verify JWT vs SUPABASE_JWT_SECRET
                 (aud='authenticated'), sub = user id → org via org_members
                 → user_client(jwt) / org-scoped Store → RLS-scoped reads
       refresh: iOS → POST /v1/auth/refresh → GoTrue /token?grant_type=refresh_token
```

The cloud tier forces `BRAIN2_BACKEND=cloud` (Supabase), which sidesteps the
local-tier loopback enforcement and the `~/.brain2/brain.db` path that would break
in a container.

## Backend changes

### 1. Apple bridge (new, un-gated endpoints)
- `POST /v1/auth/apple` — body `{ identity_token, nonce }`. Calls
  `create_client(SUPABASE_URL, SUPABASE_ANON_KEY).auth.sign_in_with_id_token(
  {'provider':'apple','token':identity_token,'nonce':raw_nonce})`. Returns
  `{ access_token, refresh_token, expires_in, expires_at, user_id }`. Maps
  GoTrue `AuthApiError` → HTTP 401. **Not** behind `require_principal` (it mints
  the session). ~40 lines; all Apple verification + provisioning delegated to
  Supabase.
- `POST /v1/auth/refresh` — proxies `POST {SUPABASE_URL}/auth/v1/token?grant_type=
  refresh_token` with the anon `apikey` header, so the anon key stays server-side.
  Returns the rotated session; client must persist the **new** refresh token.

### 2. `Principal` + `require_principal` (per-user dependency)
In `api/auth.py`:
- `Principal(user_id, org_id, access_token, is_service=False)`.
- Cloud: read `Authorization: Bearer`; `jwt.decode(token, supabase_jwt_secret,
  algorithms=['HS256'], audience='authenticated', options={'require':['exp','sub']})`;
  `user_id = sub`; `org_id = _org_for_or_create(sub)`. `ExpiredSignatureError` /
  `InvalidTokenError` → 401.
- Local: return `Principal('local','local','')` — same `active_backend()=='local'`
  fork `require_api_key` already uses (single user, no decode).
- Keep a **JWKS fallback** (`PyJWKClient` against
  `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, ES256/RS256) ready, in case the
  project migrates off the legacy HS256 shared secret.

### 3. Thread the principal; kill `_login()` on the request path
- `resolve_tenant(principal, project, kb, *, create=…)` — cloud branch uses
  `principal.{user_id, org_id, access_token}` instead of `_login()`. `TenantContext`
  shape unchanged.
- `get_store(access_token, *, org_id=None)` and `SupabaseStore(access_token,
  org_id=None)` — when `org_id` is set, `resolve_project` / `list_projects` use it
  directly and **drop** the internal `_login()`/`_org_for()`; fall back to `_login()`
  only when `org_id is None` (preserves MCP behavior).
- Endpoints (`capture`, `resume`, `explore`, `projects`, `activity`) take
  `principal: Principal = Depends(require_principal)`; routers swap
  `Depends(require_api_key)` → `Depends(require_principal)`; `knowledge_graph/activity.py`
  read/write paths take `principal` and build `get_store(principal.access_token,
  org_id=principal.org_id)`.
- `_org_for_or_create(user_id)` — try `_org_for`; on the "no org" RuntimeError,
  insert `orgs` + `org_members` via `service_client()` and return the new org_id.
  Belt-and-suspenders for a first-seen user whose signup trigger somehow didn't run.
- **MCP server stays on its own path**: build a `Principal(*_login(), _org_for(...))`
  and call the same `resolve_tenant` — keeps the engine on one code path while the
  MCP surface keeps its single configured-user identity.

No DB migration required (`orgs` / `org_members` already exist).

## Security hardening (coupled to §Backend — not optional)

Ship these in the **same** change as the auth rewire; without them, "multi-user"
isolates nothing on the activity-KG path:

1. Thread `org_id` into **every** KG read — `get_kg_subgraph`, `list_kg_nodes`,
   `kg_stats`, and the `match_kg_nodes` RPC (add an `org_id` arg) — `.eq('org_id', …)`.
2. Before any KG read/write, resolve `kb_id → org_id` from `kbs` and **assert it
   equals the JWT's org**; reject mismatches.
3. On KG **writes**, derive `org_id` from the verified kb — stop trusting
   `nd.get('org_id')` / `e.get('org_id')`. (Optional DB: `NOT NULL` + FK + CHECK
   that node/edge `org_id` matches its kb's org.)
4. Defense in depth: move the user-facing read path onto `user_client(jwt)` so RLS
   is authoritative, **or** `ALTER TABLE … FORCE ROW LEVEL SECURITY` — so a single
   forgotten `.eq` cannot fail open across orgs.
5. **Regression test (merge gate):** sign in as user B; assert user A's
   `kg_nodes`/`kg_edges`/`findings`/`projects` never appear in `/v1/activity/{graph,
   stats}`, `/v1/projects`, `/v1/resume`.

> Note: `match_findings` and the synopsis read paths share the same
> service-client + `kb_id`-only pattern. They're lower-risk (always reached via a
> tenancy-resolved `kb_id`), so this design scopes the must-fix to the KG +
> tenancy read path the phone hits directly; the broader move-to-`user_client`
> cleanup is tracked as follow-up.

## iOS changes

The app already extracts `identityToken` (`Auth/AppleSignIn.swift`) but
`Views/SignInView.swift` drops it. Wire it through:
- Generate a random `rawNonce`; set `request.nonce = sha256(rawNonce)`.
- On success, `POST { identity_token, nonce: rawNonce }` to `/v1/auth/apple`.
- Persist `access_token` + rotated `refresh_token` + `expires_at` in Keychain
  (service `dev.brain2.app`).
- On 401 / expiry, call `/v1/auth/refresh`; overwrite the stored refresh token.
- `Config.swift` base URL → the hosted domain (`https://…`). Retire the manual
  `ConnectionSheet` base-URL/token paste.

## Supabase config (dashboard, one-time)
- Authentication → Providers → **Apple**: enable; put the **app bundle id** in
  "Client IDs". Native-only → skip Services ID / .p8 / Key ID / Team ID. Ensure the
  App ID has the "Sign in with Apple" capability in the Apple Developer portal.
- Backend env: set `SUPABASE_JWT_SECRET` (the project's JWT secret — **not** the
  service-role key). HS256 + `aud='authenticated'`.

## Deploy — Fly.io
- `Dockerfile` (python 3.11; `CMD ["uvicorn","brain2.api.main:app","--host",
  "0.0.0.0","--port","8002"]`, honoring `$PORT`).
- `fly.toml` (app name, region, `[http_service]` → internal port, `/health` check).
- Force `BRAIN2_BACKEND=cloud`; never the local tier on a hosted host.
- `fly secrets`: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
  `SUPABASE_JWT_SECRET`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `TAVILY_API_KEY`.
- `.dockerignore` (`.venv`, `.git`, tests, `__pycache__`, `ios-app`, `vscode-extension`).
- CORS only matters for the webview/marketing site — the native iOS app sends no
  `Origin`. Add the site origin via `CORS_ORIGINS` if/when needed.

## Build sequence
1. **Backend auth rewire + security hardening together** (same surface, same PR):
   `Principal`/`require_principal`, thread through `resolve_tenant` + Store +
   activity, kill `_login()` on the request path, org-scope all KG reads/writes.
2. `POST /v1/auth/apple` + `POST /v1/auth/refresh`.
3. `Dockerfile` + `fly.toml`; deploy the cloud tier; smoke-test `/health` + a
   JWT-gated read.
4. Supabase Apple provider config + `SUPABASE_JWT_SECRET`.
5. iOS wiring against the hosted domain; TestFlight + a real Sign-in-with-Apple run.
6. Cross-user isolation test as the merge gate.

## Out of scope (explicitly v2+)
- Push (APNs) and any capture/write from the phone (v1 remains read-only on device).
- Laptop ↔ phone account linking (each surface authenticates independently for now;
  the Apple account is canonical).
- The broader `service_client → user_client` migration for `match_findings` /
  synopsis reads (tracked as follow-up; not on the phone's direct read path).
- Asymmetric Supabase JWT signing keys (JWKS path stubbed but HS256 is current).

## Risks
- **aud mismatch** is the #1 Apple trap — bundle id, not Services ID, in "Client IDs".
- **Fail-open cross-org** if `org_id` ever comes from anything but the JWT-derived
  membership — the service client bypasses RLS, so a typo'd filter leaks. `org_id`
  MUST come from `_org_for(jwt.sub)`.
- **Refresh-token rotation** — GoTrue rotates on every refresh; reusing an old token
  trips reuse-detection and can revoke the family. iOS must overwrite on every refresh.
- **Apple email relay / withholding** — identity must key off the Supabase user UUID
  (`sub`), never email.
- **Adding the endpoint alone does nothing** — without the `resolve_tenant` rewire,
  findings still write under the shared user/org. Auth and tenancy land together.
