# brain2 — Action Plan & Timeline

Distilled from `ws1`–`ws8` + the `ws7` runbook into a do-this-now checklist.
Anchor: **W0 = week of 2026-05-29**. Solo founder = you own every box.

> **Rule of the road:** the free-tier launch can ship *without* the paid surface.
> If payments/legal slip, **launch free-only and defer the paid gate** — don't slip the whole launch.

---

## ⏱ START NOW — long-lead items (external latency; begin W0, finish by W4)

These have waiting time you don't control. Kick them off this week even though they're not "due" until W4.

- [ ] **Form single-member LLC + EIN** (home state) + open a business bank account. *(WS-5)*
- [ ] **Create Lemon Squeezy account**, verify identity + payout. *(WS-4)*
- [ ] **Confirm + document the LLM/embedding provider's no-train / no-retain API terms** — the single highest-priority disclosure. *(WS-5 — on the critical path, must close before W4)*
- [ ] **Generate ToS + Privacy Policy + DPA** (Termly/GetTerms) and **book one fixed-fee lawyer review**. *(WS-5)*

---

## W0 · Mon 05-25 → Fri 05-29 — Prove the loop + turn on the meters
*Blocks everything measurable. This is the next action of record.*

- [ ] Reload the plugin so the MCP server connects; run the **live capture→resume loop on the cloud tier** end-to-end.
- [ ] Verify the **free local loop** too; ship `python -m brain2.api.main --check` → prints ✓db ✓sqlite-vec ✓loopback. *(WS-8)*
- [ ] Land the **highest-priority friction fixes**: "Reload this session now" as the bold last install step; MCP-connect diagnostic + status-bar connected/disconnected state; **guaranteed first capture** on first activation; tier echo on boot. *(WS-8 §2)*
- [ ] Stand up **PostHog**: ship the event taxonomy (`onboarding:flow_completed`, `capture:snapshot_captured`, `resume:resume_card_viewed` w/ `coverage_band`, `monetization:*`), super-properties, salted-hash identity, **content-free allowlist CI**. *(WS-6 §3)*
- [ ] Confirm instrumentation fires on the live loop **before any user sees it**.

**Exit check:** a clean machine can install → capture → see a populated resume card, and the events land in PostHog.

---

## W1 · Mon 06-01 → Fri 06-05 — Private beta opens
- [ ] Recruit **20–50 design partners** (Persona A solo indie + Persona B agentic power user) from Cursor/Claude Discords, X dev circles, IndieHackers. *(WS-1 §2, WS-2 ch.7/10)*
- [ ] Ship them the one-command install + the **"switch windows and come back" first-session script**. *(WS-8 §1/§5)*
- [ ] Run the **message test**: show "git stash for your head" + the hero cold to lookalikes; track the 3 risky assumptions. *(WS-1 §5)*
- [ ] Watch **activation rate + week-1 retention** in PostHog from day one.

---

## W2 · Mon 06-08 → Fri 06-12 — Feedback → patterns → fixes
- [ ] Read beta as **patterns, not single replies** (act on ≥5/10 signal). Targets: ≥5/10 paraphrase the wedge unprompted; ≥5/10 ask for the link unprompted; ≥5/10 cite local/private as a try-reason.
- [ ] Fix whatever blocks the **first populated resume card in session 1** — empty-state copy, `gap`-coverage explore CTA, hypothesis pre-fill. *(WS-8 §2–3)*
- [ ] Confirm the **activated cohort separates** from capture-only on the retention curve. If not, the activation definition or the loop is wrong — fix before scaling. *(WS-6 §4b)*
- [ ] Build the **shareable resume card** export (redacted to intent + filenames, "↻ resumed in 30s with brain2" footer) — the growth loop. *(WS-8 §4)*

---

## W3 · Mon 06-15 → Fri 06-19 — Public surface up
- [ ] Publish **landing page + waitlist** leading with the hero GIF, copy-paste install, and the one-liner *"Free, forever, on your machine. Pay only when you want your context to follow you."*
- [ ] Publish the signature **"Build vs Buy: a context-resume layer for your editor"** guide; link from nav/footer. *(WS-2 §6)*
- [ ] Go **live on marketplaces**: Claude Code plugin (`/plugin install brain2@brain2`) + VS Code Marketplace with the keyword-rich name *"brain2 — Resume Card / Context Capture (Claude Code, git)."* *(WS-2 ch.2/3)*
- [ ] Seed daily.dev Source + Squad; start build-in-public cadence on X/Bluesky.

