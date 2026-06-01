# brain2 — Open-Core Roadmap

**Date:** 2026-05-31
**Status:** Proposed — pending the Phase 0 legal gate
**Thesis:** Open-source the single-user core; sell the hosted multi-user/sync
infrastructure. The visa situation gates *when and how revenue is captured*, not
whether we open-source. Open-sourcing builds the audience while the legal vehicle
for the paid tier is sorted out.

> This integrates with — does not replace — the existing freemium plan
> (`docs/launch/ACTION-PLAN.md`, ws3 pricing, ws4 payments). Open-core becomes the
> top-of-funnel; the $8/mo Pro tier is unchanged downstream.

---

## Why this works for brain2 specifically

It's barely a pivot. brain2 v0 already ships **two-tier storage behind an
abstracted `Store` protocol** — free local SQLite + sqlite-vec vs. paid cloud
Supabase. That *is* open-core/managed-hosting; we just publish the local tier and
sell the hosted one. The `feat/multiuser-deploy-auth` work is precisely the moat
you charge for — sync, multi-device, multiuser — the part developers can't
trivially self-host.

It also fits the ICP. Our own research: developer buyers are skeptical of hype,
decide on hands-on evidence/SDKs, require free tiers and sandboxes, and validate
peer-led via GitHub/Reddit. OSS is a trust-and-distribution multiplier for exactly
this buyer — the repo becomes the funnel the Pro tier monetizes.

---

## The open / paid line (the load-bearing decision)

| Layer | Open source (free, self-host) | Paid (hosted infra) |
|---|---|---|
| **Client** | VS Code extension, iOS companion, CLI | — (same clients, cloud-connected) |
| **Engine** | MCP server, capture/resume/search skills, KG build | — |
| **Storage** | `Store` protocol + **local** SQLite + sqlite-vec tier | **Cloud** Supabase tier (managed) |
| **Sync / multi-device** | — | ✅ the moat |
| **Multiuser / teams / auth** | — | ✅ (`feat/multiuser-deploy-auth`) |
| **Managed embeddings / compute / backups** | bring-your-own keys | ✅ managed |
| **Billing** | — | $8/mo Pro via Lemon Squeezy (MoR) |

**Licensing recommendation:**
- **Core (clients + engine + local `Store`): Apache-2.0** — maximize trust and
  adoption for the dev ICP; permissive removes friction.
- **Hosted control plane (sync/auth/multiuser server): keep closed**, or apply a
  source-available license (e.g. BSL) if you want it public-but-not-hostable. Do
  *not* Apache-license the part a competitor could stand up as a rival service.
- Decide the boundary **before** the first public commit — relicensing later is
  painful and erodes trust.

---

## Steps

### Phase 0 — Legal gate (do first; blocks Phase 3–4, not Phase 1–2)

The only hard blocker. Get an immigration attorney to map your specific visa to two
*separate* questions:

- [ ] **Publishing OSS** (no income) — generally low-risk, but confirm.
- [ ] **Earning hosted-tier revenue** / being de-facto operator of the venture —
  this is where work-authorization restrictions bite, and it varies by visa type
  (F-1/OPT vs H-1B vs O-1 vs E-2…).
- [ ] Determine the compliant **revenue vehicle**: work authorization, the right
  entity, a co-founder/operator who runs the paid tier, and whether a Merchant-of-
  Record (Lemon Squeezy) changes the analysis. *(MoR reduces operational burden; it
  does not by itself make the income visa-safe.)*

**Output:** a one-page written read — *can I publish OSS now? what's the earliest
compliant path to charge, and through what structure?* This sets the Phase 3–4
timeline. **Phases 1–2 can proceed in parallel** if OSS-publishing clears.

### Phase 1 — Prepare the core for open source

- [ ] **Carve the boundary in code:** confirm the `Store` protocol cleanly isolates
  local vs cloud; ensure nothing in the OSS core imports the hosted control plane.
