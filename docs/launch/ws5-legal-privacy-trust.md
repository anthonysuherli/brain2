# WS5 — Legal, Privacy & Trust

**Workstream owner:** founder
**Status:** draft for launch
**Last updated:** 2026-05-29

> **This is advisory, not legal advice.** I'm an AI assistant, not your attorney.
> Before you charge money or publish a privacy policy, have a startup lawyer (or a
> fixed-fee service like [Clerky](https://www.clerky.com/) / [Stripe Atlas](https://stripe.com/atlas)
> legal templates) review the entity formation and the customer-facing docs. The
> dollar/timeline figures below are 2025–2026 market ranges and move over time.

---

## Why this is the highest-risk workstream

br8n captures and stores **sensitive developer context**: git branch, open/cursor
file paths, `git diff --stat`, and a one-line hypothesis of intent. On the **free
local tier** this never leaves the machine (SQLite at `~/.br8n/brain.db`,
loopback-only, no auth — see `CLAUDE.md` "Storage tiers"). On the **paid cloud tier**
that same context lands in **Supabase** (Postgres + pgvector, RLS) — and the
**exploration/extraction pipeline sends content to LLM + embedding provider APIs**.
That egress is the entire legal surface area. The free tier is a genuine trust asset;
the cloud tier is where DPA, encryption, retention, and sub-processor promises become
real obligations.

This split maps directly onto the shipped architecture: the cloud tier is the
Supabase backend behind `SupabaseStore` plus GoTrue login (snapshot `141be947` —
"two-tier storage … free local SQLite / paid cloud Supabase behind a Store protocol").

---

## 1. Entity + minimum legal kit before charging

### Entity: form a single-member LLC (don't stay a sole proprietor once money moves)

A sole proprietorship is the cheapest and simplest path (no formation paperwork, some
tax deductions), **but it offers zero liability protection** — every customer dispute,
data-handling claim, or contract problem reaches your personal assets directly. A
single-member LLC gives you a liability shield with pass-through taxes and modest cost,
and forming it is "a fraction of the cost of a single lawsuit"
([EasyFiling](https://easyfiling.us/llc-for-saas-business/),
[SpunkArt](https://spunk.codes/blog/llc-guide-solo-founders)).

Because br8n stores **sensitive code/git data**, the liability exposure is higher
than a typical content SaaS — a data-handling claim is a live risk. **Form the LLC
before you take the first paid dollar.** Indie Hackers' "you don't need an LLC yet"
advice applies to pre-revenue hobby projects; it stops applying the moment you're
processing payments and storing customer code
([Indie Hackers](https://www.indiehackers.com/post/you-dont-need-an-llc-yet-how-and-when-to-form-a-business-entity-237f8e6145)).

- **Where:** home state is simplest and usually cheapest for a solo US founder. Delaware/
  Wyoming are popular for "pro-tech laws and low cost" but add a foreign-qualification
  step + registered-agent fee if you operate elsewhere — only worth it if you anticipate
  venture funding ([PayPro](https://payproglobal.com/how-to/register-saas-business/),
  [Baremetrics](https://baremetrics.com/academy/business-formation-101-for-saas-companies)).
  **If you plan to raise VC later, a Delaware C-corp is the standard** — but for selling
  to individual developers first, an LLC is right; you can convert later.
- **Registered agent** is mandatory for every LLC (state requirement).
- **Sales tax:** SaaS is taxable in some US states and not others. This is the single
  biggest reason to consider a **Merchant of Record** (see kit below) — it offloads tax
  liability entirely. br8n KB finding `b04f6d13` already costs this: ~$230/mo premium
  at $10k MRR for Lemon Squeezy MoR over raw Stripe, "potentially worth every dollar for
  solo developers to avoid tax compliance headaches."

### Minimum legal kit before the first paid dollar

| Item | Why | How |
|---|---|---|
| Single-member LLC + EIN | Liability shield, business bank account | Home-state filing or Clerky/Atlas |
| Business bank account | Pierce-the-veil protection; don't commingle | Any business checking |
| **Terms of Service** | Limits liability, sets refund/termination terms, governing law | Generator (§2) + lawyer review |
| **Privacy Policy** | Legally required once you collect data (GDPR/CCPA), and devs read it | Generator (§2) |
| **DPA** (cloud tier) | GDPR Art. 28 requires it when you process customer data as a processor | Template (§2) |
| **Data-handling / Security page** | The trust artifact devs actually evaluate (§3) | Hand-written (§3) |
| Payment processor / MoR | Tax + checkout. MoR (Lemon Squeezy/Paddle) offloads sales-tax/VAT liability | KB `b04f6d13`, `3636613` |

A functional product site needs, at minimum, **privacy policy, refund policy, terms of
service** before charging ([EasyFiling](https://easyfiling.us/llc-for-saas-business/)).
Strongly consider a **Merchant of Record** for v1 so you don't own global sales-tax/VAT
compliance as a solo founder.

---

## 2. ToS + Privacy Policy + DPA outline (tailored to "we store code snapshots + git state")

**Recommended source for v1:** generate the base documents, then have a lawyer review.
For a solo founder on a budget, [**GetTerms.io**](https://www.termsfeed.com/blog/best-privacy-policy-generators/)
is the best value (free single doc; $25 Starter / $49 Comprehensive one-time; SaaS-specific
ToS) and [**Termly**](https://fortunly.com/business/best-privacy-policy-generator/)
is the best all-around ($10/mo, auto-updates, GDPR, SaaS templates). For self-updating
attorney-level policies, [Iubenda](https://fortunly.com/business/best-privacy-policy-generator/)
(from ~$6/mo per site). **Generators are a starting point, not a substitute for review**
— br8n's data class (source-code-adjacent) is sensitive enough to warrant one paid
lawyer pass. Recommendation: **Termly for privacy/ToS + a free GDPR Art. 28 DPA template,
then one fixed-fee lawyer review.**

### Terms of Service — key clauses (not full legalese)

- **Service description & tiers** — free local vs paid cloud; that the free tier runs
  entirely on the user's machine.
- **Acceptable use** — no uploading third-party code the user lacks rights to capture.
- **Customer data / IP ownership** — *the customer owns their code and captured context;
  br8n claims no ownership over customer content.* This is critical for a code tool;
  state it plainly.
- **License to process** — limited license to process captured content **only to provide
  the service** (store snapshots, generate preamble/synopsis, run exploration). Explicitly:
  **br8n does not train models on customer code.**
- **Subscription, billing, refunds, cancellation** — term, auto-renewal, refund window.
- **Warranty disclaimer + limitation of liability** — cap liability (typically fees paid
  in trailing 12 months); "as-is" disclaimer. This clause is the entity's main protection.
- **Termination & data return/deletion** — what happens to stored snapshots on cancel (§3).
- **Governing law / venue**, changes-to-terms, contact.

### Privacy Policy — key sections (tailored)

- **What we collect:** account/auth identity (cloud tier, via GoTrue); **workspace
  snapshots** = git branch, open/cursor **file paths**, `git diff --stat`, one-line
  hypothesis. **Be explicit that file paths and diff stats can themselves be sensitive.**
- **What we do NOT collect on the free tier:** nothing leaves the device — name it.
- **How we use it:** provide resume/capture, generate preamble + synopsis, run the
  exploration pipeline. **No selling, no ad targeting, no model training on customer data.**
- **Sub-processors:** Supabase (storage); LLM + embedding API provider(s) for exploration/
  extraction. Link to the data-handling page (§3) and a maintained sub-processor list.
- **Legal bases (GDPR), data subject rights (access/export/delete), CCPA notice.**
- **Retention & deletion** (§3), **international transfer** note (US hosting), **security**
  summary, **breach notification** commitment, **contact / DPO-equivalent**.

### DPA — outline (cloud tier only; GDPR Art. 28)

A DPA is **legally required under GDPR Article 28** when you process customer personal
data as a processor ([Secure Privacy](https://secureprivacy.ai/blog/data-processing-agreements-dpas-for-saas),
[GDPR.Direct](https://gdpr.direct/guides/data-processing-agreement-template)). Offer it as
a click-through / downloadable; you don't need to negotiate each one for individual devs,
but enterprise buyers will ask. Core clauses:

- **Roles:** customer = controller, br8n = processor; subject matter = code-context
  snapshots.
- **Scope & instructions** — process only on documented customer instruction.
- **Sub-processor terms** — list Supabase + LLM/embedding provider(s); **right to object**;
  commit to **30-day notice** before adding a sub-processor (HubSpot-style public list +
  email subscription is the norm) ([Secure Privacy](https://secureprivacy.ai/blog/data-processing-agreements-dpas-for-saas)).
- **Security measures** — encryption in transit + at rest, MFA, access control, incident
  response (mirror §3).
- **Sub-processor "technical access" standard** — anyone who *can technically* access the
  data is a sub-processor, even if they don't actively read it; that's why the LLM/embedding
  API counts ([Secure Privacy](https://secureprivacy.ai/blog/data-processing-agreements-dpas-for-saas)).
- **Deletion/return on termination** — delete or return all personal data and **certify
  deletion, typically within 30 days** ([Secure Privacy](https://secureprivacy.ai/blog/data-processing-agreements-dpas-for-saas)).
- **Audit rights, breach notification timeline, SCCs** for EU→US transfer.

---

## 3. Data-handling page content (publish at `/security` or `/data`)

This is the artifact developers actually read — write it plainly, not in legalese. Devs
"are skeptical of hype" and evaluate on "clarity and utility" (KB `f21b3893`, `11febc35`);
strong security messaging can lift trust materially (KB `b55376da`). Suggested content:

### Two tiers, two very different data stories

> **Free / local tier — your code never leaves your machine.**
> Snapshots are stored in a local SQLite database at `~/.br8n/brain.db`. The API binds
> to `127.0.0.1` (loopback only) and requires no account and no API key. Nothing is
> transmitted to br8n servers, Supabase, or any LLM/embedding API. If you never enable
> the cloud tier, we never see your data — by design.

> **Paid / cloud tier — what leaves your machine, and where it goes.**
> When you enable the cloud tier, captured snapshots (git branch, open/cursor file paths,
> `git diff --stat`, your one-line hypothesis) are sent to and stored in Supabase. When you
> run exploration/extraction, relevant content is sent to our LLM and embedding API
> provider(s) to generate research and vectors. **This is the moment your code-context
> data leaves your device.** We tell you this before you turn it on (see §5).

### Encryption, retention, deletion, sub-processors

- **In transit:** TLS/HTTPS for all client↔cloud and cloud↔sub-processor traffic.
- **At rest:** Supabase encrypts customer data at rest; Supabase maintains SOC 2, HIPAA,
  and GDPR compliance and encrypts data at rest and in transit
  ([Supabase](https://supabase.com/solutions/developers)). Cloud providers are expected to
  encrypt at rest + in transit, use MFA, audit regularly, and have an incident-response
  plan ([Secure Privacy](https://secureprivacy.ai/blog/data-processing-agreements-dpas-for-saas)).
- **Access control:** Supabase Row-Level Security scopes every row to its owner; the
  per-request access token carries RLS scope (see `CLAUDE.md` "Storage tiers").
- **Retention:** state a concrete policy — e.g., snapshots retained for the life of the
  account; deleted within **30 days** of account deletion or on request (the SaaS norm)
  ([Secure Privacy](https://secureprivacy.ai/blog/data-processing-agreements-dpas-for-saas)).
- **Deletion / export:** self-serve "delete my data" + export. Certify deletion on request.
- **No training:** we do not use customer code/context to train models, and our LLM/
  embedding sub-processor is configured for **no-retention / no-training** on submitted
  content (verify and name the provider's data-use terms — this is the single most
  important disclosure for a code tool).

### Sub-processor list (maintain publicly + notify on change)

| Sub-processor | Purpose | Data | Notes |
|---|---|---|---|
| Supabase | Storage (Postgres + pgvector), auth | Snapshots, account identity | SOC 2 / GDPR; RLS |
| LLM API provider | Exploration/extraction generation | Snippets of captured context during explore | Configure no-train/no-retain; name it |
| Embedding API provider | Vector embeddings for retrieval | Captured-context text | Same as above |
| Payment processor / MoR | Billing | Billing identity (not code) | e.g., Lemon Squeezy/Stripe |

Adopt the HubSpot model: dedicated public page, entity names + purposes + locations,
last-updated date, and an email subscription for change notices, with a **30-day objection
window** before a new sub-processor goes live ([Secure Privacy](https://secureprivacy.ai/blog/data-processing-agreements-dpas-for-saas)).

---

## 4. Trust roadmap (what to promise, and when SOC 2 pays off)

Developers buy on evidence, not promises (KB `f21b3893`), and a frictionless self-serve
free tier is itself a trust signal (KB `c707...`/`5cef7337` Sentry sandbox pattern). So
the early trust strategy is **architecture + transparency**, not certifications.

### Pre-SOC 2 (launch → first enterprise interest) — promise these, free:

1. **The local tier as proof, not marketing** — "code never leaves your machine" is
   verifiable (loopback bind, no network calls); let skeptical devs confirm it.
2. **A plain-English `/security` page** (§3) — encryption, retention, deletion, no-training,
   sub-processor list. This alone answers most individual-dev concerns.
3. **Self-serve data export + delete.**
4. **Public roadmap to SOC 2** — sharing readiness milestones "calms concerns about
   potential vulnerabilities" even before the audit completes
   ([KLR](https://kahnlitwin.com/blogs/business-blog/soc-2-compliance-for-saas-companies-a-practical-guide)).
5. **Lean on sub-processor compliance** — Supabase's SOC 2/GDPR posture is a borrowed
   trust signal you can cite ([Supabase](https://supabase.com/solutions/developers)).
6. **A short security questionnaire pre-fill** — answer the common SIG/CAIQ categories
   (access control, encryption, retention, logging, incident response) on the page so you
   can paste from it; that's exactly what questionnaires probe
   ([Bitsight](https://www.bitsight.com/blog/vrm-security-questionnaires-sig-caiq-cis-controls),
   [UpGuard](https://www.upguard.com/blog/sig-questionnaire)).

### When SOC 2 becomes worth it

Don't do SOC 2 at launch — it's the wrong spend for selling to individual developers.
**The trigger is your first serious enterprise/team deal that gates on it.** In 2026 most
enterprise security questionnaires explicitly request SOC 2 **Type 2**
([DSALTA](https://www.dsalta.com/resources/soc-2/soc-2-type-1-vs-type-2-timeline-cost-guide)).

| | Type I | Type II |
|---|---|---|
| What it proves | Controls designed correctly at a point in time | Controls operated effectively over 3–12 mo |
| Cost (startup, automation platform) | ~$25k–$40k | ~$45k–$70k (range $25k–$80k all-in) |
| Timeline | 3–6 mo (audit-ready faster w/ platforms) | 6–12 mo incl. 3-mo min observation window |
| Hidden cost | Founder/eng time (a CTO + 1 eng ≈ 400 hrs ≈ $40k), pen test $5k–$25k | same, sustained |

Sources: [Comp AI](https://www.trycomp.ai/hub/soc-2-cost-breakdown),
[StartupDefense](https://www.startupdefense.io/soc-2-costs-for-startups-complete-breakdown-and-budget-guide),
[DSALTA](https://www.dsalta.com/resources/soc-2/soc-2-type-1-vs-type-2-timeline-cost-guide).

**Sequencing for a solo founder:**
- **First enterprise ask → start Type I** for fast credibility (fastest path to initial
  enterprise trust). Many auditors **credit 40–60% of Type I cost toward Type II** if done
  within 12 months, so Type I is a cheap on-ramp, not wasted money
  ([DSALTA](https://www.dsalta.com/resources/soc-2/soc-2-type-1-vs-type-2-timeline-cost-guide)).
- **Sustained enterprise demand / regulated buyers → go to Type II.** It's what
  questionnaires now expect and is "non-negotiable" for Fortune 500 / regulated industries.
- **Use a compliance-automation platform** (Vanta/Drata/Comp AI class) — modern tooling cuts
  this from 200+ manual hours to weeks and gets you audit-ready far faster
  ([DSALTA](https://www.dsalta.com/resources/soc-2/soc-2-type-1-vs-type-2-timeline-cost-guide),
  [Comp AI](https://www.trycomp.ai/hub/soc-2-cost-breakdown)).
- A public-facing **SOC 3** summary lets you share assurance without exposing the
  confidential SOC 2 report ([KLR](https://kahnlitwin.com/blogs/business-blog/soc-2-compliance-for-saas-companies-a-practical-guide)).

### Enterprise security-questionnaire baseline (be ready to answer)

Buyers will send a SIG (SIG Lite ≈ 126 questions; SIG Core 800+) or CAIQ (~261 cloud
Y/N questions) across ~18–19 domains: access control, network security, data protection
(encryption, retention), logging/alerting, incident response, business continuity,
sub-processor oversight ([Bitsight](https://www.bitsight.com/blog/vrm-security-questionnaires-sig-caiq-cis-controls),
[UpGuard](https://www.upguard.com/blog/sig-questionnaire),
[Workstreet](https://www.workstreet.com/blog/caiq-vs-sig)). Pre-write answers for:
encryption at rest/in transit, who can access data, retention/deletion windows, MFA,
incident response, and the Supabase + LLM/embedding sub-processor chain. Most of this is
already true in the architecture — capture it once in a reusable doc.

---

## 5. The free-tier trust advantage — message it, and disclose egress at the exact seam

### Lead with "your code never leaves your machine"

This is br8n's strongest and most honest trust line, and it's a real differentiator:
most AI/dev tools emphasize "developer control" but **don't get to make a literal
"never leaves your machine" claim** ([Supabase agent tooling roundup](https://supabase.com/solutions/developers),
local-first peers like Dyad). br8n's free tier *can*, because the architecture enforces
it (SQLite + loopback + no auth + no network calls). Message it factually, not as hype —
that matches how devs evaluate (KB `f21b3893`, `11febc35` "educate, don't persuade"):

> **Free tier: 100% local. No account, no cloud, no API calls.**
> Your snapshots live in a SQLite file on your disk. br8n binds to localhost only and
> makes zero network requests. We can't see your data because it never reaches us.

Reinforce with verifiability (open the file, watch the network) — skeptical developers
trust what they can confirm over what they're told.

### The exact moment to disclose cloud-tier egress

Disclose **at the upgrade/enable seam — before the first byte leaves the device**, not
buried in the ToS. Concretely:

1. **On the cloud-tier toggle / sign-up:** an inline, plain-language notice —
   *"Enabling cloud sync sends your captured context (file paths, diff stats, hypothesis)
   to Supabase, and sends content to our LLM/embedding provider(s) when you run explore.
   This is the point your code-context data leaves your machine. [What we store · Sub-processors · Delete anytime]"*
   with a require-acknowledge checkbox.
2. **On first cloud capture and first `explore` run:** one-time confirmation that data will
   be transmitted, with a link to `/security`.
3. **In docs/README:** keep the tier boundary explicit (it already is in `CLAUDE.md`).

The honesty of doing this *at the seam* is itself the trust play: you're not hiding the
egress, you're making the user the one who flips it — which is exactly the credibility devs
reward. The free-tier promise stays clean precisely because the cloud disclosure is loud.

---

## Launch checklist (this workstream)

- [ ] Form single-member LLC + EIN + business bank account
- [ ] Choose payment: Merchant of Record (Lemon Squeezy/Paddle) for v1 tax offload
- [ ] Generate ToS + Privacy Policy (Termly/GetTerms) → **one fixed-fee lawyer review**
- [ ] Draft DPA from GDPR Art. 28 template (cloud tier)
- [ ] Publish `/security` page (§3) incl. public sub-processor list + change notifications
- [ ] **Confirm + document LLM/embedding provider no-train/no-retain terms** (highest-priority disclosure)
- [ ] Build self-serve data export + delete
- [ ] Implement cloud-enable egress disclosure at the seam (§5) with acknowledge step
- [ ] Pre-write SIG/CAIQ-baseline security answers (reuse for enterprise)
- [ ] Defer SOC 2 until first enterprise ask → Type I, then Type II

---

### KB findings cited
`141be947` (two-tier storage shipped), `b04f6d13` (Lemon Squeezy MoR cost/tax offload),
`f21b3893` (developer buying behavior — evidence over sales), `11febc35` (educate, don't
persuade), `b55376da` (security ↑ trust ~40%), `5cef7337` (Sentry frictionless sandbox =
trust). Coverage on legal/privacy was **sparse** in the KB — most substance here comes from
the web sources cited inline.
