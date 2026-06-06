# WS3 — Pricing & Packaging (br8n)

Status: draft for launch. Owner: solo founder.
Last updated: 2026-05-29.

This is the pricing & packaging workstream for br8n — a context-capture-and-resume
engine for developers (captures workspace state on interruption, replays a 30-second
resume card). The product already ships with a structural free/paid split:

- **FREE local tier** — SQLite + `sqlite-vec`, loopback-only, no auth, data never
  leaves the machine.
- **PAID cloud tier** — Supabase + pgvector behind the existing GoTrue login.

The documented (designed, mostly-unbuilt) paid value props are: cross-machine **SYNC**,
cross-repo **SEARCH**, team **SHARING**, and **MANAGED KEYS**. br8n is distributed
as a Claude Code plugin + a VS Code extension.

Grounding: this doc builds on the br8n `dev` KB. Cited finding ids inline are
`f21b3893` (developer buying behavior), `b04f6d13` (Lemon Squeezy vs Stripe fees),
`1aae84be` (SaaS analytics tooling), `d573d341` (embedded-payments CAGR),
`c7e9c440` (launch tooling). KB coverage on pricing specifics was `sparse`, so the
numbers below are sourced from external benchmarks cited inline.

---

## 1. Recommended packaging model

**Recommendation: Freemium with a value-add cloud tier — NOT open-core, NOT
usage-based.** br8n's architecture already *is* the freemium boundary: the free
tier is a complete, self-contained local product (SQLite, loopback, no auth), and
the paid tier is a hosted superset (Supabase + pgvector) that adds capabilities the
local tier physically cannot have (sync, cross-repo, sharing, managed keys). The
storage boundary and the pricing boundary are the same line. This is the cleanest
possible freemium: there is no crippled free product, only a single-machine one.

Why not the alternatives:

- **Not open-core.** Open-core gates the *source*: a free OSS core plus closed
  commercial modules. br8n's split is by *hosting/identity*, not by withholding
  code, and a solo founder gets little from maintaining a formal community-edition
  boundary on day one. Open-core's named upside is faster acquisition (~30% per
  OpenCore Summit data, via [getmonetizely](https://www.getmonetizely.com/articles/how-to-find-the-right-pricing-model-to-drive-developer-tool-adoption-in-competitive-markets)),
  but br8n captures that same bottom-up adoption through a genuinely free,
  fully-functional local tier — without the maintenance tax. (Keeping the
  *client* code public/source-available is still worth doing for trust; that is a
  distribution choice, not the monetization model.)
- **Not usage-based.** Usage metering (snapshots captured, explorations run,
  tokens) aligns cost to value but creates bill anxiety and revenue
  unpredictability — and "surprising overage charges destroy trust faster than any
  competitor" for technical buyers
  ([getmonetizely](https://www.getmonetizely.com/articles/how-to-price-developer-tools-feature-gating-and-tier-strategies-for-code-quality-platforms-74f84)).
  Developers want to predict and monitor the meter. A flat seat price for the cloud
  tier is far more legible. (There is one bounded exception — see managed-keys
  metering in §2.)

This matches how developers actually buy: they are skeptical of hype, evaluate
hands-on, and *require* instant self-service access and a free tier before they will
consider paying (`f21b3893`). A complete free local tier is the entry ticket; the
cloud tier is the upsell once the tool is a habit.

---

## 2. Exact feature gating (free forever vs paid)

Principle from the research: **gate power, not access — never gate what the user
needs to reach the aha moment**
([getmonetizely](https://www.getmonetizely.com/faqs/we-re-planning-a-freemium-model---which-features-or-usage-limits-should-the-free-tier-include-to-provide-enough-value-but-still-encourage-users-to-upgrade-to-paid-plans),
[demogo](https://demogo.com/2025/11/24/feature-gating-in-saas-practical-models-for-freemium-conversion-with-examples/)).
br8n's aha moment is the first 30-second resume card. That stays free forever.

### FREE forever (local tier)

The entire single-machine loop, with no caps that touch the core job:

- Unlimited capture (`br8n_capture`) and resume (`br8n_resume`) on this machine.
- Full preamble + coverage banding, synopsis, and the resume-card webview.
- Local gap-fill explore (`br8n_explore`) **using the user's own API key** — the
  engine runs locally; the user pays their own LLM/search bill (BYO key).
- All current repos/branches stored locally in `~/.br8n/brain.db`.
- VS Code extension + Claude Code plugin, full feature set, single device.

No artificial snapshot/repo limit on the free tier. The free tier's *only* limit is
the one the architecture already imposes: **one machine, no account, no sharing**.
That single limit is the entire upgrade thesis (this mirrors Slack gating message
*history* not messaging — the gate is a scaling pain, not a feature wall:
[demogo](https://demogo.com/2025/11/24/feature-gating-in-saas-practical-models-for-freemium-conversion-with-examples/)).

### PAID (cloud tier) — maps 1:1 to the four documented value props

| Value prop | What it unlocks (the gate) | Tier |
|---|---|---|
| **SYNC** (cross-machine) | The same repo+branch resume cards on laptop + desktop + new machine; account-backed, survives a wiped disk. The signature "I sat down at a different machine and my context was there" moment. | Pro |
| **SEARCH** (cross-repo) | Tap/search across *all* your repos+branches at once instead of one local DB per machine — "where did I leave the auth refactor, across any project?" | Pro |
| **SHARING** (team) | Share a resume card / KB with a teammate; org-scoped KBs; the onboarding-handoff use case. | Team |
| **MANAGED KEYS** | br8n-managed LLM/search keys so explore "just works" with no BYO-key setup; metered fairly inside the seat with a generous monthly allowance, hard overage cap (no surprise bills). | Team (Pro can opt in) |

Administrative, collaboration, and security/identity features are the natural paid
gates — never the core capture/resume job
([demogo](https://demogo.com/2025/06/25/feature-gating-strategies-for-your-saas-freemium-model-to-boost-conversions/)).
SYNC and cross-repo SEARCH are the individual-developer upgrades (they require an
account + hosted store, which the local tier cannot provide); SHARING and MANAGED
KEYS are the team upgrades.

Note: SYNC, cross-repo SEARCH, SHARING, and MANAGED KEYS are *designed but mostly
unbuilt*. The pricing page must only sell what ships. Recommended launch posture:
ship **SYNC + cross-repo SEARCH first** (the Pro tier is the v1 paid product);
label SHARING + MANAGED KEYS as "coming soon" on the Team tier, or hold the Team
tier off the page entirely until built.

---

## 3. Price points

Benchmark set (named comparables, individual-developer plans):

| Tool | Individual plan | Source |
|---|---|---|
| GitHub Copilot Pro | **$10/mo**, $100/yr | [github.com/features/copilot/plans](https://github.com/features/copilot/plans) |
| Cursor Pro | **$20/mo** | [getdx](https://getdx.com/blog/ai-coding-assistant-pricing/) |
| Tabnine Pro | **$12/mo** | [getdx](https://getdx.com/blog/ai-coding-assistant-pricing/) |
| Windsurf Pro | **$15/mo** | [getdx](https://getdx.com/blog/ai-coding-assistant-pricing/) |
| Raycast Pro | **$8/mo** ($8/user/mo annual), Teams $12/user/mo | [raycast.com/pricing](https://www.raycast.com/pricing) |
| Obsidian Sync | **$4–5/mo** ($4/mo annual) — the closest analog (sync add-on on a free local app) | [obsidian.md/pricing](https://obsidian.md/pricing) |

br8n's closest structural analog is **Obsidian**: a free, local-first app whose
paid product is sync ($4–5/mo). That anchors the floor. But br8n also delivers
active developer-workflow value (resume cards, explore), closer to Copilot/Tabnine
($10–12). Positioning br8n between Obsidian Sync and Copilot Pro is correct: more
than a pure sync add-on, less than a full AI coding assistant.

**Recommended price points:**

| Tier | Monthly | Annual (per mo) | Annual total | Rationale |
|---|---|---|---|---|
| **Free** | $0 | $0 | $0 | Full local product, single machine, BYO key. The acquisition engine. |
| **Pro** (individual) | **$8/mo** | **$6/mo** | **$72/yr** | Sync + cross-repo search. Anchored to Obsidian Sync ($4–5) on the low side and Copilot Pro ($10) on the high side; $8 reads as "obviously worth it" to a developer who has felt the context-rebuild tax, and undercuts Copilot to lower the impulse-buy bar. ~25% annual discount matches Obsidian/Raycast convention. |
| **Team** | **$12/user/mo** | **$10/user/mo** | **$120/user/yr** | Sharing + managed keys + admin. Matches Raycast Teams ($12/user/mo) exactly — a known-good per-seat point for developer-productivity tools. Managed keys justify the premium over Pro (br8n now carries some LLM/search COGS). |

Rationale notes:
- $8 Pro deliberately sits **below** the $10–20 AI-coding-assistant band: br8n is a
  companion, not a replacement for Copilot/Cursor, and a developer will already be
  paying for one of those. Pricing under $10 keeps br8n an easy *additive* purchase,
  not a competing budget line.
- A single Pro tier (not three) keeps the page legible for a solo founder and avoids
  decision paralysis. Add the $200-class "Ultra" tier (cf. Cursor Ultra) only if
  managed-keys heavy users demand it later.
- On payments: use a Merchant-of-Record (Lemon Squeezy / Paddle) over raw Stripe.
  At $10k MRR the MoR premium is ~$230/mo over Stripe (`b04f6d13`) — cheap insurance
  for a solo founder to offload global sales-tax/VAT compliance. Use ProfitWell/Paddle
  free metrics for MRR/churn tracking (`1aae84be`).

---

## 4. In-product upgrade triggers

Surface the upgrade prompt **only at the moment the user is actively hitting the
limitation that the paid feature removes** — high-signal, contextual, never a nag
([demogo](https://demogo.com/2025/11/24/feature-gating-in-saas-practical-models-for-freemium-conversion-with-examples/),
[a16z](https://a16z.com/how-to-optimize-your-free-tier-freemium/)). Concrete moments
for br8n:

1. **New machine / second device detected** — user runs br8n on a machine with an
   empty local DB but the same git remote they have history for elsewhere. The single
   highest-intent moment: "Your resume cards live on another machine. Sync them here
   with Pro." This is the SYNC trigger and the strongest one.
2. **Cross-repo search miss** — user runs `/br8n:search` or resume and the answer is
   "in another repo's local KB." Prompt: "Found nothing in *this* repo. Pro searches
   across all your repos — including the auth-refactor work in `service-x`."
3. **Disk-wipe / reinstall recovery** — fresh install, no local DB. "Restore your
   captured context from the cloud with Pro." (SYNC framed as backup/insurance.)
4. **Resume card opened on Nth consecutive day** — sustained engagement (10+ days,
   per the high-signal list) means the habit is formed; surface a one-time "you've
   resumed N times this week — keep your context everywhere with Pro."
5. **Teammate-share intent** — user copies a resume card / mentions a handoff, or a
   second teammate opens the same repo. Prompt the Team tier (sharing). [Gated behind
   Team shipping.]
6. **Explore BYO-key friction** — user's own key is missing/rate-limited/errors during
   `br8n_explore`. "Skip key setup — let br8n manage it on Team." [Gated behind
   managed-keys shipping.]

Rules: each trigger fires at most once per ~30 days; every prompt states the gate
up-front and is dismissable; never interrupt the actual capture/resume action
(the aha moment must always complete free).

---

## 5. Pricing-page spec

### Tiers (columns)

`Free` · `Pro` ($8/mo, $6/mo annual) · `Team` ($12/user/mo, $10 annual — mark
SHARING/MANAGED-KEYS rows "coming soon" until shipped).

### Feature-matrix rows

| Feature | Free | Pro | Team |
|---|---|---|---|
| Capture & 30-sec resume card | ✓ | ✓ | ✓ |
| VS Code extension + Claude Code plugin | ✓ | ✓ | ✓ |
| Preamble + coverage banding + synopsis | ✓ | ✓ | ✓ |
| Local gap-fill explore (BYO API key) | ✓ | ✓ | ✓ |
| Repos / branches stored | Unlimited (local) | Unlimited | Unlimited |
| Devices | 1 (this machine) | Unlimited (**Sync**) | Unlimited |
| Cross-repo search | — | ✓ | ✓ |
| Cloud backup / restore | — | ✓ | ✓ |
| Data location | Your machine only | Your machine + your cloud account | Org cloud |
| Team / shared KBs | — | — | ✓ *(soon)* |
| Managed LLM + search keys | — | opt-in *(soon)* | ✓ *(soon)* |
| Admin controls | — | — | ✓ *(soon)* |
| Support | Community / GitHub | Email | Priority |

Lead the page with the honest one-liner: **"Free, forever, on your machine. Pay only
when you want your context to follow you."**

### FAQ items

1. **Is the free tier time-limited or a trial?** No. Free is forever and fully
   functional on one machine. There is no snapshot or repo cap.
2. **Where is my data on the free tier?** Only on your machine (`~/.br8n/brain.db`),
   loopback-only, no account, never uploaded. (Directly answers the privacy-first
   developer buyer, `f21b3893`.)
3. **What exactly does Pro add?** Sync across machines + search across all your repos,
   plus cloud backup. Your data moves to your br8n cloud account.
4. **Do I need an API key?** On Free/Pro, explore uses your own LLM/search key (BYO).
   Team's managed keys remove that setup (metered with a generous allowance and a hard
   cap — no surprise bills).
5. **How does Team billing work?** Per active user per month, billed via our
   Merchant-of-Record (handles VAT/sales tax). Annual saves ~17–25%.
6. **Can I self-host the cloud tier?** The cloud tier is hosted Supabase; self-host
   guidance is on the roadmap. The free local tier is already fully self-contained.
7. **How do I downgrade / what happens to my data?** Downgrading to Free keeps your
   local DB intact; cloud data is exportable. No lock-in.

### Conversion target

- **Developer-tool freemium converts at ~1–3%** free→paid
  ([daydream](https://www.withdaydream.com/library/insights/freemium-conversion-rate),
  [getmonetizely](https://www.getmonetizely.com/articles/freemium-conversion-rate-the-key-metric-that-drives-saas-growth-3588c)).
  Open-source / mass-adoption dev tools can run lower, 0.3–1%
  ([getmonetizely](https://www.getmonetizely.com/articles/whats-the-optimal-conversion-rate-from-free-to-paid-in-open-source-saas)).
  High-intent dev/security tools with strong buyer intent reach 8–12%
  ([demogo](https://demogo.com/2025/06/25/feature-gating-strategies-for-your-saas-freemium-model-to-boost-conversions/)).
- **Realistic launch target: 2–3% free→paid in year one**, with a stretch toward 5%+
  as SYNC/SEARCH mature and the new-machine trigger (the single strongest moment)
  is well-instrumented. Setting the bar at the upper-middle of the dev-tool band (not
  the 8–12% high-intent ceiling) is honest for a brand-new, low-friction free tier.
- **Leading indicator to instrument**: time-to-first-resume-card. The API-call analog
  shows users who reach first value <10 min convert at 3–4×
  ([getmonetizely](https://www.getmonetizely.com/articles/what-onboarding-flow-converts-free-developers-to-paid-plans-a-complete-guide-for-saas-dev-tools)) —
  so the launch KPI is "% of installs that capture+resume within the first session."

---

## Sources

KB findings (br8n `dev`): `f21b3893`, `b04f6d13`, `1aae84be`, `d573d341`, `c7e9c440`.

Web:
- getmonetizely — dev-tool pricing & feature gating: https://www.getmonetizely.com/articles/how-to-price-developer-tools-feature-gating-and-tier-strategies-for-code-quality-platforms-74f84
- getmonetizely — pricing model for adoption (open-core ~30% acquisition): https://www.getmonetizely.com/articles/how-to-find-the-right-pricing-model-to-drive-developer-tool-adoption-in-competitive-markets
- getmonetizely — freemium conversion rate metric: https://www.getmonetizely.com/articles/freemium-conversion-rate-the-key-metric-that-drives-saas-growth-3588c
- getmonetizely — open-source SaaS conversion: https://www.getmonetizely.com/articles/whats-the-optimal-conversion-rate-from-free-to-paid-in-open-source-saas
- getmonetizely — onboarding flow / TTFAC: https://www.getmonetizely.com/articles/what-onboarding-flow-converts-free-developers-to-paid-plans-a-complete-guide-for-saas-dev-tools
- getmonetizely FAQ — free tier feature/limit design: https://www.getmonetizely.com/faqs/we-re-planning-a-freemium-model---which-features-or-usage-limits-should-the-free-tier-include-to-provide-enough-value-but-still-encourage-users-to-upgrade-to-paid-plans
- daydream — freemium conversion benchmarks: https://www.withdaydream.com/library/insights/freemium-conversion-rate
- demogo — feature gating models (Slack example, upgrade triggers, 8–12% dev/security): https://demogo.com/2025/11/24/feature-gating-in-saas-practical-models-for-freemium-conversion-with-examples/
- demogo — feature gating strategies: https://demogo.com/2025/06/25/feature-gating-strategies-for-your-saas-freemium-model-to-boost-conversions/
- a16z — optimizing the free tier: https://a16z.com/how-to-optimize-your-free-tier-freemium/
- getdx — AI coding assistant pricing comparison: https://getdx.com/blog/ai-coding-assistant-pricing/
- GitHub Copilot plans: https://github.com/features/copilot/plans
- Raycast pricing: https://www.raycast.com/pricing
- Obsidian pricing (Sync $4–5/mo): https://obsidian.md/pricing
