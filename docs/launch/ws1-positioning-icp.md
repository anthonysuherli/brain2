# WS1 — Positioning & ICP

brain2 launch workstream. Goal: a concrete, copy-ready positioning spine for a context-capture-and-resume engine for developers, shipping freemium (free local SQLite tier / paid cloud Supabase tier), distributed as a Claude Code plugin + VS Code extension, built by a solo founder.

Grounded in the brain2 research KB (cited as `[#shortid]`) and verified against external sources (cited inline). Date: 2026-05-29.

---

## 1. Wedge + category line

**One-sentence wedge:**
> brain2 captures what you were doing the moment you get interrupted — branch, open files, diff, and a one-line "why" — and replays it as a 30-second resume card so you skip the 23-minute re-focus tax instead of rebuilding context by hand.

The wedge is deliberately narrow: not "developer memory," not "knowledge management" — just the *interruption → resume* moment. Narrow-and-frequent is the wedge pattern that makes a dev tool indispensable rather than nice-to-have ([daily.dev competitive positioning](https://business.daily.dev/resources/developer-tools-competitive-positioning-how-to-stand-out/)). The KB confirms the transformation-over-category rule: developers don't want "another observability platform," they want to "find production bugs in 30 seconds" — describe the transformation, not the category.

**"X for Y" category line — candidates:**

| Candidate | Why it works | Risk |
|---|---|---|
| **"Git stash for your head"** ✅ **recommend** | Anchors to a tool every dev already uses for the *exact* same job (shelve work, switch context, come back) — see the git-stash-as-scratchpad behavior devs already improvise ([Atlassian](https://www.atlassian.com/git/tutorials/saving-changes/git-stash)). Instantly legible, slightly witty, names the real competitor while reframing it. | Could read as "just a git feature." |
| "Save state for coding" | Gamer/console mental model (quicksave/resume). Universally understood, captures the resume-card feel. | Less developer-native; risks sounding gimmicky. |
| "The session-resume layer for AI coding" | Rides the hottest 2026 pain — agents waking up with amnesia ([Neural Notions](https://medium.com/neuralnotions/the-agent-memory-problem-how-claude-md-solves-the-stateless-context-crisis-in-ai-coding-agents-af924609f838)). Future-facing. | Narrows to the agent crowd; undersells the solo-human-dev use. |

**Recommendation: lead with "Git stash for your head."** It does what the Supabase "open-source Firebase alternative" line did — anchor to something familiar so the purpose is obvious in five words, even if it's not literally accurate, because it makes sense to the audience ([Medium / Supabase](https://medium.com/@takafumi.endo/why-supabase-became-the-go-to-open-source-alternative-to-firebase-2d3cd59e7094)). Keep "session-resume layer for AI coding" as the secondary line for agentic-coding channels.

---

## 2. ICP personas

Three personas, ranked by launch priority. brain2's prerequisites are met for all three: instant access, self-service, free tier, no signup on local — exactly the frictionless-eval bar developers require before they'll touch a tool [#f21b3893].

### Persona A — Solo AI-assisted indie dev *(primary)*
- **Who:** Ships solo or near-solo, lives in VS Code + Claude Code/Cursor, juggles 2-4 side projects, gets interrupted constantly (day job, Discord, life).
- **Context-loss pain:** Comes back to a repo after days and has no idea what the half-finished branch was for. Re-reads their own diff to reconstruct intent. The cost is real: ~23 min to fully refocus after an interruption (Gloria Mark / Carnegie Mellon), and only ~2h48m of focused work per day survives the toggling ([techworld-with-milan](https://newsletter.techworld-with-milan.com/p/context-switching-is-the-main-productivity)).
- **Where they hang out:** Hacker News, r/programming, daily.dev, X dev-tools circles, Claude Code / Cursor Discords. Peer-led, forum-validated discovery [#f21b3893].
- **What makes them try/buy:** Free local tier, no auth, data never leaves the machine (privacy is a buy-trigger, not a footnote). `pip install` + one MCP line → working in 60 seconds. They'll *try* free instantly; they *buy* cloud only once cross-machine sync ships. Launch them on the free tier.

### Persona B — Agentic-coding power user *(strong secondary — ride the trend)*
- **Who:** Runs multiple Claude Code / Cursor / Windsurf agents, heavy MCP user, maintains a CLAUDE.md, may run parallel agent sessions.
- **Context-loss pain:** Agents are stateless — every new session "wakes up with complete amnesia" and they re-explain project state from scratch ([DEV / whoffagents](https://dev.to/whoffagents/why-your-claude-code-sessions-keep-losing-context-and-how-to-fix-it-nia)). This is described as "the most painful unsolved problem in AI-assisted development as of mid-2026" ([Marvin Ma / Medium](https://medium.com/@marvin-lijma/why-your-ai-coding-agent-keeps-forgetting-everything-and-why-prompt-engineering-wont-fix-it-a76bdc0a724f)).
- **Where they hang out:** Same as A plus MCP-server lists, Claude Code plugin marketplace, agent-tooling threads.
- **What makes them try/buy:** brain2 *is* an MCP server (`brain2_capture/resume/explore`) — drop-in for their existing stack. Trigger: "my agent forgets between sessions." Try free; this segment is the most likely to evangelize on social.

### Persona C — Senior on a multi-repo team *(future / cloud-gated)*
- **Who:** Senior/staff eng, 5-15 repos, frequent PR-review and incident interrupts that yank them off their own branch.
- **Context-loss pain:** Interrupt-driven all day; the costliest switches (complex code) take up to 45 min to recover (Carnegie Mellon), and context switching is estimated at ~$50K/developer/year ([DEV / teamcamp](https://dev.to/teamcamp/the-hidden-cost-of-developer-context-switching-why-it-leaders-are-losing-50k-per-developer-1p2j)).
- **Where they hang out:** Internal eng Slacks, Lobsters, team-lead newsletters.
- **What makes them try/buy:** Needs cross-repo search + cross-machine sync + team sharing — all **designed, not yet built**. Do **not** market to this persona at launch beyond "coming soon." Listed to keep the cloud roadmap honest, not as a launch target.

---

## 3. Messaging hierarchy

Lead with the hero interaction; everything else supports it. The hero-feature discipline is proven — Anthropic led Claude with one graspable interaction ("AI controlling the computer") rather than a feature list [#fbc14a3a]. And tone matters: developers want to be educated/enabled, not sold — kill "best-in-class / AI-driven," state the factual mechanism [#11febc35]. Frame every line as an outcome, not a feature [#b362e886].

**Hero (the one interaction): capture → 30-second resume.**

> **Headline:** `git stash for your head`
> **Subhead:** Capture what you're doing before you get pulled away — branch, open files, diff, and a one-line "why." Come back to a 30-second resume card instead of 23 minutes of "where was I?"

Alternate hero copy (A/B these):
- H: `You'll forget what this branch was for. brain2 won't.` / S: `One snapshot now → a 30-second resume card later. Local, free, never leaves your machine.`
- H: `Stop paying the 23-minute re-focus tax.` / S: `brain2 captures your workspace state on interruption and replays it as a 30-second resume card.`

**Supporting messages (in order):**

1. **Free, local, private by default.** "Runs on your machine. SQLite, loopback-only, no account, no cloud. Your code context never leaves your laptop." — privacy as a feature, factual not fluffy [#11febc35].
2. **Drop-in for your stack.** "Works as a Claude Code plugin and a VS Code extension. One MCP line or one install — capturing in 60 seconds." Frictionless self-serve eval is the developer prerequisite [#f21b3893].
3. **Fixes agent amnesia.** "Your AI agent wakes up with amnesia every session. brain2 hands it the resume card so it knows what you were doing." Targets Persona B's exact, current pain ([whoffagents](https://dev.to/whoffagents/why-your-claude-code-sessions-keep-losing-context-and-how-to-fix-it-nia)).
4. **Proof over claims.** Lead the landing page with a 20-second GIF of capture→resume and a copy-paste install block, not a hero illustration — show, don't tell [#2e77d6ca], [#5cef7337].

**Do / Don't (developer messaging):**
- DO: state the mechanism in plain language ("captures branch + open files + diff + a one-line hypothesis") [#844bbbf7]. DON'T: "AI-powered productivity platform" [#11febc35].
- DO: lead with the free tier and a runnable snippet [#f21b3893]. DON'T: gate the demo behind an email [#5cef7337].
- DO: cite the 23-min / $50K numbers as context, sourced. DON'T: invent ROI claims you can't back.

---

## 4. Competitor / alternative teardown

The real competitor is **inertia + improvised tooling**, not a funded rival. Four alternatives:

### 1. Do nothing / human memory *(the #1 competitor)*
- **What it is:** Dev re-reads their own diff and reconstructs intent from scratch on return.
- **Cost:** ~23 min refocus, up to 45 min for complex tasks (Carnegie Mellon); ~$50K/dev/yr in lost context-switching time ([teamcamp](https://dev.to/teamcamp/the-hidden-cost-of-developer-context-switching-why-it-leaders-are-losing-50k-per-developer-1p2j)).
- **brain2 differentiation:** The *intent* (the one-line hypothesis) is the part memory loses first and a diff can't recover. brain2 captures the "why," not just the "what." This is the build-vs-buy / "it's free to just remember" objection — counter it with a signature piece quantifying the real cost of doing nothing [#533cc370].

### 2. git stash + a WIP commit
- **What it is:** Shelve dirty work; sometimes a `git stash save "descriptive message"`.
- **Limit:** Stash saves *code*, not *context* — no open-file set, no cursor, no rationale, and "after a while it's hard to remember what each stash contains" ([Atlassian](https://www.atlassian.com/git/tutorials/saving-changes/git-stash)). It's explicitly "not reliable long-term storage."
- **brain2 differentiation:** Captures the workspace *and* the intent, searchable later, survives across days/machines (cloud). The "git stash for your head" line co-opts this competitor directly.

### 3. A scratchpad notes file / scratchpad repo
- **What it is:** TODO.md, a notes file, or a per-feature scratchpad branch ([DEV / bsawyer](https://dev.to/bsawyer/keeping-track-of-notes-across-projects-and-features-4jdg)).
- **Limit:** Manual, easy to forget to update, drifts out of sync with actual workspace state, no structure.
- **brain2 differentiation:** Auto-captures real state (branch/files/diff) on the interruption trigger — zero discipline required — vs. a file you must remember to write *while* being interrupted (you won't).

### 4. AI-agent memory tools (agentmemory, claude-mem, CLAUDE.md, ECC hooks)
- **What it is:** MCP servers / hooks that persist agent context across sessions — agentmemory (~$10/yr, 95.2% recall, [aibuilderclub](https://www.aibuilderclub.com/blog/ai-coding-agent-memory-agentmemory)), claude-mem ([Medium / Gary Parker](https://medium.com/@qa.gary.parker/why-lose-context-in-claude-sessions-a-claude-mem-solution-c717b6ea6de7)), CLAUDE.md, Everything Claude Code session hooks.
- **Limit:** They serve *the agent's* memory (conversation/project facts). They don't give *the human* a glanceable 30-second resume of "what was I doing," and they're agent-only — useless when you're coding without an agent.
- **brain2 differentiation:** Human-first resume card *plus* an MCP surface, so it serves both the developer (VS Code card) and the agent (preamble) from one snapshot. This is the most credible *funded-adjacent* competitor set — watch it closely; position brain2 as "for you, not just your agent." Honest note: this is a fast-moving, crowded niche.

---

## 5. Three risky positioning assumptions to validate

Run the pre-launch message test against lookalikes; act on patterns, not single replies; target **≥5/10 positive** lookalike responses per claim [#1665bb5c]. Beta cohort of 20-50 [#854de64b].

1. **"Git stash for your head" lands, not confuses.** Risk: devs read it as a minor git plugin and bounce. *Test:* show the line cold to 10 lookalikes; ≥5 should correctly paraphrase the product without further explanation. *Fallback:* swap to "save state for coding."

2. **The pain is felt strongly enough to act on, not just nodded at.** Risk: devs agree context-switching is costly but won't install a tool for it (the "I'll just remember / use git stash" objection). *Test:* of 10 lookalikes shown the hero, ≥5 should click install or ask for the link unprompted. *Fallback:* lead harder with the agent-amnesia angle (Persona B), where the pain is acute and current.

3. **Local-and-private is a try-trigger, not a yawn.** Risk: "data never leaves your machine" reads as table stakes and the free tier cannibalizes any path to paid. *Test:* ≥5/10 cite privacy/local as a reason they'd try it; separately, ≥5/10 say they'd pay for cross-machine sync *once it exists*. *Fallback:* if sync demand is weak, re-cut the paid tier around team-sharing/cross-repo for Persona C instead.
