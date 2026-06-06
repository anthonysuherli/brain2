# br8n — OSS Chat-Agent POC, grounded on the maintained Supabase KB — design

**Date:** 2026-06-03
**Status:** Design (validated against current code; not yet implemented)
**Working name:** Funnel Agent

## Summary

Turn br8n into an **open-source chat agent** that grounds every message on the
**Supabase knowledge base you maintain** — read live through the existing preamble
path, no repo-carried copy, no export step. The agent is the **introductory POC and
funnel for delapan**: the code is MIT-free; the *managed infrastructure* (the hosted
KB it reads, plus sync/teams) is the paid side. A visitor talks to the agent on the
landing site; it answers from your curated KB and, when the conversation warrants,
routes them to delapan.

> **Decision (this revision):** grounding source is the **live Supabase KB**, kept
> current by you via the existing br8n/delapan tooling. The agent reads it with
> `get_store()` + `select_preamble` exactly as the resume card does today. There is
> **no repo-carried KB / FileStore / export** — that idea is dropped.

Two build pieces, plus release prep — both reuse the shipped engine:

- **B. Enrichment** — keep the br8n self-KB + the (already-scaffolded)
  `chat-agent/*` KBs current in Supabase via repo-ingest + bounded web explore. This
  is the thing you "maintain and update."
- **C. Chat surface** — a minimal `/v1/chat` (no LangGraph) that, per message, runs
  `select_preamble` against the maintained KB and streams a grounded, persona'd
  completion.

The only genuinely new code is the thin chat loop. Everything grounding-related
already ships.

## 1. Positioning — br8n as the POC funnel for delapan

| Layer | br8n (this repo) | delapan |
|---|---|---|
| License | **MIT, free** (`LICENSING.md` drafted) | BUSL / source-available |
| What's free | the engine + the **chat-agent code** | — |
| What's paid / maintained | — | **managed infrastructure**: the hosted KB the agent reads, cross-machine sync, cross-repo search, teams |
| Role | the **live demo** on the landing site → proves the grounding loop | the product the demo sells |

The funnel is the **hosted agent** (your deployment, pointed at your maintained
Supabase KB) — not a self-contained local clone. Forkers *can* run their own against
the free local SQLite tier (`get_store()` already selects it), but the canonical,
always-current agent is yours, because you own the KB it speaks from. "We maintain
and update it" is precisely the paid/managed line.

## 2. What exists today (grounded against the code)

- **Preamble** (`agent/preamble.py`): `select_preamble(query, *, store, kb_id, depth)`
  loads `store.load_synopsis(kb_id)` + semantic `store.match_findings(kb_id, qvec, …)`,
  bands by similarity, renders `<preamble>`. The chat loop calls this **unchanged**.
- **Store selection** (`store/__init__.py`): `get_store()` / `active_backend()` pick
  Supabase when creds are present (`BR8N_BACKEND=cloud`), else local SQLite. The
  deployed agent sets cloud + creds → grounds on the maintained KB. No new store code.
- **No chat agent**: `agent/graph.py` (LangGraph) + `api/agent.py` were **excluded**
  from the fork (CLAUDE.md). Piece C re-introduces a *minimal* surface, not LangGraph.
- **KBs already in Supabase** (`br8n_projects`): a **`chat-agent`** project with 5
  purpose-built KBs — `persona-voice`, `hitl-qualification`, `agent-build-stack`,
  `landing-front-door`, `conversational-gating` — **lightly seeded** (e.g.
  `landing-front-door` carries a Kontor "conversational form replaces static form"
  finding). `br8n/dev` has a 6-topic synopsis spine. A research layer exists
  (`context-resume/market-research`, `knowledge-engine/*-competitive-position`, …).

So enrichment is *topping up* a structure already in your Supabase, and the chat loop
is the only net-new surface.

## 3. The shape

```
   MAINTAINED KB (Supabase)            RUNTIME (your deployment)
 ┌──────────────────────────┐        ┌────────────────────────────┐
 │ chat-agent/* , br8n/dev │ ─────► │  POST /v1/chat             │
 │  (you curate via the      │  read  │   embed(msg)               │
 │   br8n/delapan tools)   │  live  │   select_preamble(store=   │
 └──────────────────────────┘        │     SupabaseStore, kb_id)  │
        ▲                             │   → persona + <preamble>   │
        │ B. enrich (ongoing)         │   → stream answer          │
        └──── you maintain/update ────│   → route to delapan       │
                                      └────────────────────────────┘
                                              C. chat surface
```

## 4. Grounding source — the maintained Supabase KB

No new mechanism. The chat loop grounds through the **existing** path:

- `store = get_store()` → `SupabaseStore` on the deployment (cloud creds set).
- `select_preamble(user_message, store=store, kb_id=AGENT_KB_ID)` → live synopsis +
  semantic findings from the KB you maintain, banded and budgeted as today.
- **Which KB:** one designated **agent KB id** (env `BR8N_AGENT_KB`). v1 grounds on
  a single consolidated KB you keep current. *Optional later:* union the 5
  concern-KBs by looping `match_findings` over their kb_ids and merging bands — a
  small change, deferred until single-KB grounding feels thin.

"Maintain and update" = you enrich that KB (Piece B) with the normal tools; the agent
picks up the change on the **next message** automatically — nothing to redeploy, no
export. That live-update property is the reason to keep it in Supabase.

## 5. Piece B — Enrichment (the thing you maintain)

Keep the source KBs current in Supabase. Two intake modes already in the engine:
**repo-ingest** (local truth) and **bounded web explore** (`br8n_explore`).