---

## W4 · Mon 06-22 → Fri 06-26 — Assets + monetization + legal live
- [ ] Finalize **Show HN draft** (problem-framed title, 7-part founder first comment) + **Product Hunt gallery** + the **60–90s demo GIF** that powers every channel. *(WS-2 §2/§3)*
- [ ] **Pricing page live**: Free / Pro $8 ($6 annual) / Team $12 (SHARING + MANAGED-KEYS rows "coming soon") + the 6 in-product upgrade triggers wired. *(WS-3)*
- [ ] **Payments live**: Lemon Squeezy MoR, one paid Cloud product (monthly + annual), 14-day card-required trial, webhook endpoint (signature-verified, idempotent, `customer_id→org_id`), dunning (smart retries ~7/21d + card updater + 4-step emails). **Run the T1–T10 test plan in sandbox.** *(WS-4 §2–6)*
- [ ] **Legal kit in place**: LLC + EIN + bank account done; ToS + Privacy Policy + DPA lawyer-reviewed; `/security` page published w/ public sub-processor list; **no-train/no-retain terms confirmed**; cloud-enable egress disclosure at the seam. *(WS-5)*

---

## W5 · Mon 06-29 → Thu 07-02 — LAUNCH
- [ ] **Mon AM — read the go/no-go gate** against the beta cohort:
  - **GO only if `activation ≥ 25%` AND `crash-free ≥ 99.5%`.**
  - **NO-GO / slip a week if** `activation < 20%` OR `crash-free < 99%`.
  - (Free→cloud conversion is a **month-2+** gate, not launch-day.)
- [ ] **Tue 06-30, 8:00am ET — post Show HN** (problem-framed title) + founder first comment. **Camp the thread 6h+.** No upvote asks, no alt-account boosters.
- [ ] **By 10am** — cross-post the demo GIF to r/vscode, r/ClaudeAI, r/SideProject; share in Discord #show-and-tell; fire the X/Bluesky thread; submit daily.dev Source.
- [ ] **Monitoring checkpoints 11:00 / 14:00 / 20:00** — installs, activation %, crash-free; hot-patch onboarding if a friction wall appears.
- [ ] **Product Hunt** staggered ~1–2 weeks later (Tue/Wed/Thu, 12:01am PT) once HN gives social proof.

---

## W6+ · Mon 07-06 → ongoing — Retention loop
- [ ] Ship the **"two weeks of brain2: installs, what broke, what's next"** build-in-public post.
- [ ] Polish the **re-engagement loop**: resume-card-on-focus, branch-switch auto-offer. *(WS-8 §5)*
- [ ] **Read the 4-week scale-spend gate:** scale acquisition only if month-1 users ≥847 **AND** activation ≥25% **AND** week-1 retention ≥34%.
- [ ] Iterate the SYNC / cross-repo **upgrade-trigger mix** before discounting; treat free→cloud ≥5% as the month-2 validation bar.

---

## The 5 must-dos (drop any one = no credible launch)
1. **W0** — live capture→resume loop on both tiers, instrumented.
2. **The aha is reachable in session 1** — guaranteed first capture + populated card.
3. **One demo GIF + a validated wedge** (≥5/10 paraphrase, or fall back to "save state for coding").
4. **Show HN, executed with discipline.**
5. **Pass the go/no-go** (activation ≥25% AND crash-free ≥99.5%).

## ⚠ The one risk that's existential, not just slow
**WS-5 (legal/privacy/trust)** — brain2 stores code. Treat the LLC, the lawyer-reviewed
docs, the `/security` page, and the **confirmed no-train/no-retain term** as a *hard
precondition of charging money*, not a launch-week scramble. The free tier's verifiable
"code never leaves your machine" is your trust lead until SOC 2 is warranted (first
enterprise deal).
