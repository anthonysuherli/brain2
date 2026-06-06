# br8n — The Most Efficient Path to Users (Strategy Brief)

> **⚠️ Correction (2026-05-30):** The **VS Code extension was removed** — not the right
> surface for now. Move **#2 (the free VS Code Marketplace listing as the SEO/trust
> engine)** is on hold and needs re-scoping; the active surfaces are the **Claude Code
> plugin** and the **iOS companion**. Analysis preserved as-is for the reasoning.

**Date:** 2026-05-30 · **Owner:** founder · **Question:** *What is the most
efficient way to gain users on br8n?*

This brief answers that one question through a **leverage ÷ effort** lens. It is the
"why" layer; the sequenced "what/when" lives in
[`ACTION-PLAN.md`](./ACTION-PLAN.md), and the channel detail in
[`ws2-distribution-channels.md`](./ws2-distribution-channels.md) /
[`ws8-onboarding-growth.md`](./ws8-onboarding-growth.md). Where this brief and the
workstreams agree, that's corroboration — the fresh 2026 web research below was run
independently and landed on the same thesis.

---

## The core insight

The most efficient lever for br8n is **not** a generic dev-tool playbook — it is
that br8n already ships into the single fastest-moving distribution channel in
developer tooling: **Claude Code plugins + MCP marketplaces.** That ecosystem now has
a *directory + one-command-install* loop that didn't exist 12 months ago, and most
plugins in it are low quality. br8n pairs:

1. a **real, felt pain** — losing context on interruption while pair-coding with an AI
   ("the ~9.5-minute context-rebuild tax"), and
2. a **zero-friction free tier** — local SQLite, no signup, no API key, loopback-only,
   data never leaves the machine.

Real pain + sub-2-minute time-to-value + native to a hot distribution surface is the
exact profile that wins bottoms-up adoption. **Concentrate effort there; do not
dilute across ten channels at once.**

---

## Why "efficient" = bottoms-up PLG for this product

