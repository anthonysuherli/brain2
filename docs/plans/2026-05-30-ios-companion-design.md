# br8n iOS companion — v1 design

**Date:** 2026-05-30
**Status:** approved (brainstorm), implementation starting
**Scope:** first standalone consumer-facing UI for br8n — a native iOS app

## Decision summary

| Decision | Choice | Rationale |
|---|---|---|
| Core job | Full companion (read + capture + push), **but v1 = read spine** | Ship the "glance before standup" loop first; capture + push are v2 |
| Backend | **Hosted cloud tier** (Supabase + FastAPI behind a domain) | Phone reaches data from anywhere; required for push later |
| App stack | **Native SwiftUI** | Flagship Apple feel — Sign in with Apple, APNs, widgets first-class |
| Identity | **Apple = canonical account; laptop links to it** | One person = one account across laptop + phone |
| v1 slice | **Read spine** | Sign in with Apple → browse activity KG → read resume cards |

The deliberate v1 constraint: **zero new captured-data semantics.** v1 is a
deployment of the already-built cloud tier plus a beautiful native viewer. No
capture, no push, no writes from the phone.

## Architecture

```
SwiftUI app  ──HTTPS + Bearer JWT──>  hosted br8n cloud API (FastAPI)  ──>  Supabase
(iPhone)                               (existing cloud tier, now deployed)      (pgvector + GoTrue + RLS)
```

- **Identity:** Sign in with Apple → Supabase Apple OAuth provider → GoTrue JWT →
  sent as Bearer token → RLS scopes every read to the signed-in user.
- **The app is a pure read client in v1.** It calls existing cloud endpoints
  (`/v1/activity/graph`, `/v1/activity/stats`, `/v1/resume/{project}/{kb}`) plus
  one new discovery endpoint and one new JSON resume format.
- **No new engine logic.** Everything shown already exists server-side.

## Backend changes

### 1. Host the FastAPI cloud tier
Deploy to **Fly.io or Render** (always-on, cheap, sets up for APNs in v2). Real
domain, e.g. `api.br8n.dev`. Avoid Vercel here — serverless/short-lived means a
re-platform when push lands.

### 2. Supabase Apple OAuth provider
Enable Apple as a sign-in provider in Supabase Auth (needs Apple Developer
account, App ID + "Sign in with Apple" capability, Services ID, key). Supabase
handles token exchange; app gets a standard GoTrue session JWT. **(v1.5 / v2 —
the read endpoints work today under the existing configured user; per-Apple-user
auth replaces that.)**

### 3. Confirm RLS covers the activity-KG tables
`kg_nodes` / `kg_edges` + `match_kg_nodes` RPC must have RLS policies scoping to
the signed-in user. Verify-and-patch task. **Security-critical.**

### 4. Two new thin reads (the API gaps a phone exposes)

**Gap 1 — Discovery.** No "list my stuff" endpoint exists; `/v1/resume` requires
already knowing project + kb. The phone's home screen needs:

```
GET /v1/projects
  → [{ project, kbs: [{ kb, last_activity, snapshot_count, coverage }], ... }]
```

Thin query over projects/kbs + latest finding timestamps. Added to the `Store`
protocol so both tiers share it.

**Gap 2 — JSON resume.** `/v1/resume` returns rendered HTML (built for the VS
Code webview). A native app rendering foreign HTML in a `WKWebView` is the
compromise you'd feel immediately. Add:

```
GET /v1/resume/{project}/{kb}?format=json
  → { coverage, hypothesis, synopsis[], snapshots[], activity[], snapshot_count, preamble }
```

Refactor: split the data assembly (already done before templating) from the HTML
rendering. The SwiftUI app lays it out natively. Highest-leverage change for
"feels native."

## SwiftUI app

Four screens, one navigation stack:

1. **Sign in** — single "Sign in with Apple" button (`ASAuthorizationController`).
   On success, store JWT + refresh token in **Keychain**. Only shows with no
   valid session.
2. **Home** — cross-repo overview from `/v1/projects` + `/v1/activity/stats`: repos
   touched (most-recent first) with branch count, last-activity, coverage dot;
   plus a compact hotspots strip. The "glance before standup" screen.
3. **Repo detail** — branches (KBs) for a repo, each with last-activity + snapshot
   count.
4. **Resume card** — the payoff. Native layout of the JSON resume: **hypothesis**
   prominent at top, snapshot timeline, coverage band, collapsible preamble.

Supporting layers (thin, conventional):
- `APIClient` — async/await `URLSession`, injects Bearer JWT, auto-refresh on 401.
- `AuthStore` — `@Observable`, owns session + Keychain, drives Sign-in vs Home.
- `Models` — `Codable` structs mirroring the JSON contracts.

**Deferred to v2:** interactive activity-KG graph visualization (v1 shows
stats/hotspots, not a node graph); quick-capture; push notifications; the
laptop-link auth mechanism.

## Data flow

```
App launch
  → AuthStore reads Keychain
     → valid session?  yes → Home    no → Sign in
  → Home onAppear: parallel fetch /v1/projects + /v1/activity/stats
  → tap repo → KBs already in /v1/projects payload (no fetch)
  → tap branch → GET /v1/resume/{project}/{kb}?format=json
```

## Error handling — three states every screen handles

- **Loading** — skeleton placeholders, never a bare spinner on payoff screens.
- **Empty** — distinct from error. "No activity yet — capture from your editor to
  see it here." (Likely day-one before laptop-link exists; must feel intentional.)
- **Error** — 401 → silent refresh + retry once; persistent 401 → Sign in.
  Network/5xx → inline retry, never a dead end.

## Testing

- **Backend:** unit tests for `/v1/projects` shape and JSON-resume parity with the
  HTML version's data; RLS test proving user A can't read user B's `kg_nodes`
  (security-critical).
- **App:** `APIClient` against recorded JSON fixtures; `AuthStore` state-machine
  tests (no-session → signed-in → expired → refreshed). Mock the network.
- **One manual E2E checklist:** real device, real Sign in with Apple, real hosted
  API, seeded data → Home → drill to a resume card.

## Build sequence

1. **Backend endpoints** (this can land now, tier-shared, TDD'd):
   `/v1/projects` discovery + `/v1/resume?format=json`.
2. **Deploy + auth:** host FastAPI, Supabase Apple OAuth, RLS verification.
3. **SwiftUI app:** data layer → screens → polish.
