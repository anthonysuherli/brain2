# WS6 — Metrics & Instrumentation

**Workstream:** Launch — Metrics & Instrumentation
**Product:** br8n (freemium dev tool; free local SQLite tier / paid cloud Supabase tier)
**Owner action:** instrument the capture → resume → explore loop, the upgrade/tier surfaces, and onboarding.
**Date:** 2026-05-29

---

## Privacy constraint (read first, applies to everything below)

**Instrument behavior, NEVER code content.** No event property in this spec carries source
code, diff bodies, file contents, prompts, hypothesis text, snapshot bodies, branch names that
could leak client identity, or any KB finding text. We send *counts, sizes, durations, enums,
and hashed identifiers* only. br8n's local tier already keeps all content on-device
(`~/.br8n/brain.db`); analytics must preserve that contract even when the user is on cloud.
Every property table below is content-free by construction — the only "what was captured"
signal we keep is `file_count`, `diff_loc` (line count, not text), and a `repo_id_hash`
(salted SHA-256 of the repo path/remote, never the name).

This is non-negotiable and is the differentiating trust posture for a context tool that
necessarily sits on top of a developer's working tree.

---

## 1. North Star metric

### Proposed North Star: **Weekly Context-Restoring Resumes (WCRR)**

> The count of `resume_card_viewed` events per week where the resume actually restored context —
> i.e. the card was served from a KB that had ≥1 prior capture in the same repo+branch
> (`coverage` ∈ {`rich`, `sparse`}, not `gap`) **and** the developer continued working in that
> session (a subsequent `capture` or tool/file activity within 30 min, or `card_dismissed_resumed`).

