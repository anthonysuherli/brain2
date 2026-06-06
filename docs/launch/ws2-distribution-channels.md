# WS2 — Distribution & Launch Channels

> **⚠️ Correction (2026-05-30):** The **VS Code extension was removed** — it's not the
> right surface for now. Every channel below that depends on it (notably **#3 VS Code
> Marketplace**, the r/vscode angle, and "Claude Code & VS Code" taglines) needs
> re-scoping before execution. The active surfaces are the **Claude Code plugin** and the
> **iOS companion**. The ranked analysis is preserved as-is for the reasoning; treat the
> VS-Code-dependent rows as on hold, not actionable.

**Product:** br8n — a context-capture-and-resume engine for developers. On interruption it captures workspace state (branch, open files, git diff, a one-line hypothesis) and replays a 30-second "resume card." Freemium: free local tier (SQLite, loopback, no auth, data stays on machine) + paid cloud tier (Supabase; sync/cross-repo/team designed but mostly unbuilt). Distributed as a **Claude Code plugin** (MCP tools) + a **VS Code extension**. Solo founder.

**Date:** 2026-05-29 · **Owner:** founder

---

## Grounding (br8n KB, project=br8n / kb=dev)

The capture/resume KB confirms the audience model this plan is built on:

- **Developers are skeptical of hype; they decide on hands-on evidence, docs, and code snippets — not sales copy** [#f21b3893]. Distribution must lead with a working free tier and a literal demo, never a pitch. This directly shapes the Show HN comment and the PH maker comment below.
- **The decision path is "social and peer-led — forums, GitHub feedback, Reddit threads"** [#f21b3893]. That is the entire ranked-channel thesis: go where devs already validate tools (HN, Reddit, daily.dev, plugin marketplaces), not where we'd run ads.
- **Messaging should carry specific technical detail (languages, tools, frameworks) and ride trusted technical context like daily.dev** [#844bbbf7]. Every channel asset names the concrete surface (Claude Code, VS Code, git, MCP) rather than abstractions.
- **Signature "Build vs Buy" content is a top-connected KB entity** — the planned durable-SEO play (see §6). KB coverage on launch channels was `sparse`, so the channel tactics and post-mortem numbers below are sourced from web research and cited inline.

---

## 1. Ranked channel table

Ranked by expected early-signup yield per unit of solo-founder effort. "Signups" = rough free-tier installs/activations for a *single* well-run push, not steady-state. br8n's free tier is loopback-only with no auth, so "signup" really means **install + first `/br8n:resume`** — friction is near zero, which favors the self-serve channels at the top.

| # | Channel | Effort | Expected signups (one push) | First concrete action |
|---|---------|:---:|---|---|
| 1 | **Show HN / Hacker News** | M | 100–500 if front page; ~0 if it sinks | Write the Show HN post in §2; line up a 60-sec asciinema/GIF of capture→resume; post Tue–Thu ~8–10am ET and camp the thread answering every comment for 6h. [markepear](https://www.markepear.dev/blog/dev-tool-hacker-news-launch) |
| 2 | **Claude Code plugin marketplace** | S | 50–200 (compounding) | Polish `.claude-plugin/marketplace.json` + `plugin.json`, publish the marketplace repo publicly, then submit to `anthropics/claude-plugins-official` and list on community directories (claudemarketplaces.com, claudecodeplugins.dev). One-command `/plugin install br8n@br8n` is the lowest-friction install we have. [Claude docs](https://code.claude.com/docs/en/discover-plugins) |
| 3 | **VS Code Marketplace** | M | 30–150/wk (compounding via search) | Publish the extension with a **keyword-rich display name** ("br8n — Resume Card / Context Capture") and tags (`context`, `resume`, `git`, `productivity`, `ai`); a hero GIF in the README is the listing's #1 conversion lever. [sixth blog](https://blog.trysixth.com/2024/07/how-we-achieved-over-30000-installs-on-our-vscode-extension.html) |
| 4 | **Reddit (targeted subs)** | S | 20–100 per post | Post the demo GIF to **r/programming is NOT allowed for self-promo** — use r/vscode, r/ChatGPTCoding, r/ClaudeAI, r/SideProject, r/selfhosted (privacy angle), r/devtools. Lead with the problem ("the 9.5-min context-rebuild tax"), not the product. [conbersa](https://www.conbersa.ai/learn/best-subreddits-for-developers), [daily.dev](https://business.daily.dev/resources/how-to-market-developer-tools-on-reddit-practical-guide/) |
| 5 | **Product Hunt** | M | 50–200 (mostly non-dev tail) | Build the asset kit in §3, recruit a gold-badge hunter or self-hunt, schedule 12:01am PT Tue–Thu. Treat as awareness + social proof, not the signup engine. [Arc playbook](https://arc.dev/employer-blog/product-hunt-launch-playbook/), [hackmamba/Merian](https://hackmamba.io/developer-marketing/how-to-launch-on-product-hunt/) |
| 6 | **daily.dev (Squad + Source)** | S | 20–80/post (compounding) | Submit the br8n blog as a Source; start a "br8n / context-capture" Squad; cross-post every §4 article there. Native context with devs already reading in a new tab. [daily.dev squads](https://daily.dev/blog/why-we-are-discontinuing-company-sources-and-moving-forward-with-squads/) |
| 7 | **X / Bluesky dev circles** | S | 10–60 per thread | Post the capture→resume GIF as a standalone thread; tag/reply into Claude Code + VS Code + indiehacker circles. Build-in-public cadence (2–3x/wk) compounds; one-off won't. |
| 8 | **Signature "Build vs Buy" guide** | L | Low day-1, high 6–12mo (durable SEO) | Write "Build vs Buy: a context-resume layer for your editor" (see §6). Slow burn, but the most durable channel and links from every other asset. [Heavybit](https://www.heavybit.com/library/article/the-developer-content-mind-trick-for-signature-content/), [everydeveloper](https://everydeveloper.com/consulting/signature-content/) |
| 9 | **YouTube / demo GIFs** | M | Asset multiplier (few direct) | Record one 60–90s screen capture of the real loop; cut a 10–15s loop GIF. This *single asset* powers channels 1, 3, 4, 5, 7. Make it before launching anything else. |
| 10 | **Dev Discords / Slacks** | S | 5–40 per share | Share in Claude Code / Anthropic, VS Code, and indie-dev Discords' #show-and-tell channels *after* being a participant. Lowest reach but highest-intent early adopters and bug reports. |

**Sequencing for a solo founder:** asset (9) → marketplaces (2,3) live first so installs work → Show HN (1) as the spike → Reddit + daily.dev + X (4,6,7) ride the same week → Product Hunt (5) ~1–2 weeks later once you have social proof → signature guide (8) as the always-on engine. Discords (10) sprinkled throughout.

---

## 2. Show HN — ready to post

HN rewards modest, explicit, builder-voice titles and bans superlatives; the first comment should follow the 7-part founder format and *invite feedback, not sell* [markepear](https://www.markepear.dev/blog/dev-tool-hacker-news-launch). This aligns with the KB's "developers close the tab if you sell to them" finding [#f21b3893].

**Title (pick one):**

> **Show HN: br8n – capture your dev context on interrupt, resume it in 30 seconds**

(Alt, if you want the pain framing up front: *Show HN: br8n – kill the 9.5-minute context-rebuild tax after an interruption*. Keep it explicit, no "best/first/fastest." The IndieHackers post-mortem found the title framing was the single biggest lever — their producty first title underperformed a problem-framed one [IndieHackers](https://www.indiehackers.com/post/front-page-of-hn-the-full-postmortem-traffic-lessons-surprises-cbe9e0a7f6).)

**First comment (draft):**

> Hi HN, I'm Anthony, the solo dev behind br8n.
>
> br8n captures your workspace state when you get interrupted — current branch, open files, the git diff, and a one-line note on what you were trying to do — and replays it as a 30-second "resume card" when you come back.
>
> The problem: every time I got pulled off a task (a meeting, a Slack ping, an incident), coming back cost me ~10 minutes of "wait, what was I doing, why is this diff like this." That tax is brutal when it happens five times a day. I wanted something that snapshots intent at the moment of interruption, not a notes app I have to remember to update.
>
> How it works: it's a Claude Code plugin (MCP tools `br8n_capture` / `br8n_resume`) and a VS Code extension. Capture writes a snapshot; resume taps a small per-repo/per-branch knowledge base and renders the card with your latest hypothesis + recent snapshots.
>
> The free tier is fully local: SQLite + `sqlite-vec` at `~/.br8n/brain.db`, binds 127.0.0.1, no auth, no account, nothing leaves your machine. There's a paid cloud tier for cross-machine sync planned, but I want to be upfront that the sync/team features are mostly still on the roadmap — today's value is the local loop.
>
> What I'd love feedback on: (1) is the captured snapshot the right set of signals, or what's missing? (2) the local-first / no-auth design — does that match how you'd actually want this to store data? (3) does the resume card belong in the editor, the terminal, or both?
>
> Install + the 60-sec demo are in the README: [link]. Happy to answer anything.

**Launch-day discipline (from the post-mortems):** HN traffic is a "controlled explosion" — a ~24h spike then a 1-week long tail [IndieHackers](https://www.indiehackers.com/post/front-page-of-hn-the-full-postmortem-traffic-lessons-surprises-cbe9e0a7f6). Answer every comment fast, agree-then-address objections, **no booster comments from alt accounts** [markepear](https://www.markepear.dev/blog/dev-tool-hacker-news-launch). Have analytics + install path verified *before* posting — PostHog's lesson was retention beats vanity, so wire up "did they run resume a second time" tracking [PostHog](https://posthog.com/blog/after-the-hn-launch).

---

## 3. Product Hunt asset checklist

Timing: launch 12:01am PT, Tue/Wed/Thu for the longest day; first-4-hour momentum is the strongest Top-5 predictor (>100 upvotes before 4am PT → 82% chance of Top 10) [Arc](https://arc.dev/employer-blog/product-hunt-launch-playbook/). Keep velocity natural and geographically diverse to avoid the clearing algorithm.

| Asset | Status | Draft copy / spec |
|---|:---:|---|
| **Name** | ☐ | br8n |
| **Tagline (≤60 char)** | ☐ | "Resume your dev work in 30 seconds, not 10 minutes" |
| **Alt tagline** | ☐ | "Context capture + resume cards for Claude Code & VS Code" |
| **Topics/tags** | ☐ | Developer Tools, Productivity, Artificial Intelligence, GitHub, Visual Studio Code |
| **Thumbnail (240×240)** | ☐ | br8n mark on dark bg; legible at small size |
| **Gallery shot 1** | ☐ | The 30-sec resume card rendered (hypothesis + snapshot list) — the hero |
| **Gallery shot 2** | ☐ | Capture moment: branch + open files + diff stat being snapshotted |
| **Gallery shot 3** | ☐ | Claude Code `/br8n:resume` running inline |
| **Gallery shot 4** | ☐ | "Local-first, loopback-only, no account" privacy panel |
| **Demo GIF/video** | ☐ | The 60–90s capture→resume loop from §9 (reuse) |
| **Hunter** | ☐ | Approach a gold-badge hunter in the dev-tools/AI space *or* self-hunt; agree the first comment in writing [hackmamba](https://hackmamba.io/developer-marketing/how-to-launch-on-product-hunt/) |
| **First "maker" comment** | ☐ | See draft below |
| **First-comment links** | ☐ | GitHub repo, install one-liner, README demo |
| **Pre-launch (2–4 wks)** | ☐ | Tease on X/Bluesky + Discords; collect "notify me" emails; watch hunted.space cadence [Arc](https://arc.dev/employer-blog/product-hunt-launch-playbook/) |

**Maker first-comment (draft):**

> Hey Product Hunt — maker here. br8n came out of my own frustration: every interruption cost me ~10 minutes of rebuilding mental context when I sat back down. br8n snapshots what you were doing at the moment you get pulled away — branch, open files, the diff, and a one-line "what I was trying to do" — then replays a 30-second resume card.
>
> It runs as a Claude Code plugin and a VS Code extension. The free tier is 100% local — SQLite on your machine, loopback-only, no account — so you can try the full loop with zero signup. A cloud tier for cross-machine sync is on the roadmap.
>
> Would genuinely love to hear: what's the first thing *you* check when you return to a task after being interrupted? That's exactly what I'm trying to put on the card.

---

## 4. Four-week content calendar

One real demo asset feeds everything; each piece is repurposed across channels. Goal column states the *primary* job of each post.

| Wk | Title | Primary channel(s) | Goal |
|:--:|-------|--------------------|------|
| **0 (pre)** | 60–90s screen-capture: "Interrupted mid-bug → back in 30s" + 15s loop GIF | YouTube + GIF asset | Produce the asset that powers all channels |
| **0 (pre)** | "Notify me" tease thread: building a context-resume layer in public | X / Bluesky / Discords | Seed PH "notify me" + early followers |
| **1** | **Show HN: br8n – capture context on interrupt, resume in 30s** | Hacker News | The spike: front page + first 200–500 installs |
| **1** | "I lose 10 minutes every time I'm interrupted — so I built a resume card" (GIF) | r/vscode, r/ClaudeAI, r/SideProject | Ride HN week; high-intent installs |
| **1** | Publish marketplace listings live + one-liner install thread | Claude marketplace + VS Code + daily.dev Source | Make installs trivial; durable discovery |
| **2** | "How br8n stays 100% local: SQLite + sqlite-vec, loopback, no auth" | daily.dev Squad + r/selfhosted + HN (as Show HN/blog) | Privacy differentiator; trust (per [#f21b3893]) |
| **2** | "What I'd actually want on a resume card" — community question post | X / Bluesky + Discords | Engagement + roadmap signal |
| **3** | **Product Hunt launch** + maker comment | Product Hunt | Awareness + social proof badge |
| **3** | "Why I made the free tier local-first (and the cloud tier honest)" | Blog → daily.dev → HN | Freemium positioning; founder credibility |
| **4** | **Signature guide: "Build vs Buy: a context-resume layer for your editor"** | Blog (SEO) + HN + daily.dev | Launch the durable always-on engine (§6) |
| **4** | "Two weeks of br8n: installs, what broke, what I'm shipping next" | X / Bluesky + IndieHackers + r/SideProject | Build-in-public retention loop |

---

## 5. Three dev-tool launch post-mortems (real numbers + the lesson for br8n)

**1. PostHog — Hacker News / Show HN launch**
Numbers: **800+ GitHub stars in 5 days, "well over 200 sign-ups," ~$1,000 early spend** for initial traction [PostHog](https://posthog.com/blog/after-the-hn-launch). Crucial detail: repo tags were initially too niche and *limited discoverability* until revised, which got them onto GitHub Trending.
→ **Lesson for br8n:** the headline number is vanity; "do people run resume a second time" is the real metric — instrument retention before launch. And **tags matter for compounding discovery** — apply this directly to the VS Code Marketplace tags and the GitHub repo topics (channels 3 & 2).

**2. "Health Data for Devs" — HN front-page post-mortem (IndieHackers)**
Numbers: **~6,000 page views, ~500+ uniques from HN, ~468 active users on launch day, ~20% bounce (very low for HN), 2+ min sessions… and zero direct conversions** — but 4 inbound inquiries + 8 LinkedIn connects (3 VCs) [IndieHackers](https://www.indiehackers.com/post/front-page-of-hn-the-full-postmortem-traffic-lessons-surprises-cbe9e0a7f6). The title was rewritten away from a "too producty" first attempt.
→ **Lesson for br8n:** HN delivers *attention*, rarely day-1 paid conversion — so optimize the spike for **free-tier installs + GitHub stars + email capture**, not revenue, and pour effort into the **title framing** (problem-first: "the 9.5-min context tax"). Expect a 24h explosion then a week-long tail; have the next channel (Reddit/PH) staged to catch it.

**3. Sixth — VS Code extension, 30,000+ installs**
Numbers: **30,000+ installs**, driven largely by renaming the extension to a **keyword-rich title**, which "dramatically increased daily installs"; once ranking + reviews accrued, they reverted to a concise name without losing rank [sixth](https://blog.trysixth.com/2024/07/how-we-achieved-over-30000-installs-on-our-vscode-extension.html).
→ **Lesson for br8n:** the VS Code Marketplace is a *search engine*, not a launch event — launch the listing as **"br8n — Resume Card / Context Capture (Claude Code, git)"** to capture intent queries, lean on the hero GIF for conversion, and let it compound. This is why channel 3 is ranked above the one-shot Product Hunt push.

---

## 6. Signature "Build vs Buy" guide (channel 8 detail)

The signature-content pattern (Adam DuVander / Heavybit): publish *the* definitive guide on how to build the thing you sell, link it from home/nav/footer, and let developers discover that building it themselves is more work than it looks — many come back to buy [Heavybit](https://www.heavybit.com/library/article/the-developer-content-mind-trick-for-signature-content/), [everydeveloper](https://everydeveloper.com/consulting/signature-content/). Proven examples: LaunchDarkly's "Build or Buy a Feature Flag System," Gremlin's "Chaos Monkey Guide." This is the top-connected "Signature Content (Build vs Buy)" entity in the br8n KB.

**br8n's guide:** *"Build vs Buy: a context-resume layer for your editor"* — honestly walk through rolling your own (a git hook that dumps branch/diff/open-files to JSON, a vector store for retrieval, an MCP server to surface it, the editor webview to render a card, and the upkeep of all four). The reader sees it's a real multi-part system — and that br8n's free local tier already does it. Per [#f21b3893], keep it concrete (real code snippets, real commands), zero sales tone; per [#844bbbf7], target keywords devs actually search ("resume coding context," "git context snapshot," "Claude Code MCP context"). It does not need to rank #1 — devs researching this problem dig deep [markepear](https://www.markepear.dev/blog/developer-marketing-guide).

---

### Sources
- br8n KB findings [#f21b3893] (developer buying behavior), [#844bbbf7] (dev-focused messaging / daily.dev), KG entity "Signature Content (Build vs Buy)"
- [How to launch a dev tool on Hacker News — markepear](https://www.markepear.dev/blog/dev-tool-hacker-news-launch)
- [After the HN launch — PostHog](https://posthog.com/blog/after-the-hn-launch)
- [Front page of HN: full postmortem — IndieHackers](https://www.indiehackers.com/post/front-page-of-hn-the-full-postmortem-traffic-lessons-surprises-cbe9e0a7f6)
- [Product Hunt Launch Playbook — Arc](https://arc.dev/employer-blog/product-hunt-launch-playbook/)
- [How to launch a dev tool on Product Hunt — hackmamba / Flo Merian](https://hackmamba.io/developer-marketing/how-to-launch-on-product-hunt/)
- [Discover and install plugins — Claude Code Docs](https://code.claude.com/docs/en/discover-plugins)
- [How we got 30,000+ installs on our VS Code extension — sixth](https://blog.trysixth.com/2024/07/how-we-achieved-over-30000-installs-on-our-vscode-extension.html)
- [Best subreddits for developer marketing — conbersa](https://www.conbersa.ai/learn/best-subreddits-for-developers)
- [How to market dev tools on Reddit — daily.dev](https://business.daily.dev/resources/how-to-market-developer-tools-on-reddit-practical-guide/)
- [Discontinuing company sources, moving to Squads — daily.dev](https://daily.dev/blog/why-we-are-discontinuing-company-sources-and-moving-forward-with-squads/)
- [The Developer Content Mind Trick for Signature Content — Heavybit](https://www.heavybit.com/library/article/the-developer-content-mind-trick-for-signature-content/)
- [Signature Content — everydeveloper](https://everydeveloper.com/consulting/signature-content/)
- [Developer marketing guide — markepear](https://www.markepear.dev/blog/developer-marketing-guide)
