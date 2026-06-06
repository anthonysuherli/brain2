# WS8 — Onboarding, Activation & Growth Loops

**Workstream owner:** solo founder
**Status:** launch draft (2026-05-29)
**North Star:** weekly context-restoring resumes (a `/br8n:resume` that the developer
acts on after a real interruption — not a test invocation)

This workstream owns the path from "developer hears about br8n" to "developer has a
weekly resume habit." The thesis: br8n's time-to-value moment is **the first resume
card that actually replays where they left off** — and developers will only forgive the
install friction if they hit that moment inside the first session. Everything below is
in service of compressing install → first capture → first resume.

Grounded in the br8n `dev` KB (coverage: *sparse* on this query — see gaps at end).
Developers are skeptical of hype, decide on hands-on evidence (docs, code snippets,
ready-to-use SDKs), and require instant access, self-service, free tiers, and
frictionless onboarding before they will even evaluate [#f21b3893]. Their decision path
is peer-led — forums, GitHub, Reddit [#f21b3893]. That ICP truth governs every choice
here: br8n must *show* value in the product, never *tell* it in a brochure.

---

## 1. The activation path

The activation path is the **fewest steps to the aha moment**; everything not on that
path is friction to be cut ([Athenic cut 12 onboarding steps to 7 + SSO and moved median
time-to-activation from 8.2 days to 1.6, lifting activation 42%→81%](https://productquant.dev/blog/5-minute-aha-rule-optimize-ttv/)).
For br8n the critical path has exactly three nodes, and the goal is to traverse all
three **within the first working session**.

```
INSTALL ───────► FIRST CAPTURE ───────► FIRST RESUME CARD
(plugin or ext)   (auto on interrupt)    (the aha — "it replayed me")
```

| Step | What happens (br8n-specific) | The value moment | Friction today |
|---|---|---|---|
| **0. Install** | `/plugin marketplace add` → `/plugin install br8n@br8n` (Claude Code) **or** install VS Code extension. Backend needs `br8n` + deps (`sqlite-vec`) in `backend/.venv`. | None yet — pure cost | Plugin reload required before MCP connects; Python venv + `sqlite-vec` build; which tier am I on? |
| **1. First capture** | Auto-fires on the **first interruption** the dev hits anyway — window **blur**, **git checkout** (`.git/HEAD` change), or **idle ≥300s** (`triggers.ts`). Snapshots branch, open/cursor files, `git_diff_stat`, one-line hypothesis. Debounced 30s. Manual `/br8n:capture` also works. | "It noticed I left without me asking." | Dev must produce *one* interruption in-session; needs a hypothesis line; silent if backend isn't running |
| **2. First resume** | On focus-regain after a blur capture, the extension sets `pendingResume` and offers the card (`extension.ts`); or dev runs `/br8n:resume`. Card leads with the **latest hypothesis** ("You were: …") + files + diff stat, on `ViewColumn.Beside`. Coverage routes: `rich`/`sparse` → show card, `gap` → offer explore. | **THE AHA** — "30 seconds and I'm back where I was, not 9.5 minutes." | Empty first card if no capture happened yet; `gap` coverage on a brand-new KB can underwhelm |

**Design implication:** capture must be *invisible and automatic* (it already is — blur/
checkout/idle), but resume must be *unmissable*. The single highest-leverage onboarding
act is **engineering a guaranteed interruption-and-return inside session one** so the dev
sees a populated card, not an empty state. See the onboarding copy in §5 — the install
confirmation should explicitly say "switch windows and come back; I'll show you what I saved."

> Benchmark gravity: ["the battle is won or lost in the first 300 seconds … under 5 min
> to aha"](https://productquant.dev/blog/5-minute-aha-rule-optimize-ttv/); a 25% activation
> lift compounds to [~34% MRR over 12 months](https://www.designwithvalue.com/aha-moment).
> The local free tier ([75% of PLG companies start with free/freemium](https://www.appcues.com/blog/aha-moment-guide))
> is the entire reason a skeptical dev will try at all [#f21b3893].

---

## 2. Friction-removal checklist

Each item maps to a concrete fix that shortens time-to-value. Priority = how directly it
blocks the first resume card.

### Install / connect (highest priority — this is where devs bounce)

- [ ] **Plugin reload gap.** After `/plugin install br8n@br8n` the MCP server only
  connects on session reload. *Fix:* the install skill / README must end with a single
  bold instruction "**Reload this session now** (the MCP tools connect on reload)" — make
  the reload the explicit last install step, not an afterthought.
- [ ] **MCP connect verification.** Dev can't tell if `br8n_*` tools are live. *Fix:*
  ship a `/br8n:resume` that, on connection failure, returns a one-line diagnostic
  ("backend not reachable at `BR8N_API_URL` — is `python -m br8n.api.main` running?")
  instead of a silent error. Make the **status bar item** (`$(brain) br8n`, already in
  `extension.ts`) flip to a connected/disconnected state.
- [ ] **Backend Python deps.** `sqlite-vec` + editable install trip people up. *Fix:*
  one copy-paste block per toolchain (`uv` *and* plain `python3.11 -m venv`), and a
  `python -m br8n.api.main --check` health command that prints "✓ db, ✓ sqlite-vec,
  ✓ loopback" or names the exact missing piece. Local tier needs **no API key** (loopback
  no-auth) — say so loudly so devs don't hunt for a key.
- [ ] **Tier ambiguity.** Dev doesn't know if they're local or cloud. *Fix:* echo the
  resolved backend on first boot ("br8n: local tier (SQLite at `~/.br8n/brain.db`,
  no auth)") — `active_backend()` already knows.

### First-capture / first-resume (removes the empty state)

- [ ] **Guaranteed first capture.** Don't rely on luck. *Fix:* on first activation, the
  extension fires a **manual capture once** (or prompts "Save where you are now?") so the
  KB is never empty when the dev first opens the card. ["Never land a user on an empty
  screen"](https://productquant.dev/blog/5-minute-aha-rule-optimize-ttv/).
- [ ] **Hypothesis friction.** A blank hypothesis prompt stalls capture. *Fix:* pre-fill
  it from the branch name + top diff file ("working on `<file>` on branch `<kb>`") so the
  dev edits rather than authors.
- [ ] **`gap` coverage on a fresh KB.** First card may be thin. *Fix:* when coverage is
  `gap`, the card's CTA is the **explore button** (already wired) — frame it as "I don't
  know this repo yet — want me to learn it? (~1-3 min)", turning the empty state into the
  product's second feature, not a dead end.

> Tactics validated cross-source: simplify the critical path, progressive disclosure,
> templates/sample data over blank screens, and guided flows ([Intercom: tour-completers
> activate 30% faster](https://www.appcues.com/blog/time-to-value);
> [productschool](https://productschool.com/blog/product-strategy/product-led-onboarding)).

---

## 3. Aha moment + the metric that proves it

**Aha moment (definition):**
> The developer is interrupted, returns, opens `/br8n:resume`, and the card replays
> their exact intent — latest hypothesis + open files + in-flight diff — so they resume
> real work in ~30 seconds instead of rebuilding context for ~9.5 minutes.

This is a genuine aha, not a setup step: ["the real aha is the user accomplishing
something they couldn't do before signing up"](https://www.appcues.com/blog/aha-moment-guide).
Completing the install or even firing a capture are *prerequisites* — the aha is the
**replay landing**.

**Activation metric (proves the aha):**
> **% of new installs that view a populated resume card (coverage ≠ empty) within their
> first session**, target a single-digit-minutes [TTFV](https://productquant.dev/blog/5-minute-aha-rule-optimize-ttv/).

**Coordinating with the North Star (weekly context-restoring resumes):** activation is the
*leading* indicator; the North Star is the *retained* outcome. The funnel:

| Stage | Metric | Why it matters |
|---|---|---|
| Activation (leading) | First populated resume card in session 1 | Proves the dev felt the value once |
| Habit (lagging) | **Weekly context-restoring resumes** (North Star) | A resume acted on after a real interruption, ≥1×/week |
| Quality guard | Resume → resumed-work rate (did they keep coding after the card?) | Distinguishes a real replay from a glance |

The habit loop ([trigger → routine → reward](https://productgrowth.in/insights/consumer/habit-loop-product-design/))
maps cleanly: **trigger** = the interruption br8n already detects; **routine** = open
the resume card; **reward** = instant re-entry. br8n owns the trigger *and* the reward,
which is exactly the condition for engineered retention. Depth-of-integration beats
volume ([devs who write custom error handlers retain better than high-call-volume
users](https://www.userintuition.ai/reference-guides/habit-loops-and-retention-what-to-study-what-to-ship/)) —
so a secondary health metric is **repos with ≥3 captures** (the dev has wired br8n into
a real workflow, not kicked the tires).

---

## 4. Product-led growth loop: the **shareable resume card**

**Pick:** shareable / showcase loop on the resume card. br8n already *produces a
shareable artifact every session* — the card HTML — and ["every piece of content the user
creates is an advertisement for the tool that made it"](https://reimer.me/growing-devtools/growth-loops).

**The loop:**

1. Dev hits the aha (a great resume card replays a gnarly debugging session).
2. **"Share this resume"** exports the card as a self-contained HTML / image / gist —
   redacted to intent + file names (never proprietary diff content; redaction is the trust
   gate). A small "↻ resumed in 30s with br8n" footer + install link is the payload.
3. Dev drops it in a PR description, a standup thread, or a tweet ("this is how I picked up
   a 2-day-old branch") — the peer-led channels br8n's ICP actually trusts [#f21b3893].
4. A peer sees a *concrete artifact* (hands-on evidence, the only thing this ICP believes
   [#f21b3893]), clicks install, hits their own aha → produces their own shareable card.

**Why it compounds:** the artifact is generated as a *byproduct of getting value*, not as a
marketing chore — the defining property of a real growth loop where ["the product is both
the value delivery and the distribution channel"](http://nativeviralloop.com/knowledge/product-led-growth-viral-loop.html).
Output scales with active usage, so acquisition rides retention instead of paid spend —
ideal for a solo founder with no marketing headcount.

**Adjacent loops to stage later** (do not build at launch — keep scope tight):
- **KB-as-API distribution** — the cloud tier's `/v1` context API lets other tools read a
  repo's session KB; each integration is a new surface ([integrations as loops, Snyk-style
  GitHub PRs](https://reimer.me/growing-devtools/growth-loops)). Cloud value prop, *future*.
- **Team invite** — "share this branch's brain with a teammate" (cross-machine sync). Also
  a *future* cloud differentiator per the tiers design; do not document as shipping.

---

## 5. Re-engagement loop + empty-state copy

### Re-engagement: resume-card-on-focus

br8n's re-engagement is a **contextual trigger**, the strongest kind — surface the
product ["at the right moment based on user behavior"](https://www.userintuition.ai/reference-guides/habit-loops-and-retention-what-to-study-what-to-ship/),
not a nagging notification.

- **Primary (already wired):** after a blur-triggered capture, on focus-regain the
  extension flips `pendingResume` and offers the card (`extension.ts`). This *is* the
  re-engagement loop — the dev's own context-switch is the re-entry trigger. Polish target:
  make the offer a gentle, dismissible status-bar nudge, never a stealing-focus modal.
- **Branch-switch resume:** the `git_checkout` trigger should, on the *next* return to a
  branch, auto-offer that branch's card — "welcome back to `feature/x`, here's where you
  were."
- **Lapsed-repo nudge (cloud/email, future):** Day-1/3/7 micro-retention checkpoints
  ([habit windows](https://userpilot.com/blog/app-retention-strategies/)) — but for a
  loopback local tool, keep re-engagement *in-editor*, not email. Notifications are
  ["training wheels"](https://productgrowth.in/insights/consumer/habit-loop-product-design/);
  br8n's real trigger is the interruption itself.

### Empty-state onboarding copy (drafts)

Empty states must ["always suggest what to do next" and use friendly
personality](https://blog.logrocket.com/ux-design/empty-states-ux-examples/). Three states
br8n will hit:

**A. Fresh install, no captures yet (resume card opened too early):**
> **Nothing to resume — yet.**
> br8n saves your context automatically the moment you step away — switch windows,
> check out a branch, or go idle for 5 minutes, then come back here.
> *Want to test it now?* Run **/br8n:capture** to snapshot where you are, then reopen
> this card. You'll see how 30-second re-entry feels.

**B. Capture exists but coverage = `gap` (KB doesn't know the repo):**
> **You're saved — but I don't know this repo well yet.**
> Here's where you left off: *"<latest hypothesis>"*.
> I can spend ~1–3 minutes learning this codebase + branch from the web and your repo so
> future resumes are richer. **[ Explore this repo → ]**

**C. Backend unreachable (the silent-failure killer):**
> **br8n can't reach its engine.**
> The local engine isn't responding at `<BR8N_API_URL>`. Start it with
> `python -m br8n.api.main` (free local tier — no API key needed, loopback only), or run
> `python -m br8n.api.main --check` to see what's missing. Then reopen this card.

---

## Open gaps (KB coverage was *sparse* on this query)

The `dev` KB grounded ICP + SaaS benchmarks well [#f21b3893, #43300575] but had **no
findings specific to**: developer-plugin onboarding funnels, MCP/Claude-Code activation
patterns, or context-tool retention curves. Recommend a `/br8n:explore` pass on
"developer plugin activation funnel" and "AI coding-tool retention benchmarks" before the
launch metrics targets in §3 are set as hard numbers rather than directional.

---

### Sources

- [The 5-Minute Aha Rule / TTFV optimization — ProductQuant](https://productquant.dev/blog/5-minute-aha-rule-optimize-ttv/)
- [The aha moment guide — Appcues](https://www.appcues.com/blog/aha-moment-guide)
- [Shorten time to value with onboarding — Appcues](https://www.appcues.com/blog/time-to-value)
- [Aha Moment & activation — DesignWithValue](https://www.designwithvalue.com/aha-moment)
- [Product-led onboarding — Product School](https://productschool.com/blog/product-strategy/product-led-onboarding)
- [Growth loops for devtools — Jonathan Reimer](https://reimer.me/growing-devtools/growth-loops)
- [PLG & viral loops — NativeViralLoop](http://nativeviralloop.com/knowledge/product-led-growth-viral-loop.html)
- [Habit loops and retention — UserIntuition](https://www.userintuition.ai/reference-guides/habit-loops-and-retention-what-to-study-what-to-ship/)
- [Habit loop in product design — ProductGrowth.in](https://productgrowth.in/insights/consumer/habit-loop-product-design/)
- [App retention strategies — Userpilot](https://userpilot.com/blog/app-retention-strategies/)
- [Empty states in UX — LogRocket](https://blog.logrocket.com/ux-design/empty-states-ux-examples/)
- KB findings: `[#f21b3893]` developer buying behavior, `[#43300575]` month-one SaaS benchmarks (br8n `dev` KB)