- Developers evaluate hands-on and skip sales/ads/gated content — they go straight to
  docs, code, and peer validation. The product must do the acquiring.
  [productmarketingalliance](https://www.productmarketingalliance.com/developer-marketing/open-source-to-plg/)
- PLG winners optimize **Time-To-First-Value**; the freemium benchmark is **< 15 min**.
  Lovable hit $100M ARR in 8 months on this discipline. br8n's local loop can
  plausibly hit **< 2 min** (install → `/br8n:capture` → `/br8n:resume`).
  [daily.dev GTM](https://business.daily.dev/resources/dev-tool-companies-go-to-market-strategy-launch-scale/)
- Community-led / product-led / ecosystem channels outperform paid campaigns; 91% of
  SaaS plans to invest *more* in PLG in 2025.
  [userflow](https://www.userflow.com/blog/best-saas-customer-acquisition-strategies)
- Niche communities where your users already gather (Claude/Cursor Discords, targeted
  subreddits, HN) beat broad launch platforms for indie dev tools; Product Hunt's
  indie ROI has faded to "awareness + SEO," not the signup engine.
  [DEV: why PH no longer works](https://dev.to/indiehackerksa/why-product-hunt-no-longer-works-for-indie-founders-aom)

---

## Ranked by efficiency (leverage ÷ effort)

| # | Move | Effort | Why it's efficient |
|---|------|:---:|---|
| 1 | **Own the Claude Code plugin / MCP discovery surface** | **S** | One-command `/plugin install` + `claude mcp add`; community directories (claudemarketplaces.com) + `awesome-*` lists are near-zero-cost listings that put you in front of devs already sold on AI coding. br8n already has the manifest + marketplace.json + `.mcp.json`. **Highest leverage, lowest effort.** |
| 2 | **Free version on the VS Code Marketplace as the SEO/trust engine** | M | The proven paid-extension pattern: ship a valuable free version to maximize reach + search ranking, upsell later. The Marketplace is a *search engine*, not an event — keyword-rich listing + hero GIF + the first ~20 reviews compound. |
| 3 | **Protect time-to-first-value (it's already the moat)** | M | < 2-min local loop with zero config is rare. Keep all auth/Supabase friction out of the free path; engineer onboarding so a new user *manufactures* the resume-card aha in session 1. |
| 4 | **One signature content wedge on the pain, not the product** | M | "We measured the context-rebuild tax of AI pair programming" / "Build vs Buy: a context-resume layer for your editor." One linkable, data-backed essay beats a blog cadence and powers HN + community drops. |
| 5 | **Launch narrow, then HN — sequenced** | M | Get listed (1) → polish TTFV (3) → ship essay (4) → *then* coordinated Show HN + Discord/Reddit drops, so the launch lands on a product that converts. HN gives a 24h spike + 1-week tail of *attention*, rarely day-1 revenue. |
| 6 | **Hybrid/paid motion — later, not now** | — | PQLs convert 15–30% vs 2–5% for MQLs, but sync/cross-repo/team value props aren't built yet (per CLAUDE.md). Don't sell them. Spin the free flywheel; instrument who hits local's limits and let that PQL signal pull the cloud tier into existence. |

---

## The existential caveat (efficiency's blind spot)

Efficiency optimizes the *funnel*; it assumes the *trust precondition* is met. br8n
stores code. Per [`ws5`](./ws5-legal-privacy-trust.md), the LLC, lawyer-reviewed
ToS/Privacy/DPA, a `/security` page, and a **confirmed no-train / no-retain LLM term**
are a hard precondition of charging money — not a launch-week scramble. The free
tier's verifiable "code never leaves your machine" is the trust lead until then.

## The other blind spot: instrumentation

This entire strategy turns on TTFV / activation / retention numbers. Without telemetry
on the free tier (install → first capture → first resume → repeat use) you're flying
blind. [`ws6`](./ws6-metrics-instrumentation.md) covers the PostHog taxonomy +
content-free allowlist — treat it as a W0 dependency of everything above, not an
afterthought.

---

## If you do only three things (next 2 weeks)

See [`efficient-growth-plan.md`](./efficient-growth-plan.md) for the executable version.

1. **Get listed in every Claude Code plugin / MCP directory and awesome-list.**
2. **Make the free-tier install a sub-2-minute, zero-config "aha"**, with READMEs that
   sell the resume-card moment via a GIF.
3. **Write + seed the one "context-rebuild tax" essay** — *after* 1 and 2, so the
   traffic converts.

Everything else (paid ads, sales, broad launch platforms) is lower-efficiency until
that free-tier flywheel is measurably turning.

---

## Sources

- [Open source → PLG for dev tools — Product Marketing Alliance](https://www.productmarketingalliance.com/developer-marketing/open-source-to-plg/)
- [Developer GTM: launch & scale — daily.dev](https://business.daily.dev/resources/dev-tool-companies-go-to-market-strategy-launch-scale/)
- [Best SaaS customer acquisition strategies 2025 — Userflow](https://www.userflow.com/blog/best-saas-customer-acquisition-strategies)
- [Claude Code plugins — Anthropic](https://www.anthropic.com/news/claude-code-plugins)
- [Claude Code plugin/MCP directory — claudemarketplaces.com](https://claudemarketplaces.com/)
- [Plugin distribution — claudefa.st](https://claudefa.st/blog/tools/mcp-extensions/plugins-distribution)
- [Publishing VS Code extensions — VS Code docs](https://code.visualstudio.com/api/working-with-extensions/publishing-extension)
- [Selling VS Code extensions / free-to-pro — Dodo Payments](https://dodopayments.com/blogs/sell-vscode-extensions)
- [Why Product Hunt no longer works for indie founders — DEV](https://dev.to/indiehackerksa/why-product-hunt-no-longer-works-for-indie-founders-aom)
