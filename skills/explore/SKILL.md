---
name: explore
description: Force the brain2 gap-fill pipeline — plan → web search → crawl → extract → merge — to seed or deepen the repo+branch KB from the web, then rebuild the synopsis. Use when /brain2:pickup returns coverage='gap', when starting a KB from scratch, or when the user explicitly wants fresh online research persisted into the session KB.
---

# brain2 — Explore

Run the exploration pipeline to grow the KB from the web. This is the **grow** step
that `/brain2:search` calls conditionally — invoke it directly when you already know
the KB is thin and want to fill it.

## Step 0 — Resolve target + tap

Follow [`../_shared/preamble-first.md`](../_shared/preamble-first.md): resolve
`project`/`kb` from git, then `mcp__plugin_brain2_brain2__brain2_resume(project, kb, query=<the
topic>)` to confirm the gap is real and to **target the prompt at the thin areas**
rather than re-fetching what's already known. Show the resume card.

## Step 1 — Shape the prompt

Turn the user's topic into a focused exploration `prompt`. If the resume card showed
partial coverage, narrow the prompt to the missing slice (don't re-explore covered
ground). Pass `max_findings` only if the user wants to cap breadth; otherwise let
the config default apply.

## Step 2 — Run (blocking)

```
mcp__plugin_brain2_brain2__brain2_explore(project, kb, prompt=<focused prompt>, max_findings?)
```

This **blocks 1–3 minutes** (plan→search→crawl→extract→merge). Tell the user it's
running before you call it. On return you get `{finding_count, finding_ids}`; the
synopsis rebuild is scheduled automatically.

## Step 3 — Report + re-ground

State how many findings were persisted. Then re-tap with
`mcp__plugin_brain2_brain2__brain2_resume(project, kb, query=<topic>)` to show the now-richer card
and answer whatever prompted the explore. The next `/brain2:pickup` will reflect the
new knowledge.
