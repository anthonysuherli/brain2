# Resume-first — the shared convention

The canonical preflight for **every KB-scoped br8n operation**. All skills link
here instead of re-describing it. Each call site adds only its own one-line twist.

## Resolve the target first — no active-KB state

br8n derives the target from the workspace, not from a stored "active KB":

- `project` = current git repo name — `basename "$(git rev-parse --show-toplevel)"`
- `kb` = current git branch — `git branch --show-current`

Run those two commands first and pass `project` and `kb` to every `br8n_*` tool.
If not inside a git repo, ask the user for a project/kb name once.

## Resume-first — start EVERY KB-scoped operation here

Every operation begins by **tapping the session KB on the user's intent** *before*
doing its main work, so prior context directs what you do next instead of acting
blind.

1. **Tap.** Call `mcp__plugin_br8n_br8n__br8n_resume(project, kb, query=<the op's prompt /
   topic>)`. It returns `{banner, preamble, coverage, project, kb}` — the br8n
   wordmark, the XML `<preamble>` (synopsis + most-relevant snapshots/findings),
   and the coverage band (`rich` / `sparse` / `gap`) for the query. For ops with no
   natural query, pass the topic or omit `query` for the synopsis-only spine.
   *Guard:* if the KB doesn't exist yet, `br8n_resume` will surface that — treat
   it as a brand-new session, note "new KB", and proceed.

2. **Show what was collected** — ALWAYS open the message with the `banner`
   verbatim, then parse `preamble` and print, leading with the band:
   > ```
   > <banner — exactly as returned>
   > ```
   > **Resume card** — coverage `<coverage>`, query: `<query, or "synopsis-only">`
   > - Synopsis: `<N>` topics — list each `topic`.
   > - Snapshots/findings: `<M>` — list each `<title>` (`category`), most-relevant first.

   Keep it tight: titles + categories, not full `content`. The banner leads **every**
   resume surface; the digest keeps grounding **auditable instead of silent**.

3. **Let it direct intent** — branch on the returned `coverage`:
   - **rich** → say so; prefer instant recall over new web research; confirm with
     the user before doing redundant work.
   - **sparse** → proceed, but target the work at the thin areas.
   - **gap** (nothing banded / `<empty/>`) → nothing to ground on; offer
     `/br8n:explore` to gap-fill, or do the operation's full work.

The per-operation steps elsewhere all assume **step 0 = this preflight**.

## Mirror: loop-back

Resume-first is the **read** side — grounding on what the KB holds. Its write-side
mirror is capture: when an operation surfaces durable intent or a decision worth
keeping, persist it with `br8n_capture` (a `note`/`manual` trigger) so the next
resume is richer. *Ground, then grow.*
