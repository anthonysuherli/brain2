# WS7 — Launch Sequence & Runbook (capstone)

**Workstream:** Launch — Integration / Runbook
**Product:** brain2 — context-capture-and-resume engine for developers. Captures workspace
state on interruption (branch, open/cursor files, `git diff --stat`, a one-line hypothesis)
and replays a 30-second resume card. Freemium: free local tier (SQLite, loopback, no auth,
data stays on machine) + paid cloud tier (Supabase; **SYNC + cross-repo SEARCH ship-ready
for v1**, team-sharing + managed-keys "coming soon"). Distributed as a Claude Code plugin +
VS Code extension. Solo founder.
**Owner:** founder · **Date:** 2026-05-29 · **Status:** executable runbook
**Anchor:** **W0 = week of 2026-05-29** (Mon 2026-05-25 .. Fri 2026-05-29). Each phase is
one calendar week; dates below are concrete.

This is the integration workstream. It does **not** re-derive strategy — it sequences and
cross-references the seven sibling deliverables into one dated, executable plan:

| Ref | File | Owns |
|---|---|---|
| WS-1 | `ws1-positioning-icp.md` | wedge, ICP, messaging, competitor teardown |
| WS-2 | `ws2-distribution-channels.md` | ranked channels, Show HN + PH assets, content calendar |
| WS-3 | `ws3-pricing-packaging.md` | freemium model, $8 Pro / $12 Team, pricing page, upgrade triggers |
| WS-4 | `ws4-payments-billing.md` | MoR (Lemon Squeezy), trial, webhooks, dunning, test plan |
| WS-5 | `ws5-legal-privacy-trust.md` | LLC, ToS/Privacy/DPA, `/security` page, egress disclosure |
| WS-6 | `ws6-metrics-instrumentation.md` | WCRR North Star, PostHog taxonomy, go/no-go thresholds |
| WS-8 | `ws8-onboarding-growth.md` | activation path, friction fixes, shareable-card growth loop |

