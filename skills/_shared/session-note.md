# Session-note — the shared convention

The canonical end-of-session write. The `Stop` hook fires at the end of every
conversation and injects a directive pointing here; this is what to do when it does.
Other surfaces link here instead of re-describing it.

## When it runs

At **session end** — the `Stop` hook (`hooks/session-note.py`) emits a non-blocking
`additionalContext` directive. This is fire-and-forget: it must never block the user
or fail the session. If the gate `BR8N_LIVING_DOCS=0` is set, the hook stays silent
and there is nothing to do.

## Skip silently if nothing happened

First decision: **was anything substantive done this session?** Decisions made, code
changed, a problem solved, an open thread left dangling — those are worth a note. A
trivial Q&A, a read-only look-around, or a one-line answer is **not**. If nothing
durable happened, do nothing — no note, no message.

## Resolve the target

Same as every KB-scoped op (see `preamble-first.md`):

- `project` = git repo basename — `basename "$(git rev-parse --show-toplevel)"`
- `kb` = current git branch — `git branch --show-current`
- `project_path` = repo root — `git rev-parse --show-toplevel`

## Read the policy, then render

1. **Fetch the note policy.** Call
   `mcp__br8n__br8n_notes_policy_get(project, kb, project_path)`. It returns the
   note **template** (the sections this KB wants) and a **steer** (free-text guidance
   on what to emphasize / omit). If it's unavailable, fall back to a sensible default:
   `## Decisions`, `## Changes`, `## Open questions`.

2. **Summarize THIS conversation into those sections, honoring the steer.** Durable
   facts only — what was decided, what changed, what's still open. Not a transcript,
   not a play-by-play. Tight markdown.

## Persist with br8n_note

One call writes the note as both a searchable `note` Finding **and** a markdown file
under `.br8n/notes/<kb>/`, then schedules a debounced re-distill of the curated doc
tree:

```
mcp__br8n__br8n_note(
    project=<repo basename>,
    kb=<git branch>,
    project_path=<repo root>,
    content=<the rendered markdown>,
    session_id=<this session's id>,
    title=<one-line summary of the session>,
)
```

Returns `{finding_id, note_path, project, kb}`. That's the whole job — don't block,
don't announce, don't re-raise. The distill happens in the background.
