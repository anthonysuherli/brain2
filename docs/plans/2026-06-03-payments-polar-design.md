# delapan payments — easiest path to first revenue (Polar MoR)

**Date:** 2026-06-03
**Status:** Design — ready to execute (manual signup + code integration)
**Owner:** Anthony

## Context

We want to start receiving payments for delapan without using Stripe-direct.
Stripe does not onboard **Indonesia-registered businesses** to *receive* payments,
and the founder is an Indonesian citizen, currently in the US on an **H-1B**, planning
an Indonesian **PT** eventually, selling a **mostly-global, self-serve** developer tool.

**Optimizing for:** fastest path to first dollar. Decision: start as an **individual
seller now**, migrate to the PT later.

## Decision: Polar (Merchant of Record)

Chosen over Lemon Squeezy and Gumroad because it uniquely clears every constraint at once:

- **Indonesia is a supported seller country** (payouts via **Stripe Connect Express**,
  which is a different product from standalone Stripe payments — the ID onboarding block
  does not apply).
- **Individuals can sign up** (no registered company required) when Stripe Connect
  Express offers the "Individual" business type for the country.
- **Merchant of Record** — Polar is the legal seller and remits all global VAT/sales tax
  on our behalf. We file no foreign tax registrations.
- **Developer-tool native**, lowest MoR fee of the candidates (~4% + fees).

Runner-up: **Lemon Squeezy** (5% + 50¢ + 1% non-US payout; mid-migration into Stripe
Managed Payments → platform uncertainty). Fallback for instant validation: **Gumroad**
(~10%, weak subscription UX). **Paddle** is the most mature but has stricter onboarding —
revisit once the PT exists.

> Sources: polar.sh/docs/merchant-of-record/supported-countries ;
> lemonsqueezy.com/blog/new-bank-payouts ; lemonsqueezy.com/blog/2026-update

## Open question that gates the "individual-now" path

**Does Stripe Connect Express currently offer the _Individual_ business type for
Indonesia?** Verify live during signup (Business Type toggle). If it is **company-only**,
flip to forming the PT first, then onboard the org. Everything else in this plan is
unchanged either way.

## ⚠️ Separate, unresolved track: H-1B work authorization

An MoR makes the **individual/company** able to *collect* money. It does **not** resolve
whether the founder may **actively operate** the business from US soil while on H-1B
(owning is fine; actively working it is restricted). This is an immigration question for
a US attorney — out of scope for the payments design, but must be tracked in parallel.
Mitigations under consideration: passive ownership + co-founder operates; work done only
while outside the US; own-company H-1B sponsorship (hard); change of status.

## Section 1 — Account setup (individual now)

1. Sign up at **polar.sh** with personal email; organization type = **Individual**.
2. Connect **Stripe Connect Express** for payouts; Business Type = **Individual**.
3. KYC: Indonesian **KTP** (or passport) + verification selfie. No NPWP/NIB needed yet.
4. Payout destination: **Indonesian bank account in own name** (fallback: Wise).
5. Tax form: submit **W-8BEN** (non-US person).
- Timeline: same-day to a few days (KYC review).

## Section 2 — Product & checkout

- Model delapan as a **subscription** product in Polar (define tiers/prices).
- Integrate **Polar Checkout** — hosted checkout link is the fastest (zero frontend
  work); upgrade to embedded/API checkout later.
- Gate access on Polar **webhooks** (`subscription.created/updated/canceled`) →
  flip an entitlement flag per user in the app's auth/store layer.
- Customer self-service: Polar's **customer portal** handles upgrades/cancellations.

## Section 3 — Payout

- Polar pays out via Stripe Connect Express to the connected ID bank/Wise on its payout
  schedule. As an individual, this revenue is **personal income** until the PT migration
  — track it for personal Indonesian tax (and note US tax exposure given physical
  presence; confirm with an accountant).

## Section 4 — PT migration path (later)

When the PT is formed (regular PT — chosen for adding a co-founder/investors later):
1. Create a **new Polar organization** under the PT (NIB, NPWP, company bank).
2. Re-create products/prices; point the app's webhook/entitlement config at the org.
3. Migrate active subscriptions (Polar support-assisted) or grandfather + new-signups-on-org.
4. From then on, revenue books to the PT; consider PKP/PPN only above IDR 4.8B and the
   0.5% UMKM final-tax facility for early years.

## Execution checklist

- [ ] (You) Sign up to Polar as Individual; verify ID "Individual" business type exists
- [ ] (You) Complete KYC + connect ID bank / Wise + submit W-8BEN
- [ ] (You) Create the delapan subscription product + price tiers in Polar
- [ ] (Code) Integrate Polar hosted checkout + webhook entitlement gating in the delapan app
- [ ] (Parallel) Draft ToS / Privacy (PDP-Law aware) / Refund pages Polar requires
- [ ] (Parallel) Book a US immigration attorney consult re: H-1B active-operation line
- [ ] (Later) Form PT → migrate Polar account to the org
