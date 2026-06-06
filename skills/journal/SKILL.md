---
name: journal
description: Your cross-project personal journal — write an entry any time (insight, reflection, reference, decision) and search it back by meaning. Distinct from session notes (which are per repo+branch, written at session end); the journal is global and on-demand. Use when the user wants to jot a durable thought, "journal this", "note to self", or recall past entries ("what did I conclude about X", "search my journal").
---

# br8n — Journal (cross-project, write-anytime, searchable)

The journal is your **global notebook**, separate from session notes. Session
notes are bound to the current repo+branch and written automatically at session
end; a journal entry is written **whenever you choose** and is **searchable
across every project**. Both live in the same `~/.br8n/brain.db`; the journal
just uses a reserved, repo-independent scope.

## Step 0 — Resolve optional context

The journal itself is global, so a write needs no project. But it's useful to
stamp **where you were** when you journaled, and `scope=project|both` searches
need the current repo+branch:

```bash
basename "$(git rev-parse --show-toplevel)"   # project (optional context)
git branch --show-current                     # kb
git rev-parse --show-toplevel                 # project_path
```

If not in a git repo, omit them (writes still work; `scope=project` is then N/A).

## Mode select — branch on the args

| Invocation | Mode | Do |
|---|---|---|
| `/br8n:journal <text>` | **Write** | Step A — save an entry |
| `/br8n:journal search <query> [--scope both\|journal\|project] [--type T]` | **Search** | Step B — recall by meaning |
| `/br8n:journal recent [N]` | **Recent** | Step C — list latest entries |

If the first arg is `search` or `recent`, use that mode; otherwise treat the
whole input as the text to journal.

## Step A — Write an entry

From the user's text, infer a `type` (one of `insight`, `reflection`,
`reference`, `decision`) and any obvious `tags`; when unclear, leave `type`
empty. Then call:

`mcp__plugin_br8n_br8n__br8n_journal(text, type, tags, title, project, project_path)`

- `text` — the entry (required).
- `type` / `tags` — your inferred label + keywords (optional).
- `project` / `project_path` — the resolved repo context, if any (optional).

On success it returns `{finding_id, entry_path, scope}`. Confirm briefly: echo
the one-line title and the `type`, e.g. *"Journaled (decision): prefer scope
filters over separate corpora."* Do not paste the whole entry back.

## Step B — Search the journal

Parse `--scope` (default `both`) and optional `--type` from the args; the rest
is the query. Call:

`mcp__plugin_br8n_br8n__br8n_journal_search(query, scope, type, limit, project, kb, project_path)`

- `scope=journal` — your journal entries only.
- `scope=project` — this repo+branch's session notes only (pass `project`/`kb`).
- `scope=both` (default) — journal entries **and** every project's notes.

It returns `{results: [{title, snippet, score, category, tags, id}], scope,
count}`, ranked by similarity. Render the top results as a short list — title,
a one-line snippet, and the `category` (journal vs note) so the user can tell
their notebook from their work-logs. If `count` is 0, say so and suggest a
broader `--scope` or different wording.

## Step C — List recent entries

`/br8n:journal recent [N]` (default 10). Call
`mcp__plugin_br8n_br8n__br8n_journal_recent(limit=N)`. It returns
`{entries: [{title, tags, created_at, ...}], count}`. Render newest-first as a
compact list (date · title · type). This is a chronological skim, not a search.