| Source KB | Purpose for the agent | Seed via | Target |
|---|---|---|---|
| `br8n/dev` (self-KB) | what br8n *is* — architecture, tiers, the loop, OSS stance | **ingest** repo: CLAUDE.md, `docs/plans/*`, `LICENSING.md`, README | rich |
| `chat-agent/persona-voice` | the agent's voice + refusal/escalation tone | ingest a short persona brief + web on dev-tool bot voice | sparse→rich |
| `chat-agent/conversational-gating` | "talk your way past the gatekeeper" qualification flow | already seeded; explore conversational-qualification patterns | rich |
| `chat-agent/hitl-qualification` | when to escalate a hot lead to a human / delapan | web explore lead-qual + PLG-to-sales handoff | sparse→rich |
| `chat-agent/agent-build-stack` | how the agent is built (streaming, deploy) | ingest C's own design + web on the chosen stack | rich |
| `chat-agent/landing-front-door` | the funnel: what the landing promises, FAQ | ingest `site/*` + the OSS/positioning docs | rich |
| **new** `chat-agent/delapan-handoff` | when/how to route to delapan + objection handling | ingest delapan positioning + web on PLG upsell | sparse |

`/build` (delapan) or bounded `/br8n:explore` runs do the filling; each is bounded
(`max_findings ≤ 6`) per the non-blocking precedent. No export afterward — the agent
reads the result live. If you ground on a single agent KB (§4), periodically fold the
concern-KBs into it (or enable the union option).

## 6. Piece C — Chat surface (minimal, no LangGraph)

### Endpoint — `api/chat.py` (re-introduced, thin)

`POST /v1/chat` (SSE stream). Per message:

1. `qvec = embed_text(user_message)`.
2. `preamble, coverage = await select_preamble(user_message, store=get_store(), kb_id=AGENT_KB)`.
3. System prompt = **persona** (curated in `persona-voice`) + `<preamble>` + **funnel
   instructions** ("answer from the context; when the visitor's need maps to managed
   infra — hosting, sync, teams — surface delapan and offer the handoff").
4. Stream a completion via `clients.ai_gateway` (the engine's client).
5. Return the stream; thread short history client-side (stateless server).

No graph, no tools in v1 — a single grounded completion loop, ~120 lines.

### Deploy

The server is stateless but **needs Supabase creds** (it reads the maintained KB) —
so it's a small always-on service, not a static asset. Reuse the Fly.io target from
`2026-05-30-multiuser-deploy-auth-*`; set `BR8N_BACKEND=cloud` + `BR8N_AGENT_KB`.
The landing `site/` embeds a chat widget POSTing to `/v1/chat` — the agent becomes
the hero interaction (ties to the rebuilt hero).

### Gating

The agent is free and ungated to talk to. "Use the infrastructure" (hosted/sync/
teams) is the delapan upsell the agent routes to — code free, infra paid/maintained.

## 7. OSS release prep (from the original ask)

Tracked in `LICENSING.md`; the must-dos before flipping public:

1. **License** — create `LICENSE` from the MIT template, copyright `2026 Anthony
   Suherli`. (Apache-2.0 only if patent exposure becomes a concern.)
2. **Scrub secrets from git *history*** — `.env`, Supabase keys, the shared dev
   identity. br8n shares Supabase `gunqbyddzuwzpncfigro` with delapan;
   `git filter-repo` (HEAD-delete is insufficient). **Especially important now:** the
   deployed agent uses real Supabase creds — they must live only in deploy secrets,
   never in the public repo or history.
3. **Untangle the shared Supabase schema** — one repo owns `supabase/migrations/`,
   the other references it (can't be MIT here + BUSL there).
4. **README** — license section + a quickstart. Note honestly that the hosted agent
   reads a managed KB; forkers can run their own against the free local tier.
5. **Third-party inventory** — `pip-licenses` / `license-checker` pass.

## 8. Config gates (env)

- `BR8N_AGENT_KB` — the kb_id (or `project/kb`) the agent grounds on.
- `BR8N_BACKEND=cloud` + Supabase creds — selects the maintained KB on the deploy.
- `BR8N_CHAT` — chat endpoint on/off.
- `BR8N_CHAT_MODEL` — completion model slug (AI Gateway).

## 9. Build sequence (each step independently shippable)

1. **C1** `/v1/chat` thin loop grounding on `get_store()` + `select_preamble` against a
   designated KB. *Done when:* a local request returns a grounded, streamed answer
   sourced from the KB's findings (run against the local tier with a seeded KB).
2. **B** Enrich the source KBs in Supabase (ingest + bounded explore) — the ongoing
   "maintain and update" loop. The agent picks up changes live, no redeploy.
3. **C2** Site chat widget + Fly deploy (cloud backend, `BR8N_AGENT_KB` set).
4. **Release** §7 (license, history scrub, schema untangle, README) — gate public on
   this; double-check no Supabase creds in history given the deploy now uses them.

## 10. Open questions / YAGNI

- **Single agent KB vs union of the 5 concern-KBs** — v1 grounds on one designated KB;
  the loop-and-merge union is a small, deferred extension.
- **Conversation memory** — stateless v1 (history client-side). Server-side threads
  are a managed-infra concern, not a POC one.
- **Tools in chat** — none in v1 (single grounded completion). Add only if the agent
  needs to *act* (e.g. start a delapan trial), which is itself the upsell boundary.
- **KB availability** — because grounding is live, a Supabase outage degrades the
  agent. Mitigation if it matters later: a short in-process cache of the last good
  preamble per query-cluster. Deferred (don't reintroduce a local copy prematurely).
- **Embedding-model consistency** — query embedding must match the model the KB's
  finding vectors were built with; the engine already standardizes this
  (`text-embedding-3-small`), so it's a non-issue while one model is used.
```
