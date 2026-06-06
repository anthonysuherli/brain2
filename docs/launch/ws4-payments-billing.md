# WS4 — Payments & Billing Infrastructure

**Workstream:** Launch / Monetization
**Product:** br8n (freemium developer tool — free local SQLite tier, paid Supabase cloud tier)
**Seller:** Solo founder, selling globally (digital subscription, no physical goods)
**Date:** 2026-05-29
**Status:** Draft for launch review

---

## 0. TL;DR

Use a **Merchant of Record (MoR) — Paddle or Lemon Squeezy — at launch**, not raw
Stripe. As a solo founder selling a digital subscription worldwide, the MoR's ~1.5–2 pt
fee premium buys away the single biggest non-product time-sink: registering for,
collecting, filing, and remitting VAT/GST/sales tax across 100+ jurisdictions, with the
**legal liability** sitting on the MoR rather than on me. The KB already reached this
conclusion at $10k MRR — "the extra fee is potentially worth every dollar for solo
developers to avoid tax compliance headaches" [#b04f6d13]. This doc confirms it with a
current fee model and specs the full subscription/billing implementation against
br8n's cloud-tier `org_id` tenancy.

---

## 1. Provider Recommendation — Stripe vs Merchant of Record

### 1.1 The core distinction (why this is not just a fee question)

