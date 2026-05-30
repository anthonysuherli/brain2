# brain2 — Efficient Growth Plan (highest-leverage sequence)

**Date:** 2026-05-30 · **Owner:** founder (solo)

The minimal, efficiency-first execution path derived from
[`efficient-growth-strategy.md`](./efficient-growth-strategy.md). This is **not** a
replacement for [`ACTION-PLAN.md`](./ACTION-PLAN.md) — that is the full launch
timeline. This doc isolates the *fewest moves with the most leverage* so a solo
founder knows what to do first and what to ignore until later.

> **Sequencing rule:** instrument (W0) → make installs work + convert (1,2,3) →
> *then* drive traffic (4,5). Driving traffic to an un-instrumented, high-friction
> product is the most common way to waste a launch.

---

## W0 — Preconditions (do before any traffic)

These gate everything; skipping them means flying blind or losing trust.

- [ ] **Telemetry live** — PostHog event taxonomy (`onboarding:flow_completed`,
  `capture:snapshot_captured`, `resume:resume_card_viewed` w/ `coverage_band`),
  salted-hash identity, **content-free allowlist CI**. Confirm events fire on the live
  loop *before any user sees it*. → [`ws6`](./ws6-metrics-instrumentation.md)
- [ ] **Trust precondition in motion** — LLC/EIN started, ToS/Privacy/DPA drafted +
  lawyer review booked, **no-train/no-retain LLM term confirmed**. Free-only launch can
  proceed without payments, but **not** without the privacy story. → [`ws5`](./ws5-legal-privacy-trust.md)
- [ ] **Both loops proven** — live `capture → resume` on local *and* cloud tiers;
  `python -m brain2.api.main --check` prints ✓db ✓sqlite-vec ✓loopback.

**Exit check:** a clean machine installs → captures → sees a populated resume card,
and the events land in PostHog.

---

## Move 1 — Own the plugin/MCP discovery surface *(S effort, highest leverage)*

A few hours of work; compounding, near-zero marginal cost.

- [ ] Publish the marketplace repo publicly; verify `/plugin install brain2@brain2`
  and `claude mcp add` both work from a clean machine.
- [ ] Submit/list everywhere devs browse: the official Claude Code plugin ecosystem,
  community directories (claudemarketplaces.com, claudecodeplugins.dev), and the
  relevant `awesome-claude-code` / `awesome-mcp-servers` GitHub lists.
- [ ] Set deliberate **GitHub repo topics** (discovery ranking signal — PostHog's HN
  lesson: bad tags suppressed reach until fixed).

---

## Move 2 — VS Code listing as the SEO/trust engine *(M effort, compounding)*

The Marketplace is a search engine; the listing is a landing page.

- [ ] Publish with a **keyword-rich display name**:
  *"brain2 — Resume Card / Context Capture (Claude Code, git)."*
- [ ] Deliberate keywords/tags (≤30): `context`, `resume`, `session memory`,
  `ai pair programming`, `claude code`, `mcp`, `git`, `productivity`.
- [ ] **Hero GIF** of the resume card at the top of the README — the #1 conversion lever.
- [ ] Farm the **first ~20 reviews** from design partners (rating + install count drive
  ranking). → [`ws2 §1`, `ws8`](./ws2-distribution-channels.md)

---

## Move 3 — Protect time-to-first-value *(M effort, this is the moat)*

Target: **< 2 minutes**, **zero config**, aha reached in session 1.

- [ ] One-command install; **"Reload this session now"** as the bold final step.
- [ ] **Guaranteed first capture** on first activation; tier echo on boot;
  MCP connected/disconnected status indicator.
- [ ] A guided **"capture now → close → resume"** demo so the user *manufactures* the
  aha moment immediately.
- [ ] Keep **all** Supabase/auth/setup friction out of the free path. → [`ws8`](./ws8-onboarding-growth.md)

---

## Move 4 — One signature content wedge *(M effort, durable)*

Win the *problem*, not the product. One strong essay > a blog cadence.

- [ ] Write **"Build vs Buy: a context-resume layer for your editor"** (or
  "We measured the context-rebuild tax of AI pair programming") — concrete code/commands,
  zero sales tone, target real search queries ("resume coding context", "git context
  snapshot", "Claude Code MCP context"). → [`ws2 §6`](./ws2-distribution-channels.md)
- [ ] Link it from repo README, landing page nav/footer; mine `docs/reports/` for data.

---

## Move 5 — Narrow drops, then Show HN — sequenced *(M effort, the spike)*

Only after Moves 1–3 are solid (so the spike converts).

- [ ] **Recruit 20–50 design partners** from Claude/Cursor Discords, X dev circles,
  IndieHackers; run the message test on the wedge.
- [ ] **Show HN** — problem-framed title ("kill the 9.5-min context-rebuild tax"),
  7-part founder first comment, camp the thread 6h+, **no alt-account boosters**.
- [ ] **Same-day** cross-post the demo GIF to r/vscode, r/ClaudeAI, r/SideProject;
  Discord #show-and-tell; X/Bluesky thread; daily.dev Source.
- [ ] **Product Hunt** ~1–2 weeks later, once HN gives social proof.
  → full runbook in [`ws7`](./ws7-launch-runbook.md) / [`ACTION-PLAN W4–W5`](./ACTION-PLAN.md)

---

## Move 6 — Paid motion: defer until the flywheel turns

- [ ] Do **not** sell sync/cross-repo/team value props yet (unbuilt per CLAUDE.md).
- [ ] Instrument **who hits local's limits** (multi-machine, cross-repo); treat those as
  PQL signal pulling the cloud tier into existence. Free→cloud ≥5% is a **month-2** bar,
  not launch-day. → [`ws3`, `ws4`](./ws3-pricing-packaging.md)

---

## Go / no-go (from `ACTION-PLAN`)

- **GO** only if `activation ≥ 25%` **AND** `crash-free ≥ 99.5%`.
- **Slip a week** if `activation < 20%` **OR** `crash-free < 99%`.

## What to deliberately NOT do (efficiency = subtraction)

- ❌ Paid ads / SEM — devs skip them; CAC dwarfs the local tier's value.
- ❌ Broad launch platforms as the *primary* engine — awareness only.
- ❌ Selling unbuilt cloud features — burns trust, the one non-recoverable asset.
- ❌ A content cadence before one signature piece exists.
- ❌ Any of Moves 4–5 before telemetry (W0) and TTFV (Move 3) are real.