- [ ] **Repo hygiene:** scrub secrets/history, add `LICENSE` (Apache-2.0),
  `README` (the "git stash for your head" wedge), `CONTRIBUTING`, `SECURITY.md`,
  `CODE_OF_CONDUCT`, issue/PR templates.
- [ ] **Make self-host real:** a 5-minute local quickstart (install extension → MCP
  connects → capture/resume loop on the SQLite tier with zero cloud account).
- [ ] **Draw the upgrade seam in the product:** a clear, non-naggy "Sync across
  devices / your team → Pro" affordance where cloud value appears.

**Output:** a public-ready repo where a developer can self-host the full
single-user experience in minutes, with an obvious (not annoying) path to Pro.

### Phase 2 — Publish + distribute

- [ ] Flip the repo public; ship a tagged `v0.x` release + changelog.
- [ ] Launch surfaces for the dev ICP: Show HN, relevant subreddits, a short
  "why/how it works" post (education-first, per positioning/ws1).
- [ ] Instrument top-of-funnel: stars, installs, self-host activations, and a
  waitlist/free-beta capture for the hosted tier (PostHog per ws6).
- [ ] Seed docs + a couple of real-use writeups (the peer-led validation devs trust).

**Output:** brain2 is publicly usable and discoverable; a measurable funnel from
GitHub → self-host → Pro-interest exists, even before the charge is on.

### Phase 3 — Stand up the paid hosted tier *(gated on Phase 0)*

- [ ] Finish `feat/multiuser-deploy-auth`: managed cloud Supabase tier, auth,
  multi-device sync, team workspaces.
- [ ] Provision the hosted control plane (deploy, secrets, backups, observability).
- [ ] Free hosted **beta** behind the waitlist — prove the live cloud capture/resume
  loop end-to-end before billing.

**Output:** a working managed service that delivers the sync/multiuser value the
OSS core deliberately omits.

### Phase 4 — Turn on monetization *(gated on Phase 0's revenue vehicle)*

- [ ] Wire Lemon Squeezy (MoR) checkout → entitlement → Pro features (ws4).
- [ ] Pricing/packaging live: free OSS self-host vs $8/mo Pro (ws3).
- [ ] Go/no-go on the existing bar: activation ≥25% AND crash-free ≥99.5%.

**Output:** revenue-generating Pro tier, operated through the compliant structure
Phase 0 defined.

---

## What "done" looks like (final output)

1. **A public OSS repo** (Apache-2.0 core) any developer can self-host in ~5 min —
   the full local single-user capture/resume/search loop, no cloud account needed.
2. **A hosted Pro service** ($8/mo via Lemon Squeezy MoR) that adds the things you
   *can't* self-host: cross-device sync, multiuser/teams, managed
   embeddings/backups — i.e. **the infrastructure is the product you sell.**
3. **A measured funnel:** GitHub stars/installs → self-host activations → Pro
   conversions, instrumented in PostHog against the activation/crash-free bar.
4. **A clean open/paid boundary** enforced in code and licensing, so the OSS tier
   drives adoption without cannibalizing the moat.
5. **A documented, attorney-blessed revenue structure** — the legal vehicle through
   which the hosted tier earns, compliant with your visa.

**One-liner end state:** *brain2's single-user brain is free and open; remembering
across your devices and your team is the paid infrastructure — and the company is
structured so you can legally run it.*

---

## Open questions / risks

- **Phase 0 is the schedule.** If the visa read says "no revenue until X," Phases
  1–2 still ship value and audience; only the charge waits. Don't let it block the
  open-sourcing.
- **Cannibalization:** the OSS local tier must be genuinely great (or it won't
  drive adoption) yet must not include sync/multiuser (or there's nothing to sell).
  The `Store` protocol boundary is what keeps this honest — guard it.
- **License boundary is one-way.** Pick the core vs. control-plane split before the
  first public commit.
- **MoR ≠ legal cover.** Lemon Squeezy simplifies tax/ops, not work-authorization.
- **Support load.** Public OSS means public issues; budget triage time from Phase 2.