**Why this is the right North Star.** A good North Star captures the *value the customer
derives*, is influenceable by product (not directly settable), and leads revenue
([Amplitude North Star Framework](https://amplitude.com/books/north-star/about-north-star-framework)).
WCRR satisfies all three:

- **Captures real value, not vanity.** br8n's entire reason to exist is killing the
  ~9.5-minute context-rebuild tax (CLAUDE.md). A *resume that restored context* is the literal
  moment of value delivery. A raw "resume count" would be gameable/vanity; gating on
  prior-capture + continued-work makes it a genuine value event — exactly the discipline
  Amplitude recommends ("if you can move your North Star directly, it's probably not a good
  North Star").
- **Leading indicator of revenue.** Weekly-habit users convert to paid at 3–4× the rate of
  sporadic users ([Pulseahead trial-to-paid benchmarks](https://www.pulseahead.com/blog/trial-to-paid-conversion-benchmarks-in-saas)).
  WCRR is a weekly *habit* metric, so it is structurally a leading indicator of the cloud-tier
  conversion that monetizes [#2ce52b97].
- **Product can influence it via clear inputs.** Resume card quality, capture frequency,
  coverage band, auto-resume-on-focus (Phase 2) all feed it.

**Input metrics (the 3–5 levers that move WCRR):**
1. Captures per active user per week (you can't restore what you didn't capture).
2. Resume coverage mix (% of resumes landing `rich`/`sparse` vs `gap`).
3. Median time-to-first-resume after a capture.
4. Auto-resume-on-focus attach rate (Phase 2 surface).

### Alternative North Stars (considered, not chosen)

| # | Candidate | Why considered | Why not chosen as NSM |
|---|---|---|---|
| A | **Weekly Active Repos with ≥1 capture+resume pair** | Account-level breadth; maps cleanly to "habit woven into workflow" retention pattern (productivity apps retain because they enter the workflow — [Lovable retention benchmarks](https://lovable.dev/guides/what-is-a-good-retention-rate-for-an-app)). | Coarser than WCRR — counts the repo once no matter how much value was delivered. Better as a *retention denominator* than the NSM. |
| B | **Context-minutes saved per week** (WCRR × modeled ~9.5 min/resume) | Speaks the product's core promise in business language (time recovered); great for marketing/board. | Derived/modeled (the 9.5-min figure is an assumption), so it fails the "metric teams can directly influence and trust" bar. Use it as the *narrative wrapper* on top of WCRR, not the operating metric. |

---

## 2. Activation event & time-to-value

### Activation event: **First Successful Capture→Resume Loop**

> A user is **activated** the first time they fire `snapshot_captured` and then, in the same
> repo+branch, fire a context-restoring `resume_card_viewed` (`coverage` ≠ `gap`) — the minimum
> closed loop that proves the product's promise.

**Rationale.** Activation is the moment the *business* sees a user realize value, distinct from
a single "aha" ([Appcues aha-moment guide](https://www.appcues.com/blog/aha-moment-guide);
[Statsig](https://www.statsig.com/perspectives/aha-moment-saas-metrics)). For br8n a lone
capture is a promise; the *resume that pays it back* is activation. We will validate this
choice the way PostHog recommends — build a cohort of users who completed the loop and confirm
they retain materially better than capture-only users; if not, revisit the definition
([PostHog AARRR funnel](https://posthog.com/product-engineers/aarrr-pirate-funnel)).

**Do not gate the aha behind auth on the local tier.** Best practice is to deliver value before
forcing login/credit-card ([Appcues](https://www.appcues.com/blog/aha-moment-guide)) — and the
free tier already requires no key (loopback-only, CLAUDE.md), so the activation loop is reachable
on first install with zero friction. Protect that.

**Time-to-value (TTV) targets.** Shorter TTV → less churn
([Userpilot aha guide](https://userpilot.com/blog/aha-moment/)). Top-quartile PLG products
activate ≥60% of users within the first 24h
([Userpilot activation benchmark 2024](https://userpilot.com/blog/user-activation-rate-benchmark-report-2024/)).

| Target | Goal | Stretch |
|---|---|---|
| Time to first **capture** (install → `snapshot_captured`) | < 10 min (one work session) | < 5 min |
| Time to **activation** (install → first restoring resume) | < 24 h | < 1 h (same session) |
| Activation **rate** (of installs, 7-day window) | ≥ 25% | ≥ 40% (top-quartile band, 20–40% is leading-PLG range per [Userpilot](https://userpilot.com/blog/saas-average-conversion-rate/)) |

---

## 3. Event taxonomy → PostHog

PostHog conventions applied throughout ([PostHog naming best practices](https://posthog.com/questions/best-practices-naming-convention-for-event-names-and-properties)):
**`category:object_action`**, lowercase, snake_case, present-tense verbs; booleans use
`is_`/`has_`; timestamps end `_timestamp`. To avoid property explosion we use static property
names with enum values (e.g. `coverage_band`), never dynamic keys.

**Global super-properties** (attached to every event, set once on identify):
`tier` (`local`|`cloud`), `app_version`, `client_surface` (`mcp`|`vscode`|`skill`),
`distinct_id` (anonymous install UUID), `org_id` (`local` for free tier).
**Privacy:** none of these carry code, paths, names, or KB text.

| Event (`category:object_action`) | Fires when | Properties (content-free) | Notes |
|---|---|---|---|
| `onboarding:flow_completed` | User finishes first-run setup (install + first repo+branch resolved) | `surface`, `tier`, `duration_ms`, `setup_path` (`fresh`\|`existing_db`) | Onboarding-complete event (KB key event [#7648d691]). |
| `capture:snapshot_captured` | `br8n_capture` / `/v1/capture` succeeds | `repo_id_hash`, `branch_id_hash`, `file_count`, `diff_loc`, `has_hypothesis` (bool), `trigger` (`manual`\|`focus_loss`\|`skill`), `tier` | **No file contents, no diff text, no hypothesis text, no real branch name** — hashes + counts only. |
| `resume:resume_card_viewed` | `br8n_resume` / `/v1/resume` returns a card | `repo_id_hash`, `branch_id_hash`, `coverage_band` (`rich`\|`sparse`\|`gap`), `snapshot_count`, `is_auto_resume` (bool), `latency_ms`, `tier` | Core NSM source event. `coverage_band` is the value gate. |
| `resume:card_dismissed_resumed` | User acts on the card and continues the session | `repo_id_hash`, `time_to_action_ms`, `is_auto_resume` | Confirms the "continued work" half of NSM. |
| `explore:gap_fill_started` | `br8n_explore` / `/v1/explore` kicks off | `repo_id_hash`, `branch_id_hash`, `trigger` (`gap_band`\|`manual`\|`skill`), `tier` | No query/plan text. |
| `explore:gap_fill_completed` | Pipeline merges findings + rebuilds synopsis | `repo_id_hash`, `duration_ms`, `findings_added` (int), `coverage_before`, `coverage_after`, `status` (`ok`\|`error`) | Counts only — no finding text. |
| `monetization:upgrade_clicked` | User clicks an upgrade/CTA surface | `cta_location` (`resume_card`\|`gap_band`\|`settings`\|`cli_nudge`), `current_tier`, `prompt_reason` (`sync`\|`cross_repo`\|`manual`) | Upgrade-click key event [#7648d691]. No PII. |
| `monetization:tier_switched` | `BR8N_BACKEND` / login changes effective tier | `from_tier`, `to_tier`, `method` (`env`\|`login`\|`settings`), `is_first_switch` (bool) | Tracks free→cloud movement; the conversion event. |
| `monetization:checkout_completed` | Paid subscription starts (cloud) | `plan`, `mrr_cents`, `is_first_payment` (bool) | Revenue tie-in for CAC/MRR [#2ce52b97], [#1aae84be]. |

**Identity & privacy mechanics:**
- `repo_id_hash` / `branch_id_hash` = salted SHA-256 of repo remote/path and branch; salt is
  per-install and never transmitted, so identifiers are stable for cohorting but non-reversible
  and non-correlatable across installs.
- Local tier: telemetry is **opt-in**, anonymous (`org_id="local"`), and the user can disable it
  entirely; even when on, it ships only the columns above.
- A schema CI check (PostHog schema management — [docs](https://posthog.com/docs/product-analytics/schema-management))
  rejects any new property not on an allowlist, preventing accidental content leakage.

---

## 4. Launch funnel & dashboard spec

Pirate-funnel framing, instrumented in PostHog ([AARRR](https://posthog.com/product-engineers/aarrr-pirate-funnel); [Funnels docs](https://posthog.com/docs/product-analytics/funnels)).

### 4a. Acquisition→Revenue funnel (PostHog Funnel insight)

| Step | Event | Definition |
|---|---|---|
| 1. Install / Signup | `onboarding:flow_completed` | First-run completed (proxy for "signup" on a local-first tool). |
| 2. First capture | `capture:snapshot_captured` (first) | Promise made. |
| 3. **Activation** | first restoring `resume:resume_card_viewed` (`coverage_band` ≠ `gap`) in same repo+branch | Promise paid back — the activation gate from §2. |
| 4. Week-1 retention | any `resume:resume_card_viewed` in days 1–7 after activation | Habit forming. |
| 5. Upgrade intent | `monetization:upgrade_clicked` | PLG monetization signal. |
| 6. Paid | `monetization:tier_switched` (to `cloud`) → `checkout_completed` | Conversion / revenue. |

Conversion window: 7 days steps 1–4, 30 days steps 5–6. Break funnel down by `client_surface`
and `setup_path`.

### 4b. Cohort & retention views

- **Weekly retention curve (NSM-anchored):** PostHog Retention insight, "first event" =
  activation, "returning event" = `resume:resume_card_viewed` (restoring). Report W1/W2/W4/W8.
  *This is the operating chart for the North Star.*
- **Activated-vs-not validation cohort:** two PostHog cohorts — completed activation loop vs
  capture-only — overlaid on the retention curve to prove activation predicts retention (the
  PostHog validation step). If curves don't separate, the activation definition is wrong.
- **Tier-conversion cohort:** users who fired `upgrade_clicked`, tracked to `tier_switched`,
  segmented by `prompt_reason` to learn which value prop (sync / cross-repo) drives upgrades.
- **Weekly signup cohorts:** new-install cohorts by ISO week to read launch-day vs steady-state
  and watch whether activation% holds as volume scales (cohort-over-aggregate discipline,
  [Stackmatix PLG funnel](https://www.stackmatix.com/blog/plg-funnel-metrics)).

### 4c. Launch dashboard tiles (PostHog dashboard)

1. **North Star — WCRR**, weekly trend + 4-week rolling avg.
2. NSM inputs: captures/active-user/wk, coverage mix (stacked %), median time-to-first-resume.
3. Acquisition→Revenue funnel (4a) with step conversion %.
4. NSM-anchored retention curve (4b) with the activated-vs-not overlay.
5. Activation rate (24h and 7-day) vs the 25%/40% targets.
6. Free→cloud conversion % and MRR (ties to CAC/payback in §5; MRR via [#1aae84be]).

---

## 5. Launch-success thresholds (go/no-go)

Graded against the KB benchmarks [#2ce52b97]: indie launch-day **100–500 signups**, median
**847 month-1 users**, **CAC $127**, month-3 retention **34%**, break-even **8.2 months**.
Cross-checked against external benchmarks for activation (20–40% leading PLG,
[Userpilot](https://userpilot.com/blog/user-activation-rate-benchmark-report-2024/)), freemium
conversion (~5–6% avg, [Pulseahead](https://www.pulseahead.com/blog/trial-to-paid-conversion-benchmarks-in-saas)),
and week-1 retention (top-quartile ≈ 7%+ D7 / strong PLG ≈ 30% by Andrew Chen's rule,
[Lovable](https://lovable.dev/guides/what-is-a-good-retention-rate-for-an-app)).

| Metric | NO-GO (below) | GO (meets) | STRONG (beats) | Benchmark basis |
|---|---|---|---|---|
| Launch-day signups (installs) | < 100 | 100–500 | > 500 | KB indie launch-day range [#2ce52b97] |
| Month-1 users | < 400 | ≥ 847 | > 1,200 | KB median 847 [#2ce52b97] |
| Activation rate (7-day, install→restoring-resume) | < 20% | ≥ 25% | ≥ 40% | leading-PLG 20–40% ([Userpilot](https://userpilot.com/blog/user-activation-rate-benchmark-report-2024/)) |
| TTV to activation (median) | > 24 h | ≤ 24 h | ≤ 1 h | top-quartile 24h activation ([Userpilot](https://userpilot.com/blog/user-activation-rate-benchmark-report-2024/)) |
| Week-1 NSM retention (activated cohort) | < 25% | ≥ 34% | ≥ 45% | KB month-3 retention 34% used as W1 floor [#2ce52b97]; PLG-strong ≈ 30%+ |
| Free→cloud conversion (90-day) | < 3% | ≥ 5% | ≥ 8% | freemium avg ~5.6%, top 6–8% ([Pulseahead](https://www.pulseahead.com/blog/trial-to-paid-conversion-benchmarks-in-saas)) |
| CAC (paid acquisition, if run) | > $127 | ≤ $127 | ≤ $90 | KB CAC $127 [#2ce52b97] |
| Payback / break-even | > 8.2 mo | ≤ 8.2 mo | ≤ 6 mo | KB break-even 8.2 mo [#2ce52b97] |

**Go/no-go decision rule (read at launch + 4 weeks):**
- **GO to scale spend** only if *all* of: month-1 users ≥ 847, activation ≥ 25%, week-1 NSM
  retention ≥ 34%. (Don't pour acquisition into a leaky funnel — activation + retention gate
  spend.)
- **NO-GO / fix-first** if activation < 20% **or** week-1 retention < 25%, regardless of signup
  volume — the loop isn't delivering value; fix capture→resume quality before marketing.
- **Conversion is a month-2+ gate, not launch-day:** free→cloud ≥ 5% is required before
  treating cloud monetization as validated; below 3% means the paid value props
  (sync/cross-repo, still FUTURE per CLAUDE.md) aren't compelling yet — keep iterating on the
  free loop and `prompt_reason` mix rather than discounting.

---

## Tooling decision

**PostHog** is the product-analytics system of record (already the KB-endorsed choice for
analytics + the key-event list [#7648d691]; gives funnels, retention cohorts, and path analysis
in one tool — [Userpilot PostHog review](https://userpilot.com/blog/posthog-analytics/)).
MRR/revenue reconciliation rides on the existing Stripe/Paddle-style stack already catalogued in
the KB [#1aae84be]. Error tracking (Sentry) stays separate per [#7648d691] and is out of scope
for this workstream.

## Sources

KB findings: `[#7648d691]` analytics/error stack + key events, `[#2ce52b97]` early-stage SaaS
KPIs + launch benchmarks, `[#1aae84be]` MRR/analytics tooling, `[#1665bb5c]` pre-launch
validation discipline.

Web: [Amplitude North Star Framework](https://amplitude.com/books/north-star/about-north-star-framework),
[Amplitude good vs bad NSM](https://amplitude.com/blog/good-bad-north-star-metric),
[Appcues aha-moment guide](https://www.appcues.com/blog/aha-moment-guide),
[Statsig aha-moment metrics](https://www.statsig.com/perspectives/aha-moment-saas-metrics),
[Userpilot aha guide](https://userpilot.com/blog/aha-moment/),
[Userpilot activation benchmark 2024](https://userpilot.com/blog/user-activation-rate-benchmark-report-2024/),
[Userpilot SaaS conversion benchmarks](https://userpilot.com/blog/saas-average-conversion-rate/),
[Pulseahead trial-to-paid benchmarks](https://www.pulseahead.com/blog/trial-to-paid-conversion-benchmarks-in-saas),
[PostHog naming conventions](https://posthog.com/questions/best-practices-naming-convention-for-event-names-and-properties),
[PostHog schema management](https://posthog.com/docs/product-analytics/schema-management),
[PostHog AARRR funnel](https://posthog.com/product-engineers/aarrr-pirate-funnel),
[PostHog funnels docs](https://posthog.com/docs/product-analytics/funnels),
[Stackmatix PLG funnel metrics](https://www.stackmatix.com/blog/plg-funnel-metrics),
[Lovable retention benchmarks](https://lovable.dev/guides/what-is-a-good-retention-rate-for-an-app).