**Grounding (brain2 `dev` KB).** Beta cohort is **20–50 testers**, validation cuts launch-day
bugs ~60%, and 60% of unvalidated products fail [#854de64b]. Validate messaging against
lookalikes and **act on patterns (≈5/10 positive), not single replies** [#1665bb5c]. The
current-state snapshot [#141be947] sets W0's first task: "reload plugins so the MCP server
connects and exercise the live resume/capture loop on the cloud tier." Launch-day signup band
**100–500**, month-1 median **847 users**, CAC **$127**, month-3 retention **34%**,
break-even **8.2 months** [#43300575], [#2ce52b97].

---

## 1. Phase table — W0..W5+ (dated milestones, cross-referenced)

| Phase | Dates | Theme | Milestones (→ workstream pulled from) |
|---|---|---|---|
| **W0** | **Mon 2026-05-25 → Fri 2026-05-29** | **Prove the live loop + turn on the meters** | • Reload plugin so MCP server connects; run the **live capture→resume loop on the cloud tier** end-to-end [#141be947]. • Verify free local loop too (`python -m brain2.api.main --check` → ✓db ✓sqlite-vec ✓loopback) (**WS-8** friction list). • Land **WS-8** highest-priority friction fixes: plugin-reload-is-last-step instruction, MCP connect diagnostic + status-bar connected/disconnected state, guaranteed first capture on first activation, tier echo on boot. • Stand up **PostHog**: ship the §3 event taxonomy (`onboarding:flow_completed`, `capture:snapshot_captured`, `resume:resume_card_viewed` w/ `coverage_band`, `monetization:*`), super-properties, salted-hash identity, allowlist schema CI (**WS-6**). • Confirm instrumentation fires on the live loop before any user sees it. |
| **W1** | Mon 2026-06-01 → Fri 2026-06-05 | **Private beta opens (design partners)** | • Recruit **20–50 design partners** [#854de64b] from Persona A (solo AI-assisted indie) + Persona B (agentic-coding power user) channels — Claude Code / Cursor Discords, X dev circles, IndieHackers (**WS-1** §2, **WS-2** ch.10/7). • Ship them the one-command install + the "switch windows and come back" first-session script (**WS-8** §1, §5). • Run the **pre-launch message test**: show "git stash for your head" + the hero cold to lookalikes (**WS-1** §5); track the three risky assumptions. • Watch **activation rate** + **week-1 NSM retention** in PostHog from day one (**WS-6** §4). |
| **W2** | Mon 2026-06-08 → Fri 2026-06-12 | **Beta feedback → patterns → fixes** | • Read beta as **patterns, not single replies** — act on ≥5/10 signal [#1665bb5c]. Targets: ≥5/10 paraphrase the wedge unprompted; ≥5/10 ask for the install link unprompted; ≥5/10 cite local/private as a try-reason (**WS-1** §5). • Fix whatever blocks the **first populated resume card in session 1** (the aha) — empty-state copy, `gap`-coverage explore CTA, hypothesis pre-fill (**WS-8** §2–3). • Confirm activation cohort separates from capture-only on the retention curve (**WS-6** §4b) — if not, the activation definition or the loop is wrong; fix before scaling. • Build the **shareable resume card** export (redacted to intent + filenames, "↻ resumed in 30s with brain2" footer) (**WS-8** §4). |
| **W3** | Mon 2026-06-15 → Fri 2026-06-19 | **Public surface up: waitlist + signature guide** | • Publish **landing page + waitlist** ("notify me") leading with the hero GIF, copy-paste install, and the honest one-liner "Free, forever, on your machine. Pay only when you want your context to follow you" (**WS-1** §3, **WS-3** §5). • Publish the signature **"Build vs Buy: a context-resume layer for your editor"** guide — the durable always-on engine; link it from nav/footer (**WS-1** §4, **WS-2** §6). • Publish **marketplace listings live**: Claude Code plugin (`/plugin install brain2@brain2`) + VS Code Marketplace with keyword-rich name "brain2 — Resume Card / Context Capture (Claude Code, git)" (**WS-2** ch.2/3). • Seed daily.dev Source + Squad; start build-in-public cadence on X/Bluesky (**WS-2** ch.6/7). |
| **W4** | Mon 2026-06-22 → Fri 2026-06-26 | **Asset prep + monetization + legal live** | • Finalize **Show HN draft** (problem-framed title, 7-part founder first comment) and **Product Hunt gallery** (resume-card hero shot, capture moment, `/brain2:resume` inline, privacy panel) + the **60–90s demo GIF** that powers every channel (**WS-2** §2/§3, ch.9). • **Pricing page live**: Free / Pro $8/mo ($6 annual) / Team $12/user (SHARING + MANAGED-KEYS rows marked "coming soon") + the 6 in-product upgrade triggers wired (**WS-3** §2–5). • **Payments live**: Lemon Squeezy MoR, one paid Cloud product (monthly + annual), 14-day card-required trial, webhook endpoint (signature-verified, idempotent, `customer_id→org_id`), dunning (smart retries ~7/21d + card updater + 4-step emails), run the T1–T10 test plan in sandbox (**WS-4** §2–6). • **Legal kit in place**: single-member LLC + EIN + business bank account; ToS + Privacy Policy + DPA (lawyer-reviewed); `/security` page published w/ public sub-processor list; **LLM/embedding no-train/no-retain terms confirmed**; cloud-enable egress disclosure at the seam (**WS-5** §1–5). |
| **W5** | Mon 2026-06-29 → Thu 2026-07-02 | **LAUNCH DAY** | • **Go/no-go gate** (§3) read Mon AM against beta metrics. • If GO: **Show HN** Tue 2026-06-30 ~8:00am ET, camp the thread 6h+; Reddit + daily.dev + X ride the same week (**WS-2** ch.1/4/6/7). • **Product Hunt** staggered 1–2 weeks out (Tue/Wed/Thu 12:01am PT) once HN gives social proof (**WS-2** ch.5). • Maker comments, live monitoring on the PostHog launch dashboard (**WS-6** §4c). Full hour-by-hour in §2. |
| **W6+** | Mon 2026-07-06 → ongoing | **Post-launch retention loop** | • Ship the **"two weeks of brain2: installs, what broke, what's next"** build-in-public post (**WS-2** ch.4 wk4). • Run the **re-engagement loop**: resume-card-on-focus polish, branch-switch auto-offer (**WS-8** §5). • Read the **4-week go/no-go** (**WS-6** §5): GO-to-scale-spend only if month-1 users ≥847 **and** activation ≥25% **and** week-1 NSM retention ≥34%. • Treat **free→cloud ≥5%** as a month-2+ gate, not launch-day. Iterate the SYNC/cross-repo upgrade-trigger mix before discounting (**WS-3** §4, **WS-6** §5). |

---

## 2. Launch day — hour-by-hour choreography (W5, anchor: Tue 2026-06-30)

All times **ET** (founder primary clock); PT noted where it drives Product Hunt timing.
The discipline: HN delivers **attention, rarely day-1 paid conversion** — optimize the spike
for **free-tier installs + GitHub stars + waitlist**, not revenue (**WS-2** §5). No booster
comments from alt accounts. Agree-then-address every objection.

| Time (ET) | Action | Source |
|---|---|---|
| **T-1 day (Mon 06-29)** | Final go/no-go read (§3). Freeze code. Verify install path on a clean machine (plugin reload + `--check` health). Confirm PostHog dashboard live + events firing. Pre-write 8–10 likely HN objection replies. | WS-6, WS-8 |
| **06:30** | Final smoke test: live capture→resume on both tiers; checkout sandbox→prod sanity; `/security` + pricing + landing all 200-OK. | WS-4, WS-5, WS-8 |
| **07:45** | Post pre-warm: nothing public yet. Tee up the Show HN text + README demo link in a draft. | WS-2 §2 |
| **08:00** | **Post Show HN** (problem-framed title). Immediately add the 7-part founder first comment. Do **not** ask for upvotes. | WS-2 §2 |
| **08:00–14:00** | **Camp the thread.** Reply to every comment within minutes; agree-then-address. Watch rank; a 24h "controlled explosion" then a week-long tail. | WS-2 §2/§5 |
| **09:00** | Cross-post the demo GIF to r/vscode, r/ClaudeAI, r/SideProject (problem-first, not producty). Share in Claude Code + VS Code Discord #show-and-tell. | WS-2 ch.4/10 |
| **10:00** | Submit brain2 blog as a daily.dev Source; post in the Squad. Fire the build-in-public X/Bluesky thread with the GIF. | WS-2 ch.6/7 |
| **11:00** | **Monitoring checkpoint #1** — PostHog: installs, `flow_completed`, first `snapshot_captured`, activation rate so far, crash-free sessions. Watch for an install-path break (the #1 launch-day killer per WS-8). | WS-6 §4c |
| **12:00–13:00** | Keep answering HN. Capture recurring questions → live-edit the README FAQ. | WS-2 §2 |
| **14:00** | **Monitoring checkpoint #2** — activation trending to ≥25%? funnel step where people drop? Hot-patch onboarding copy/diagnostics if a friction wall appears. | WS-6 §4, WS-8 §2 |
| **17:00** | Recap thread on X ("N installs, here's what's breaking and what I'm fixing tonight"). Thank HN commenters. | WS-2 ch.4 |
| **20:00** | **Monitoring checkpoint #3** — day-1 totals vs the 100–500 band [#2ce52b97]. Log every bug + every "what was missing from the snapshot?" answer (the WS-1 §5 validation question). | WS-6, WS-1 |
| **22:00** | Ship same-day hot-fixes for any install/connect breakage. Update the HN thread if a fix lands. | WS-8 §2 |
| **T+1..T+7** | Ride the tail: reply to late HN/Reddit, schedule **Product Hunt** for the following Tue/Wed/Thu 12:01am PT (gallery + maker comment ready), keep the build-in-public cadence. | WS-2 ch.5/7 |

**Product Hunt sub-choreography** (when it runs, ~1–2 wks post-HN): go live **12:01am PT**,
post the maker first comment immediately, keep upvote velocity natural and geographically
diverse (first-4-hours momentum is the Top-5 predictor). Treat PH as **awareness + social
proof**, not the signup engine (**WS-2** §1/§3).

---

## 3. Go / No-Go gate (read W5 Monday, before launch day)

Using **WS-6's exact thresholds** (`ws6-metrics-instrumentation.md` §5), measured on the
W1–W2 beta cohort. **Pass requires ALL hard gates GREEN.**

| Gate | NO-GO (below) | GO (meets) | STRONG | Decides |
|---|---|---|---|---|
| **Activation rate** (7-day, install→restoring-resume, coverage ≠ `gap`) | **< 20%** | **≥ 25%** | ≥ 40% | **Hard gate.** Below 20% = the loop isn't delivering value; fix capture→resume quality first. |
| **Crash-free sessions** (Sentry; proxy: `status=ok` rate on capture/resume/explore) | **< 99%** | **≥ 99.5%** | ≥ 99.9% | **Hard gate.** A context tool that crashes on the working tree forfeits trust instantly (WS-5 privacy posture). |
| TTV to activation (median) | > 24 h | ≤ 24 h | ≤ 1 h | Soft — flags onboarding friction (WS-8). |
| Week-1 NSM retention (activated cohort) | < 25% | ≥ 34% | ≥ 45% | Soft at launch; **hard at the W6 scale-spend gate.** |
| Beta validation signal | < 5/10 on any core claim | ≥ 5/10 patterns [#1665bb5c] | clear lookalike pull | Soft — if the wedge confuses, swap to "save state for coding" before HN (WS-1 §5 fallback). |

**Decision rule.** **GO to launch** only if activation ≥ 25% **AND** crash-free ≥ 99.5% on the
beta cohort. **NO-GO / fix-first** if activation < 20% **OR** crash-free < 99% — slip the
launch a week and fix the loop; do not pour HN attention into a leaky or crashing funnel
(WS-6 §5). **Free→cloud conversion is explicitly NOT a launch-day gate** — it is a month-2+
gate (≥5% over 90 days) because SYNC/cross-repo are the v1 paid value and need post-launch
volume to validate (**WS-3** §5, **WS-6** §5).

---

## 4. Dependency map (which workstream blocks which)

```
                       ┌─────────────────────────────────────────────┐
                       │  W0: LIVE LOOP (cloud+local) + WS-6 meters   │  ← blocks everything
                       │      + WS-8 friction fixes                   │     measurable
                       └───────────────┬─────────────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                               ▼                              ▼
  WS-1 positioning            WS-8 activation loop           WS-6 instrumentation
  (wedge/ICP/messaging)       (aha, friction, share loop)    (NSM, taxonomy, gates)
        │                               │                              │
        │  feeds copy                   │  feeds the share artifact    │  feeds go/no-go
        ▼                               ▼                              ▼
  WS-2 distribution  ◀──────────────────┴──────────────────────────────┘
  (HN/PH/marketplace/guide)      (needs working loop + GIF + copy + meters)
        │
        │  the public spike needs the buyable surface ready:
        ▼
  ┌──────────────┬───────────────┬───────────────────────┐
  │ WS-3 pricing │ WS-4 payments │ WS-5 legal/privacy/trust│  ← all must be LIVE before
  │  page+tiers  │  MoR+webhooks │  LLC+ToS+DPA+/security  │     launch *if* you sell at launch
  └──────────────┴───────┬───────┴───────────────────────┘
                         │
                         ▼
                  W5 LAUNCH DAY (WS-2 choreography + WS-6 monitoring)
                         │
                         ▼
                  W6+ retention loop (WS-8) → W6 scale-spend gate (WS-6)
```

**Blocking edges, stated:**
- **W0 (live loop + meters) blocks all measurement** — no activation/crash-free gate without it; it is the literal next step [#141be947].
- **WS-8 + WS-1 block WS-2** — you cannot post the Show HN / PH demo until the loop works in-session (WS-8) and the wedge copy is validated (WS-1).
- **WS-3 → WS-4** — payments implement the prices WS-3 sets; pricing page and checkout must agree.
- **WS-4 + WS-5 jointly gate "selling at launch"** — you may **not** take a paid dollar before the LLC, ToS/Privacy/DPA, `/security` page, **and** the MoR webhook entitlement path are all live (WS-5 §1, WS-4 §2.6). You *can* launch the **free tier** without the paid surface complete — decoupling the free spike from the paid gate is a valid de-risking move.
- **WS-5 blocks WS-4's cloud egress** — the egress disclosure at the seam and the no-train/no-retain confirmation must precede the first byte leaving a user's machine (WS-5 §5).
- **WS-6 gates WS-2's launch day** — go/no-go (§3) is read from WS-6 metrics; a NO-GO slips the WS-2 spike.

---

## 5. Critical path + biggest risk (single callout)

**The smallest set of must-dos** (drop any one and there is no credible launch):

1. **W0 — the live capture→resume loop works on both tiers, instrumented.** Everything
   measurable hangs off this; it is the next action of record [#141be947]. (WS-8, WS-6)
2. **The aha is reachable in session 1** — guaranteed first capture + a populated resume
   card, no empty/`gap` dead-end. This is what activation measures and what the whole
   funnel converts on. (WS-8 §1–3)
3. **One demo GIF + a validated wedge.** The GIF powers every channel; "git stash for your
   head" must paraphrase clean (≥5/10) or fall back before HN. (WS-2 ch.9, WS-1 §5)
4. **Show HN, executed with discipline** — problem-framed title, founder first comment,
   6h thread camp. The single biggest day-1 install spike. (WS-2 §2)
5. **Pass the go/no-go** — activation ≥25% AND crash-free ≥99.5% before posting. (WS-6 §3)

If selling at launch, add **(6) the paid surface live and legal**: Lemon Squeezy MoR +
pricing page + LLC/ToS/DPA/`/security`. If not ready, **launch free-only and defer the paid
gate** rather than ship it half-done — the free spike does not depend on it.

> **⚠️ Biggest risk: WS-5 (legal/privacy/trust) is the highest-risk workstream — because
> brain2 stores code.** Every other workstream's downside is a slow launch; WS-5's downside
> is existential. brain2 captures git branches, file paths, `git diff --stat`, and intent —
> source-code-adjacent data — and on the cloud tier that egresses to Supabase + LLM/embedding
> APIs (`ws5-legal-privacy-trust.md`, "Why this is the highest-risk workstream"). A missing
> LLC leaves personal assets exposed; an unconfirmed **no-train/no-retain** term on the LLM
> provider, or a privacy claim the architecture doesn't back, is a trust-and-liability event
> that no amount of HN traction survives. **Mitigations, on the critical path:** (a) the free
> local tier's "code never leaves your machine" is *verifiable* — make it the trust lead
> (WS-5 §5); (b) confirm + document the LLM/embedding no-train/no-retain terms **before W4
> close** — it is the single highest-priority disclosure; (c) one fixed-fee lawyer pass on
> ToS/Privacy/DPA before the first paid dollar; (d) publish `/security` with the live
> sub-processor list before the cloud tier is sellable. Treat WS-5 sign-off as a **hard
> precondition** of charging money, not a launch-week scramble.

---

### KB findings cited
`[#854de64b]` beta cohort 20–50 / validation cuts ~60% launch bugs / 60% unvalidated fail ·
`[#1665bb5c]` validate against lookalikes, act on patterns (≈5/10) not single replies ·
`[#141be947]` current-state snapshot: next step = reload plugin, run live cloud capture/resume loop ·
`[#43300575]` month-1 median 847 users, CAC $127, retention 34%, break-even 8.2mo ·
`[#2ce52b97]` early-stage SaaS KPIs + indie launch-day 100–500 signups.
KB coverage on launch sequencing was **sparse**; the dated structure here is synthesized from
the seven sibling workstream docs, anchored on the KB's validation/beta benchmarks.

### Sibling docs cross-referenced
`ws1-positioning-icp.md`, `ws2-distribution-channels.md`, `ws3-pricing-packaging.md`,
`ws4-payments-billing.md`, `ws5-legal-privacy-trust.md`, `ws6-metrics-instrumentation.md`,
`ws8-onboarding-growth.md`.