A **payment processor** (Stripe) moves the money; **you** are the seller of record, so
**you** are legally responsible for tax registration, collection, filing, and
remittance everywhere you have nexus. Stripe Tax *calculates and collects* but
explicitly does **not** file or remit in most jurisdictions — "you remain responsible
for filing and remittance" — so you'd still need Avalara/Anrok or Stripe's paid filing
add-on, plus the registrations themselves
([Fungies](https://fungies.io/stripe-tax-limitations-understanding-the-difference-from-the-merchant-of-record-model/),
[Stripe Tax](https://stripe.com/tax)).

A **Merchant of Record** (Paddle, Lemon Squeezy) legally *resells* your software:
the transaction is between the customer and the MoR, who then "buys" it from you. The
MoR "handles complete tax compliance — calculating taxes, collecting them, filing
returns, and remitting payments to tax authorities worldwide," and carries the liability
([TaxJar](https://www.taxjar.com/blog/what-is-a-merchant-of-record-mor),
[fintechspecs](https://fintechspecs.com/blog/stripe-vs-paddle-vs-lemon-squeezy-vs-polar-merchant-of-record-b2b-saas/)).

For a **solo founder selling globally**, that liability transfer is the product. The
oft-cited estimate: going raw-Stripe to "save" money costs a micro-SaaS "at least 10
hours a year dealing with sales tax compliance" — and that ignores registration cost and
audit risk
([F³ Fund It](https://f3fundit.com/stripe-vs-paddle-vs-lemon-squeezy-micro-saas-2026/)).

> Note on Stripe's own MoR: in 2026 Stripe launched **Stripe Managed Payments**, an MoR
> covering ~75 countries / 35 product categories, expected to add ~3.5% on top of
> standard fees, and you still owe compliance in unsupported territories
> ([Paddle](https://www.paddle.com/resources/stripe-managed-payments),
> [Dodo](https://dodopayments.com/blogs/is-stripe-a-merchant-of-record)). It is newer,
> pricier than the headline implies, and not yet a reason to pick the Stripe stack over a
> mature MoR for a solo launch.

### 1.2 Current fee structures (verified May 2026)

| Provider | Model | Headline fee | Tax handling |
|---|---|---|---|
| **Stripe (raw)** | Payment processor | 2.9% + $0.30 (US); **+1.5%** intl card; **+1%** currency conversion → ~4.4–5.4% + $0.30 on intl | You register/file/remit. Stripe Tax = **+0.5%** to *calculate*, not remit |
| **Stripe Billing add-on** | Recurring engine | **+0.7%** of billing volume (covers Smart Retries, dunning, schedules) | — |
| **Paddle** | Merchant of Record | **5% + $0.50** | MoR remits VAT/GST/sales tax in 200+ jurisdictions |
| **Lemon Squeezy** | Merchant of Record | **5% + $0.50** | MoR remits in 200+ jurisdictions |

Sources: Stripe intl surcharges [Dodo calculator](https://dodopayments.com/blogs/stripe-fees-calculator);
Stripe Billing 0.7% flat / Stripe Tax 0.5% [Flexprice](https://flexprice.io/blog/stripe-pricing-breakdown-2026),
[Stripe Billing pricing](https://stripe.com/billing/pricing);
MoR 5% + $0.50 [globalsolo](https://www.globalsolo.global/blog/stripe-vs-paddle-vs-lemon-squeezy-2026),
[DEV](https://dev.to/jettfu/stripe-vs-paddle-vs-lemon-squeezy-fee-comparison-2026-2c77).
*Pricing changes often — re-verify against the providers' own pages before signing.*

### 1.3 Fee model at $1k / $5k / $10k MRR

Assumptions for br8n: digital subscription, **~60% of revenue from international
buyers** (developer tool, global audience), average sub ~$15/mo so per-transaction $0.30/$0.50
fixed fees matter. Stripe "full stack" = base processing + intl/FX blend + Billing 0.7%
+ Stripe Tax 0.5% (calculation only — **filing/registration not included**). MoR =
5% + $0.50 all-in (tax fully handled).

Blended Stripe effective rate ≈ (0.4 × 2.9%) + (0.6 × ~4.9% intl+FX) + 0.7% Billing +
0.5% Tax ≈ **~5.4% + ~$0.30/txn**, *plus* off-platform registration/filing cost & time.

| MRR | Txns/mo (~$15 ASP) | **Stripe full stack** (proc+intl+Billing+Tax, calc only) | **MoR (Paddle / Lemon Squeezy)** 5% + $0.50 | MoR premium | What the premium buys |
|---|---|---|---|---|---|
| **$1,000** | ~67 | ~$54 + $20 fixed ≈ **$74/mo** + your tax labor | ~$50 + $33.50 ≈ **$83.50/mo** | ~$10/mo | All VAT/GST registration, filing, remittance + liability removed |
| **$5,000** | ~333 | ~$270 + $100 ≈ **$370/mo** + tax labor | ~$250 + $166.50 ≈ **$416.50/mo** | ~$47/mo | Same, at scale where multi-jurisdiction filing gets real |
| **$10,000** | ~667 | ~$540 + $200 ≈ **~$740/mo**¹ | ~$500 + $333.50 ≈ **~$833/mo** | ~$93/mo | KB benchmark: MoR ≈ $550 vs Stripe ≈ $320 *pre-Tax & pre-filing* [#b04f6d13] |

¹ The KB's $320 figure [#b04f6d13] is Stripe's **pre-Stripe-Tax, US-weighted** base.
Once intl surcharges, Billing 0.7%, and Tax 0.5% stack — and especially once you add the
real cost of registering and filing VAT in the EU/UK plus US economic-nexus states — the
gap narrows to roughly the small-MRR fixed-fee delta shown above, and the **labor +
liability** swing decisively favors MoR for a solo operator.

### 1.4 Recommendation

**Launch on a Merchant of Record. Pick Lemon Squeezy** (Stripe-owned since 2024; clean
API/checkout, SaaS-native subscriptions, strong indie docs) **with Paddle as the
fallback** (heavier B2B/invoicing, broader enterprise features). Both are 5% + $0.50,
so the choice is DX/ecosystem, not price
([appstackbuilder](https://appstackbuilder.com/blog/stripe-vs-lemon-squeezy-vs-paddle)).

Migrate to raw Stripe + Stripe Tax/Anrok only **after** ~$25–50k MRR, when the saved
percentage points fund a part-time finance/ops contractor to own compliance — a
deliberate later decision, not a launch one.

---

## 2. Subscription Implementation Spec

> Terminology below uses Stripe/MoR-neutral concepts; the MoR (Lemon Squeezy/Paddle)
> exposes the same primitives (products, variants/prices, subscriptions, webhooks).

### 2.1 Plans

| Plan | Price | Tier mechanism | Notes |
|---|---|---|---|
| **Local (Free)** | $0 | `BR8N_BACKEND=local`, SQLite, no auth, loopback | **No billing object at all.** Never touches the MoR. `org_id="local"` synthetic. |
| **Cloud (Paid)** | ~$12–15/mo or ~$120–150/yr | `BR8N_BACKEND=cloud`, Supabase + GoTrue + RLS | Single paid plan at launch. Annual ~2 months free to pull cash forward + cut churn. |
| **(Future) Team** | per-seat | Same Supabase `org_id`, multiple members | Deferred — matches CLAUDE.md "team sharing = FUTURE". |

Keep it **one paid plan** at launch. Plan sprawl is premature for a solo founder.

### 2.2 Trial vs Freemium — use both (hybrid)

br8n is *already freemium*: the free local tier is the top of funnel and needs no
billing. Layer a **14-day free trial of the Cloud tier on top**, with **card required**
to start the trial:

- Hybrid freemium + premium-feature trial is the fastest-growing PLG pattern (used by
  ~65% of PLG SaaS in 2026); trials convert in 12–18 days vs 90–180 days for pure
  freemium ([Chargebee](https://www.chargebee.com/resources/guides/subscription-pricing-trial-strategy/saas-trial-plans/)).
- **Collect the card up front** — trials with a card on file convert **2–3×** better
  ([Chargebee](https://www.chargebee.com/resources/guides/subscription-pricing-trial-strategy/saas-trial-plans/)).
- **14 days** is the B2B sweet spot — enough to evaluate, short enough to create urgency
  ([Chargebee](https://www.chargebee.com/resources/guides/subscription-pricing-trial-strategy/saas-trial-plans/)).

So: free local forever (no card) → trial of cloud (card on file, 14 days) → paid cloud.

### 2.3 Proration

- On **upgrade** (e.g. monthly→annual, or future free-cloud→team): prorate immediately,
  charge the difference now.
- On **downgrade**: apply at **period end** (credit/no immediate charge) to avoid refund
  complexity and confusing invoices.
- **Watch the failure mode:** a technically-correct proration line can still produce a
  confusing invoice and a support ticket
  ([OpenMedium](https://www.openmedium.biz/technology-consulting/how-to-choose-a-saas-billing-platform-that-wont-break-as-you-scale/)).
  Show a plain-language "you'll be charged $X today, then $Y on [date]" preview in the UI
  before confirming.

### 2.4 Cancel / Downgrade

- **Cancel** → set `cancel_at_period_end = true`. User keeps cloud access until period
  end; on expiry, downgrade the `org` to local-equivalent (revoke cloud RLS scope, keep
  their data read-exportable for a grace window).
- **Downgrade** (paid → free) → flip `BR8N_BACKEND` entitlement to `local`; data stays
  in their local SQLite path. No data destruction on cancel — offer export.
- Offer an **annual→monthly** path and a pause option to deflect outright cancels.

### 2.5 Webhook events to handle

The webhook handler is the source of truth for entitlement — never grant access from the
client redirect alone. **Verify the signature**, make handlers **idempotent** (dedupe on
event id), and return 2xx fast
([Stripe webhooks](https://docs.stripe.com/billing/subscriptions/webhooks)).

| Event (Stripe naming; MoR has equivalents) | br8n action |
|---|---|
| `checkout.session.completed` / order created | Provision: create/link Supabase `org`, set entitlement = cloud, store `customer_id` + `subscription_id` |
| `customer.subscription.created` | Mark org `status=trialing` or `active`; record `current_period_end` |
| `customer.subscription.updated` | Reconcile plan/price changes, trial→active, proration; update entitlement |
| `customer.subscription.trial_will_end` (≈3 days out) | Send "trial ending, card will be charged" email |
| `invoice.paid` / `invoice.payment_succeeded` | Extend `current_period_end`; ensure org stays `active` |
| `invoice.payment_failed` | Enter dunning: mark `past_due`, fire dunning email, keep access during retry window ([Stripe](https://docs.stripe.com/billing/subscriptions/webhooks)) |
| `customer.subscription.deleted` | Subscription ended (cancel or terminal dunning failure) → downgrade org to local entitlement |
| `customer.subscription.paused` | Suspend cloud access without deleting data (if pause offered) |

### 2.6 Billing identity → cloud-tier `org_id`

This is the load-bearing mapping. br8n's engine never touches a storage client
directly — it calls `get_store()`, and cloud carries a per-request JWT for Supabase RLS
(per CLAUDE.md). Billing must resolve to the **same `org_id`** that RLS scopes on.

```
MoR/Stripe customer  ──1:1──▶  Supabase org (org_id)  ──▶  RLS scope on findings/KBs
        │                              │
   customer_id,                  entitlement = cloud|local,
 subscription_id,               plan, status (trialing/active/past_due/canceled),
   stored on org                current_period_end
```

- On first paid checkout, create (or look up) the Supabase `org`, then **store
  `billing_customer_id` and `subscription_id` as columns on that org row.** The webhook
  handler keys off `customer_id` → `org_id`.
- Entitlement check on every cloud request: load org by JWT → org_id, read
  `entitlement` + `status`. `active`/`trialing` ⇒ serve; `past_due` ⇒ serve + nudge;
  `canceled`/expired ⇒ 402 / route to local.
- **Free local tier:** synthetic `org_id="local"`, no auth, no billing object — it must
  never call the billing system. Keep the billing/entitlement check entirely inside the
  `active_backend()=="cloud"` branch so the local tier stays creds-less and offline.
- Add a small `billing_events` audit table (event id, type, org_id, raw payload) for
  idempotency + debugging.

---

## 3. Dunning & Involuntary-Churn Recovery

Involuntary churn (failed payments, expired cards) is recoverable revenue. The KB's own
benchmark and current sources agree on the configuration and the recovery envelope.

### 3.1 Config

- **Smart retries:** ML-timed retries, **up to ~7 attempts over ~21 days** [#08a85dd6];
  the engine retries soft declines ("Do Not Honor") sooner and hard declines
  ("Invalid Card") later
  ([Stripe Smart Retries](https://docs.stripe.com/billing/revenue-recovery/smart-retries),
  [Kinde](https://www.kinde.com/learn/billing/churn/dunning-strategies-for-saas-email-flows-and-retry-logic/)).
  On a MoR, this is built-in; on Stripe it lives under **Billing → Revenue recovery →
  Retries**.
- **Card updater / account updater:** enable it — automatically refreshes expired/reissued
  card numbers; one of the highest-ROI toggles
  ([Kinde](https://www.kinde.com/learn/billing/churn/dunning-strategies-for-saas-email-flows-and-retry-logic/)).
- **Dunning email sequence** (customer-friendly, not aggressive — goal is resolve+retain):
  1. Day 0 — "payment failed, we'll retry, here's a 1-click update-card link"
  2. Day ~3 — reminder + retry notice
  3. Day ~7 — "access at risk" with urgency
  4. Day ~14/21 — final notice before cancellation
- **Access policy:** keep cloud access **on** during the retry window (don't punish a
  bounced card); downgrade to local only on terminal failure
  (`customer.subscription.deleted`).

### 3.2 Expected recovery

| Lever | Recovery |
|---|---|
| Smart retries | **20–40%** of failed payments [#08a85dd6] |
| + Dunning emails | **+10–20%** [#08a85dd6] |
| **Combined (retries + emails + card updater)** | **30–60%**, up to **60–70%** with card updater [#08a85dd6], [Kinde](https://www.kinde.com/learn/billing/churn/dunning-strategies-for-saas-email-flows-and-retry-logic/) |
| **MRR saved (involuntary churn reduction)** | **2–5% of MRR** [#08a85dd6] |

At $10k MRR, that 2–5% is **$200–500/mo recovered** — i.e. dunning alone roughly pays for
the MoR fee premium from §1.3.

---

## 4. Revenue Analytics Tooling

From the KB analytics finding [#1aae84be] plus current options:

| Tool | Fit for br8n | Verdict |
|---|---|---|
| **MoR built-in dashboard** (Lemon Squeezy / Paddle) | MRR, churn, revenue out of the box; **Paddle bundles ProfitWell Metrics free** (acquired 2022) [#1aae84be] | **Launch choice** — zero setup, free |
| **ProfitWell Metrics** | Free MRR/churn/LTV; works with Stripe too [#1aae84be] | **Add even on launch** — free, best free metrics layer |
| **Stripe Sigma** | SQL custom reporting *inside Stripe* — but we're on a MoR at launch, and it's paid + needs SQL [#1aae84be] | Skip until/unless on raw Stripe |
| **Chartsy** | 3rd-party layer over Stripe/Paddle; invoice-accurate MRR/ARR/churn/LTV/expansion [#1aae84be] | Optional later when expansion-MRR tracking matters |

**Recommendation:** lean on the **MoR dashboard + free ProfitWell Metrics** at launch
($0 added). Revisit Chartsy/Sigma only after migrating to raw Stripe or when cohort/
expansion analytics drive decisions.

---

## 5. Implementation Checklist

- [ ] Choose MoR: create **Lemon Squeezy** account (Paddle as fallback); verify identity/payout.
- [ ] Define **one paid Cloud product** + monthly and annual prices.
- [ ] Configure **14-day trial, card required** on the cloud subscription.
- [ ] Add columns to Supabase `org`: `billing_customer_id`, `subscription_id`, `plan`,
      `status`, `current_period_end`, `entitlement`.
- [ ] Add `billing_events` audit table (idempotency + debugging).
- [ ] Build webhook endpoint (`/v1/billing/webhook`): **signature verify**, **idempotent**,
      handle the §2.5 events, map `customer_id → org_id`.
- [ ] Implement entitlement gate inside the `active_backend()=="cloud"` path only;
      **local tier must never call billing**.
- [ ] Wire **checkout** (hosted MoR checkout) → on success link/create Supabase org.
- [ ] Implement **proration** (upgrade=immediate, downgrade=period-end) + UI charge preview.
- [ ] Implement **cancel** = `cancel_at_period_end`; downgrade to local on expiry; offer export.
- [ ] Configure **dunning**: smart retries (~7/21d), card updater on, 4-step email sequence.
- [ ] Enable **MoR dashboard + ProfitWell Metrics**.
- [ ] Tax: confirm MoR handles VAT/GST/sales-tax (it does as MoR) — no self-registration at launch.
- [ ] Secrets: store MoR API key + webhook secret server-side; never expose to local tier.

---

## 6. Test Plan

Use the MoR's **test/sandbox mode** and Stripe-style **test cards** for forced outcomes.
For each flow, assert: (a) the right webhook fires, (b) Supabase `org` row reflects
correct `status`/`entitlement`/`current_period_end`, (c) the engine's `get_store()` path
grants/denies cloud access accordingly.

| # | Flow | Steps | Expected |
|---|---|---|---|
| T1 | **Trial start** | Checkout with valid test card | `subscription.created` (trialing); org `status=trialing`, `entitlement=cloud`; cloud access granted; no charge yet |
| T2 | **Trial → paid** | Advance clock past 14d | `subscription.updated` (active) + `invoice.paid`; org `active`; card charged |
| T3 | **Upgrade** (monthly→annual) | Change plan mid-cycle | `subscription.updated`; **immediate prorated charge**; UI preview matched actual invoice |
| T4 | **Downgrade** (annual→monthly / paid→free) | Request downgrade | Change applied at **period end**; no immediate refund; access correct until then; on free, org→local entitlement, data retained |
| T5 | **Cancel** | Cancel subscription | `cancel_at_period_end=true`; access until period end; at expiry `subscription.deleted` → org downgraded to local; export offered |
| T6 | **Failed payment → recovery** | Use a card that declines on renewal | `invoice.payment_failed`; org `past_due`; **access stays on**; dunning email #1 sent; retry succeeds → `invoice.paid`, org back to `active` |
| T7 | **Failed payment → terminal** | Force all retries to fail | Retries exhaust over ~21d; `subscription.deleted`; org downgraded to local; final dunning email sent |
| T8 | **Webhook idempotency** | Re-deliver same event id twice | Second delivery is a no-op; `billing_events` dedup holds; no double-provision/charge |
| T9 | **Local tier isolation** | Run `BR8N_BACKEND=local` end-to-end | **Zero** billing/MoR calls; works offline, no creds, `org_id="local"`; loopback-only |
| T10 | **Tax correctness** | Checkout as EU (VAT) + US-nexus-state customer | MoR applies/collects correct VAT/sales tax; invoice shows tax line; remittance is MoR's responsibility |

---

## Appendix — Citations

**br8n KB findings (project=br8n, kb=dev):**
- `[#b04f6d13]` — Fee Comparison: Lemon Squeezy vs Stripe at $10k MRR (MoR premium worth it for solo devs)
- `[#08a85dd6]` — Failed Payment Recovery & Dunning Metrics (7 retries/21d, 30–60% recovery, 2–5% MRR saved)
- `[#1aae84be]` — SaaS Analytics & Metrics Tools (Sigma, ProfitWell, Chartsy)

**Web sources (verified May 2026):**
- Fee comparison: [globalsolo](https://www.globalsolo.global/blog/stripe-vs-paddle-vs-lemon-squeezy-2026), [DEV](https://dev.to/jettfu/stripe-vs-paddle-vs-lemon-squeezy-fee-comparison-2026-2c77), [F³ Fund It](https://f3fundit.com/stripe-vs-paddle-vs-lemon-squeezy-micro-saas-2026/), [appstackbuilder](https://appstackbuilder.com/blog/stripe-vs-lemon-squeezy-vs-paddle)
- MoR vs Stripe Tax / liability: [Fungies](https://fungies.io/stripe-tax-limitations-understanding-the-difference-from-the-merchant-of-record-model/), [TaxJar](https://www.taxjar.com/blog/what-is-a-merchant-of-record-mor), [Stripe Tax](https://stripe.com/tax), [fintechspecs](https://fintechspecs.com/blog/stripe-vs-paddle-vs-lemon-squeezy-vs-polar-merchant-of-record-b2b-saas/)
- Stripe Managed Payments (MoR): [Paddle](https://www.paddle.com/resources/stripe-managed-payments), [Dodo](https://dodopayments.com/blogs/is-stripe-a-merchant-of-record)
- Stripe fees / intl surcharges: [Dodo calculator](https://dodopayments.com/blogs/stripe-fees-calculator)
- Stripe Billing 0.7% / Tax 0.5%: [Flexprice](https://flexprice.io/blog/stripe-pricing-breakdown-2026), [Stripe Billing pricing](https://stripe.com/billing/pricing)
- Trials/freemium/proration: [Chargebee](https://www.chargebee.com/resources/guides/subscription-pricing-trial-strategy/saas-trial-plans/), [OpenMedium](https://www.openmedium.biz/technology-consulting/how-to-choose-a-saas-billing-platform-that-wont-break-as-you-scale/)
- Webhooks: [Stripe subscription webhooks](https://docs.stripe.com/billing/subscriptions/webhooks)
- Dunning/smart retries: [Stripe Smart Retries](https://docs.stripe.com/billing/revenue-recovery/smart-retries), [Kinde](https://www.kinde.com/learn/billing/churn/dunning-strategies-for-saas-email-flows-and-retry-logic/)

*Pricing and provider features change frequently — re-verify against each provider's
own pricing page before contracting.*
